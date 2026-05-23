"""Unified, lenient channel discovery directly into the channels table."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone

import httpx
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.circuit_breaker import is_open
from core.supabase import get_supabase_client
from core.system_settings import get_runtime_settings
from tasks.scrape_bitchute import scrape_bitchute_channel
from tasks.scrape_rumble import scrape_rumble_channel
from utils.channel_urls import (
    ChannelUrlCandidate,
    canonicalize_channel_url,
    extract_supported_channel_urls,
)
from utils.taxonomy import KEYWORD_TAXONOMY

logger = logging.getLogger(__name__)

_SERPER_SEARCH_URL = "https://google.serper.dev/search"
_QUERY_LIMIT = 1_000_000
_MAX_PAGES_PER_QUERY = 1_000_000
_INSERT_LIMIT = 1_000_000_000
_QUERY_STAGNATION_LIMIT = 1_000_000
_GLOBAL_STOP_NO_NEW_INSERTED = 1_000_000
_MAX_FEEDBACK_TERMS = 1_000_000
_SCRAPE_NEW_LIMIT = 1_000_000
_CHANNEL_PAGE_SIZE = 1_000_000
_SERPER_MAX_ATTEMPTS = 3
_SERPER_RETRY_DELAY_SECONDS = 1.5
_SERPER_RETRY_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_SERP_LINK_KEYS = {
    "link",
    "url",
    "sourceurl",
    "source_url",
    "redirecturl",
    "redirect_url",
}
_SERP_TEXT_KEYS = {
    "attributes",
    "date",
    "description",
    "displayedLink",
    "displayed_link",
    "extensions",
    "highlightedWords",
    "highlighted_words",
    "link",
    "position",
    "richSnippet",
    "rich_snippet",
    "sitelinks",
    "snippet",
    "title",
    "url",
}
_RELATIVE_RUMBLE_CHANNEL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])/(c|user)/([A-Za-z0-9][A-Za-z0-9_-]{1,127})\b",
    re.IGNORECASE,
)
_RELATIVE_BITCHUTE_CHANNEL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])/channel/([A-Za-z0-9][A-Za-z0-9_-]{1,127})\b",
    re.IGNORECASE,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_normalize_text_values(item))
        return values
    if isinstance(value, dict):
        values = []
        for item in value.values():
            values.extend(_normalize_text_values(item))
        return values
    if isinstance(value, (int, float)):
        return [str(value)]
    return []


def _fallback_name(channel_url: str) -> str:
    return channel_url.rstrip("/").split("/")[-1] or channel_url


def _existing_channel_by_url(client, channel_url: str) -> dict[str, object] | None:
    try:
        result = (
            client.table("channels")
            .select(
                "id,channel_url,name,has_been_scraped,discovery_confidence,discovery_evidence_count"
            )
            .eq("channel_url", channel_url)
            .maybe_single()
            .execute()
        )
    except APIError:
        logger.warning("Failed to look up existing channel by URL: %s", channel_url)
        return None

    data = getattr(result, "data", None)
    return data if isinstance(data, dict) else None


def _iter_channel_rows(client, columns: str):
    """Yield channel rows in pages so discovery can scan large databases."""
    page_size = max(
        1, min(get_runtime_settings().discovery_channel_page_size, _CHANNEL_PAGE_SIZE)
    )
    start = 0
    while True:
        result = (
            client.table("channels")
            .select(columns)
            .range(start, start + page_size - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        for row in rows:
            yield row
        if len(rows) < page_size:
            break
        start += page_size


def upsert_discovered_channel(
    *,
    client,
    candidate: ChannelUrlCandidate,
    source: str,
    source_ref: str | None,
    title: str | None,
    category: str | None,
    confidence: float,
) -> tuple[bool, bool]:
    """Insert or refresh a discovered channel row.

    Returns (inserted_or_updated, already_existed). Existing scraped rows keep
    their scraped identity; only discovery evidence is refreshed.
    """
    now = _utc_now_iso()
    existing = _existing_channel_by_url(client, candidate.channel_url)
    evidence_count = int((existing or {}).get("discovery_evidence_count") or 0) + 1
    best_confidence = max(
        float((existing or {}).get("discovery_confidence") or 0.0),
        confidence,
    )

    if existing is not None:
        payload: dict[str, object] = {
            "discovery_confidence": best_confidence,
            "discovery_evidence_count": evidence_count,
            "discovery_last_seen_at": now,
            "last_discovery_source": source,
            "updated_at": now,
        }
        if source_ref:
            payload["discovered_from_channel_id"] = source_ref
        if category:
            payload["discovery_category"] = category
        if not bool(existing.get("has_been_scraped")) and title:
            payload["name"] = title

        result = (
            client.table("channels")
            .update(payload)
            .eq("channel_url", candidate.channel_url)
            .execute()
        )
        return bool(result.data), True

    payload = {
        "platform": candidate.platform,
        "channel_url": candidate.channel_url,
        "name": title or _fallback_name(candidate.channel_url),
        "description": "",
        "is_active": True,
        "has_been_scraped": False,
        "discovery_source": source,
        "last_discovery_source": source,
        "discovery_category": category,
        "discovery_status": "new",
        "discovery_confidence": confidence,
        "discovery_evidence_count": 1,
        "discovery_last_seen_at": now,
        "discovered_at": now,
        "updated_at": now,
    }
    if source_ref:
        payload["discovered_from_channel_id"] = source_ref

    result = client.table("channels").insert(payload).execute()
    return bool(result.data), False


def _collect_known_channel_candidates(
    channel: dict[str, object],
) -> list[tuple[ChannelUrlCandidate, str]]:
    field_blobs = {
        "contact_info": _normalize_text_values(channel.get("contact_info")),
        "secondary_urls": _normalize_text_values(channel.get("secondary_urls")),
        "description": _normalize_text_values(channel.get("description")),
        "video_titles": _normalize_text_values(channel.get("video_titles")),
        "channel_url": _normalize_text_values(channel.get("channel_url")),
    }

    candidates: dict[str, tuple[ChannelUrlCandidate, str]] = {}
    source_platform = str(channel.get("platform") or "")
    for field_name, blobs in field_blobs.items():
        for blob in blobs:
            for candidate in extract_supported_channel_urls(blob):
                candidates.setdefault(candidate.channel_url, (candidate, field_name))
            for candidate in _extract_relative_channel_urls(blob, source_platform):
                candidates.setdefault(candidate.channel_url, (candidate, field_name))
    return list(candidates.values())


def _extract_relative_channel_urls(
    text: str, source_platform: str
) -> list[ChannelUrlCandidate]:
    """Extract same-platform relative channel links from scraped page fragments."""
    candidates: dict[str, ChannelUrlCandidate] = {}
    if source_platform == "rumble":
        for match in _RELATIVE_RUMBLE_CHANNEL_PATH_PATTERN.finditer(text):
            candidate = canonicalize_channel_url(
                f"https://rumble.com/{match.group(1).lower()}/{match.group(2)}"
            )
            if candidate is not None:
                candidates[candidate.channel_url] = candidate
    elif source_platform == "bitchute":
        for match in _RELATIVE_BITCHUTE_CHANNEL_PATH_PATTERN.finditer(text):
            candidate = canonicalize_channel_url(
                f"https://bitchute.com/channel/{match.group(1)}"
            )
            if candidate is not None:
                candidates[candidate.channel_url] = candidate
    return list(candidates.values())


def _seed_discovery_confidence(source_field: str) -> float:
    """Score seed evidence by how directly the source field points to a channel."""
    if source_field in {"contact_info", "secondary_urls"}:
        return 0.97
    if source_field == "description":
        return 0.92
    if source_field == "video_titles":
        return 0.84
    return 0.9


def _query_for_keyword(keyword: str, platform: str) -> str:
    if platform == "rumble":
        return f'site:rumble.com "{keyword}" (inurl:/c/ OR inurl:/user/) -inurl:/v -inurl:/embed/'
    return f'site:bitchute.com "{keyword}" inurl:/channel/ -inurl:/video/ -inurl:/embed/'


def _category_phrase(category: str) -> str:
    return category.replace("_", " ")


def _keyword_templates(category: str, keyword: str) -> list[str]:
    category_phrase = _category_phrase(category)
    templates = [
        _query_for_keyword(keyword, "rumble"),
        _query_for_keyword(keyword, "bitchute"),
        f'site:rumble.com/c/ "{keyword}" -inurl:/v -inurl:/embed/',
        f'site:rumble.com/user/ "{keyword}" -inurl:/v -inurl:/embed/',
        f'site:bitchute.com/channel/ "{keyword}" -inurl:/video/ -inurl:/embed/',
        f'site:rumble.com "{keyword}" "{category_phrase}" -inurl:/v -inurl:/embed/',
        f'site:bitchute.com "{keyword}" "{category_phrase}" inurl:/channel/ -inurl:/video/ -inurl:/embed/',
        f'site:rumble.com intitle:"{keyword}" -inurl:/v -inurl:/embed/',
        f'site:bitchute.com intitle:"{keyword}" inurl:/channel/ -inurl:/video/ -inurl:/embed/',
        f'"{keyword}" "rumble.com/c/" -inurl:/v -inurl:/embed/',
        f'"{keyword}" "rumble.com/user/" -inurl:/v -inurl:/embed/',
        f'"{keyword}" "bitchute.com/channel/" -inurl:/video/ -inurl:/embed/',
        f'"{keyword}" "Rumble channel"',
        f'"{keyword}" "BitChute channel"',
    ]
    return list(dict.fromkeys(templates))


def _iter_search_queries() -> list[tuple[str, str, str, str]]:
    queries: list[tuple[str, str, str, str]] = []
    categories = list(KEYWORD_TAXONOMY.keys())
    keyword_positions: dict[str, int] = {category: 0 for category in categories}
    template_positions: dict[tuple[str, int], int] = {}

    query_limit = min(
        get_runtime_settings().discovery_serper_query_limit, _QUERY_LIMIT
    )
    while len(queries) < query_limit:
        progressed = False
        for category in categories:
            keywords = KEYWORD_TAXONOMY.get(category, [])
            if not keywords:
                continue

            keyword_pos = keyword_positions[category] % len(keywords)
            keyword = keywords[keyword_pos]
            templates = _keyword_templates(category, keyword)
            template_key = (category, keyword_pos)
            template_pos = template_positions.get(template_key, 0)

            if template_pos >= len(templates):
                keyword_positions[category] = (keyword_pos + 1) % len(keywords)
                keyword_pos = keyword_positions[category]
                keyword = keywords[keyword_pos]
                templates = _keyword_templates(category, keyword)
                template_key = (category, keyword_pos)
                template_pos = template_positions.get(template_key, 0)

            if template_pos >= len(templates):
                continue

            queries.append((category, keyword, templates[template_pos], "base"))
            template_positions[template_key] = template_pos + 1
            progressed = True
            if len(queries) >= query_limit:
                break

        if not progressed:
            break

    return queries


def _append_feedback_queries_round_robin(
    *,
    active_queries: list[tuple[str, str, str, str]],
    feedback_by_category: dict[str, list[tuple[str, str, str, str]]],
    max_queries: int,
) -> None:
    """Append one feedback query per category per pass to preserve niche fairness."""
    categories = list(KEYWORD_TAXONOMY.keys())
    while len(active_queries) < max_queries:
        progressed = False
        for category in categories:
            bucket = feedback_by_category.get(category) or []
            if not bucket:
                continue
            active_queries.append(bucket.pop(0))
            progressed = True
            if len(active_queries) >= max_queries:
                break
        if not progressed:
            break


def _search_serper(query: str, page: int = 1) -> list[dict[str, object]]:
    results_per_query = get_runtime_settings().discovery_results_per_query
    last_error: httpx.HTTPError | ValueError | None = None
    for attempt in range(1, _SERPER_MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=20.0) as http:
                response = http.post(
                    _SERPER_SEARCH_URL,
                    headers={
                        "X-API-KEY": scraper_settings.serp_api_key,
                        "Content-Type": "application/json",
                    },
                    json={"q": query, "num": results_per_query, "page": page},
                )
                if response.status_code in _SERPER_RETRY_STATUS_CODES:
                    response.raise_for_status()
                response.raise_for_status()
                payload = response.json()
                organic = payload.get("organic", []) if isinstance(payload, dict) else []
                if not isinstance(organic, list):
                    return []
                return organic[:results_per_query]
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt >= _SERPER_MAX_ATTEMPTS:
                raise
            delay = _SERPER_RETRY_DELAY_SECONDS * attempt
            logger.warning(
                "Serper search attempt %d/%d failed for query=%s page=%d; retrying in %.1fs: %s",
                attempt,
                _SERPER_MAX_ATTEMPTS,
                query,
                page,
                delay,
                exc,
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error
    return []


def _walk_serp_values(
    value: object, *, parent_key: str | None = None
) -> list[tuple[str | None, str]]:
    values: list[tuple[str | None, str]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            values.extend(_walk_serp_values(nested, parent_key=key_text))
        return values
    if isinstance(value, list):
        for nested in value:
            values.extend(_walk_serp_values(nested, parent_key=parent_key))
        return values
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        if text:
            values.append((parent_key, text))
    return values


def _extract_candidate_links(item: dict[str, object]) -> list[str]:
    links: dict[str, None] = {}
    for key, text in _walk_serp_values(item):
        normalized_key = (key or "").replace("-", "_").lower()
        if normalized_key in _SERP_LINK_KEYS or text.startswith(("http://", "https://")):
            links[text] = None
    return list(links.keys())


def _extract_serp_candidates(item: dict[str, object]) -> list[ChannelUrlCandidate]:
    """Extract supported channel URLs from SERP links, titles, and snippets."""
    candidates: dict[str, ChannelUrlCandidate] = {}
    for link in _extract_candidate_links(item):
        candidate = canonicalize_channel_url(link)
        if candidate is not None:
            candidates[candidate.channel_url] = candidate

    text_values = []
    for key, text in _walk_serp_values(item):
        normalized_key = (key or "").replace("-", "_")
        if key is None or normalized_key in _SERP_TEXT_KEYS:
            text_values.append(text)
    text_blob = " ".join(text_values)
    for candidate in extract_supported_channel_urls(text_blob):
        candidates[candidate.channel_url] = candidate
    return list(candidates.values())


def _candidate_was_direct_serp_link(
    item: dict[str, object], candidate: ChannelUrlCandidate
) -> bool:
    """Return whether the candidate came from a SERP URL field, not only text."""
    for link in _extract_candidate_links(item):
        linked_candidate = canonicalize_channel_url(link)
        if linked_candidate is None:
            continue
        if linked_candidate.channel_url == candidate.channel_url:
            return True
    return False


def _keyword_discovery_confidence(
    *,
    query: str,
    query_kind: str,
    item: dict[str, object],
    candidate: ChannelUrlCandidate,
) -> float:
    """Score discovery strength without rejecting useful loose candidates."""
    confidence = 0.75
    query_lower = query.lower()

    if query_kind == "feedback":
        confidence = 0.67
    if '"rumble channel"' in query_lower or '"bitchute channel"' in query_lower:
        confidence = min(confidence, 0.58)
    if "rumble.com/c/" in query_lower or "rumble.com/user/" in query_lower:
        confidence = max(confidence, 0.78)
    if "bitchute.com/channel/" in query_lower or "inurl:/channel/" in query_lower:
        confidence = max(confidence, 0.78)
    if _candidate_was_direct_serp_link(item, candidate):
        confidence = max(confidence, 0.82)

    return round(confidence, 2)


def _extract_feedback_terms(item: dict[str, object]) -> list[str]:
    blob = f"{item.get('title') or ''} {item.get('snippet') or ''}".lower()
    tokens = re.findall(r"[a-z][a-z0-9_]{3,20}", blob)
    ignore = {
        "about",
        "bitchute",
        "channel",
        "home",
        "official",
        "rumble",
        "video",
        "watch",
    }
    return [token for token in tokens if token not in ignore]


def _feedback_queries(
    *,
    platform: str,
    category: str,
    keyword: str,
    terms: list[str],
) -> list[str]:
    selected = terms[
        : min(get_runtime_settings().discovery_max_feedback_terms, _MAX_FEEDBACK_TERMS)
    ]
    queries: list[str] = []
    for term in selected:
        if platform == "rumble":
            queries.append(
                f'site:rumble.com "{keyword}" "{category}" "{term}" -inurl:/v -inurl:/embed/'
            )
        else:
            queries.append(
                f'site:bitchute.com inurl:/channel/ "{keyword}" "{category}" "{term}" -inurl:/video/ -inurl:/embed/'
            )
    return queries


def _discover_from_known_channels(client) -> dict[str, object]:
    insert_limit = min(get_runtime_settings().discovery_insert_limit, _INSERT_LIMIT)
    columns = "id,channel_url,name,description,video_titles,contact_info,secondary_urls"

    discovered = 0
    inserted = 0
    refreshed = 0
    duplicates = 0
    invalid = 0
    self_links = 0
    new_urls: list[dict[str, object]] = []
    field_metrics: dict[str, int] = {
        "video_titles": 0,
        "contact_info": 0,
        "secondary_urls": 0,
        "description": 0,
        "channel_url": 0,
    }
    self_link_field_metrics: dict[str, int] = {
        "video_titles": 0,
        "contact_info": 0,
        "secondary_urls": 0,
        "description": 0,
        "channel_url": 0,
    }
    platform_metrics = {"rumble": 0, "bitchute": 0}
    inserted_platform_metrics = {"rumble": 0, "bitchute": 0}

    source_channels = 0
    for channel in _iter_channel_rows(client, columns):
        source_channels += 1
        source_channel_id = str(channel.get("id") or "")
        source_channel_url = str(channel.get("channel_url") or "")
        for candidate, source_field in _collect_known_channel_candidates(channel):
            if candidate.channel_url == source_channel_url:
                self_links += 1
                self_link_field_metrics[source_field] = (
                    self_link_field_metrics.get(source_field, 0) + 1
                )
                continue

            discovered += 1
            field_metrics[source_field] = field_metrics.get(source_field, 0) + 1
            platform_metrics[candidate.platform] = platform_metrics.get(candidate.platform, 0) + 1
            if inserted >= insert_limit:
                break

            try:
                confidence = _seed_discovery_confidence(source_field)
                changed, existed = upsert_discovered_channel(
                    client=client,
                    candidate=candidate,
                    source="auto_seed",
                    source_ref=source_channel_id or None,
                    title=_fallback_name(candidate.channel_url),
                    category=None,
                    confidence=confidence,
                )
            except APIError:
                invalid += 1
                continue

            if not changed:
                invalid += 1
                continue
            if existed:
                refreshed += 1
                duplicates += 1
            else:
                inserted += 1
                inserted_platform_metrics[candidate.platform] = (
                    inserted_platform_metrics.get(candidate.platform, 0) + 1
                )
                new_urls.append(
                    {
                        "channel_url": candidate.channel_url,
                        "platform": candidate.platform,
                        "confidence": confidence,
                    }
                )
        if inserted >= insert_limit:
            break

    return {
        "source_channels": source_channels,
        "discovered": discovered,
        "inserted": inserted,
        "refreshed": refreshed,
        "duplicates": duplicates,
        "invalid": invalid,
        "self_links": self_links,
        "field_metrics": field_metrics,
        "self_link_field_metrics": self_link_field_metrics,
        "platform_metrics": platform_metrics,
        "inserted_platform_metrics": inserted_platform_metrics,
        "new_urls": new_urls,
    }


def _discover_from_keywords(client) -> dict[str, object]:
    runtime = get_runtime_settings()
    insert_limit = min(runtime.discovery_insert_limit, _INSERT_LIMIT)
    max_pages_per_query = min(
        runtime.discovery_max_pages_per_query, _MAX_PAGES_PER_QUERY
    )
    query_stagnation_limit = min(
        runtime.discovery_query_stagnation_limit, _QUERY_STAGNATION_LIMIT
    )
    global_stop_no_new = min(
        runtime.discovery_global_stop_no_new, _GLOBAL_STOP_NO_NEW_INSERTED
    )
    max_feedback_terms = min(runtime.discovery_max_feedback_terms, _MAX_FEEDBACK_TERMS)
    discovered = 0
    inserted = 0
    refreshed = 0
    duplicates = 0
    invalid = 0
    searched_queries = 0
    pages_fetched = 0
    raw_links = 0
    no_new_global = 0
    inserted_by_platform = {"rumble": 0, "bitchute": 0}
    category_metrics: dict[str, dict[str, int]] = {
        category: {
            "searched_queries": 0,
            "base_queries": 0,
            "feedback_queries": 0,
            "discovered": 0,
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 0,
        }
        for category in KEYWORD_TAXONOMY.keys()
    }
    feedback_terms_counter: Counter[str] = Counter()
    new_urls: list[dict[str, str]] = []

    seed_queries = _iter_search_queries()
    active_queries: list[tuple[str, str, str, str]] = list(seed_queries)
    feedback_by_category: dict[str, list[tuple[str, str, str, str]]] = {
        category: [] for category in KEYWORD_TAXONOMY.keys()
    }
    seen_feedback_queries: set[str] = set()
    max_active_queries = min(runtime.discovery_serper_query_limit, _QUERY_LIMIT) * 2
    query_idx = 0

    while query_idx < len(active_queries):
        category, keyword, query, query_kind = active_queries[query_idx]
        query_idx += 1
        if inserted >= insert_limit:
            break

        searched_queries += 1
        metrics = category_metrics.setdefault(
            category,
            {
                "searched_queries": 0,
                "base_queries": 0,
                "feedback_queries": 0,
                "discovered": 0,
                "inserted": 0,
                "refreshed": 0,
                "duplicates": 0,
                "invalid": 0,
            },
        )
        metrics["searched_queries"] += 1
        if query_kind == "feedback":
            metrics["feedback_queries"] += 1
        else:
            metrics["base_queries"] += 1
        no_new_for_query = 0
        no_new_for_active_query = True
        terms_for_query: Counter[str] = Counter()

        for page_num in range(1, max_pages_per_query + 1):
            if inserted >= insert_limit:
                break
            pages_fetched += 1
            new_this_page = 0
            try:
                organic_results = _search_serper(query, page=page_num)
            except (httpx.HTTPError, ValueError) as exc:
                logger.error(
                    "Keyword discovery search failed for query=%s page=%d: %s",
                    query,
                    page_num,
                    exc,
                )
                break

            for item in organic_results:
                title = str(item.get("title") or "").strip()
                terms = _extract_feedback_terms(item)
                terms_for_query.update(terms)
                feedback_terms_counter.update(terms)
                raw_links += len(_extract_candidate_links(item))
                candidates = _extract_serp_candidates(item)
                if not candidates:
                    invalid += 1
                    metrics["invalid"] += 1
                    continue

                for candidate in candidates:
                    discovered += 1
                    metrics["discovered"] += 1
                    try:
                        confidence = _keyword_discovery_confidence(
                            query=query,
                            query_kind=query_kind,
                            item=item,
                            candidate=candidate,
                        )
                        changed, existed = upsert_discovered_channel(
                            client=client,
                            candidate=candidate,
                            source="auto_keyword",
                            source_ref=None,
                            title=title or _fallback_name(candidate.channel_url),
                            category=category,
                            confidence=confidence,
                        )
                    except APIError:
                        invalid += 1
                        metrics["invalid"] += 1
                        continue

                    if not changed:
                        invalid += 1
                        metrics["invalid"] += 1
                        continue
                    if existed:
                        refreshed += 1
                        duplicates += 1
                        metrics["refreshed"] += 1
                        metrics["duplicates"] += 1
                    else:
                        inserted += 1
                        inserted_by_platform[candidate.platform] += 1
                        metrics["inserted"] += 1
                        new_this_page += 1
                        no_new_for_active_query = False
                        new_urls.append(
                            {
                                "channel_url": candidate.channel_url,
                                "platform": candidate.platform,
                                "confidence": confidence,
                            }
                        )

            if new_this_page == 0:
                no_new_for_query += 1
            else:
                no_new_for_query = 0
            if no_new_for_query >= query_stagnation_limit:
                break

        platform = "rumble" if "site:rumble.com" in query else "bitchute"
        feedback_queries = _feedback_queries(
            platform=platform,
            category=category,
            keyword=keyword,
            terms=[term for term, _count in terms_for_query.most_common(max_feedback_terms)],
        )
        for feedback_query in feedback_queries:
            if feedback_query in seen_feedback_queries:
                continue
            seen_feedback_queries.add(feedback_query)
            feedback_by_category.setdefault(category, []).append(
                (category, keyword, feedback_query, "feedback")
            )
        if query_idx >= len(active_queries):
            _append_feedback_queries_round_robin(
                active_queries=active_queries,
                feedback_by_category=feedback_by_category,
                max_queries=max_active_queries,
            )

        if no_new_for_active_query:
            no_new_global += 1
        else:
            no_new_global = 0
        if no_new_global >= global_stop_no_new:
            logger.info("Keyword discovery stopping due to global no-new-insert limit")
            break

    return {
        "searched_queries": searched_queries,
        "pages_fetched": pages_fetched,
        "raw_links": raw_links,
        "discovered": discovered,
        "inserted": inserted,
        "refreshed": refreshed,
        "duplicates": duplicates,
        "invalid": invalid,
        "inserted_rumble": inserted_by_platform["rumble"],
        "inserted_bitchute": inserted_by_platform["bitchute"],
        "category_metrics": category_metrics,
        "feedback_terms": [term for term, _ in feedback_terms_counter.most_common(10)],
        "new_urls": new_urls,
    }


def queue_discovered_channel_scrapes(new_urls: list[dict[str, object]]) -> int:
    """Queue scrapes for newly discovered channels."""
    queued = 0
    scrape_new_limit = min(
        get_runtime_settings().discovery_new_scrape_limit, _SCRAPE_NEW_LIMIT
    )
    seen: set[str] = set()
    client = get_supabase_client()
    priority_rows = sorted(
        new_urls,
        key=lambda row: float(row.get("confidence") or 0.0),
        reverse=True,
    )
    for row in priority_rows:
        if queued >= scrape_new_limit:
            break
        channel_url = str(row.get("channel_url") or "")
        platform = str(row.get("platform") or "")
        if not channel_url or channel_url in seen:
            continue
        seen.add(channel_url)
        if platform in {"rumble", "bitchute"} and is_open(platform):
            logger.warning(
                "Skipping discovered %s scrape due to open circuit breaker: %s",
                platform,
                channel_url,
            )
            continue
        if platform == "rumble":
            scrape_rumble_channel.delay(channel_url)
            queued += 1
        elif platform == "bitchute":
            scrape_bitchute_channel.delay(channel_url)
            queued += 1
        else:
            continue
        try:
            client.table("channels").update(
                {
                    "discovery_status": "queued",
                    "updated_at": _utc_now_iso(),
                }
            ).eq("channel_url", channel_url).execute()
        except (APIError, TypeError, ValueError) as exc:
            logger.warning(
                "Failed to mark discovered channel queued: %s - %s",
                channel_url,
                exc,
                exc_info=True,
            )
    return queued


def discover_channels_now(*, queue_scrapes: bool = False) -> dict[str, object]:
    """Run all automatic discovery sources and insert channels directly."""
    client = get_supabase_client()
    discovery_failed = False
    try:
        seed_result = _discover_from_known_channels(client)
    except (APIError, KeyError, TypeError, ValueError) as exc:
        discovery_failed = True
        logger.error("Seed discovery phase failed: %s", exc, exc_info=True)
        seed_result = {
            "source_channels": 0,
            "discovered": 0,
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 1,
            "self_links": 0,
            "field_metrics": {},
            "self_link_field_metrics": {},
            "platform_metrics": {},
            "inserted_platform_metrics": {},
            "new_urls": [],
            "error": str(exc),
        }

    try:
        keyword_result = _discover_from_keywords(client)
    except (APIError, KeyError, TypeError, ValueError) as exc:
        discovery_failed = True
        logger.error("Keyword discovery phase failed: %s", exc, exc_info=True)
        keyword_result = {
            "searched_queries": 0,
            "pages_fetched": 0,
            "raw_links": 0,
            "discovered": 0,
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 1,
            "inserted_rumble": 0,
            "inserted_bitchute": 0,
            "category_metrics": {},
            "feedback_terms": [],
            "new_urls": [],
            "error": str(exc),
        }

    new_urls = [
        *(seed_result.get("new_urls") or []),
        *(keyword_result.get("new_urls") or []),
    ]
    scrape_queued = queue_discovered_channel_scrapes(new_urls) if queue_scrapes else 0

    return {
        "seed_expansion": {key: value for key, value in seed_result.items() if key != "new_urls"},
        "keyword_expansion": {key: value for key, value in keyword_result.items() if key != "new_urls"},
        "inserted": int(seed_result["inserted"]) + int(keyword_result["inserted"]),
        "refreshed": int(seed_result["refreshed"]) + int(keyword_result["refreshed"]),
        "duplicates": int(seed_result["duplicates"]) + int(keyword_result["duplicates"]),
        "invalid": int(seed_result["invalid"]) + int(keyword_result["invalid"]),
        "new_urls": new_urls,
        "scrape_queued": scrape_queued,
        "discovery_failed": discovery_failed,
    }


@celery_app.task(name="scraper.tasks.discover_channels")
def discover_channels() -> dict[str, object]:
    """Discover supported channels and put them directly into channels."""
    logger.info("Starting unified channel discovery")
    try:
        result = discover_channels_now(queue_scrapes=True)
        logger.info(
            "Unified discovery complete: inserted=%d refreshed=%d duplicates=%d invalid=%d scrape_queued=%d",
            result["inserted"],
            result["refreshed"],
            result["duplicates"],
            result["invalid"],
            result["scrape_queued"],
        )
        return result
    except (APIError, KeyError, TypeError, ValueError) as exc:
        logger.error("Unified channel discovery failed: %s", exc, exc_info=True)
        return {
            "seed_expansion": {"error": str(exc)},
            "keyword_expansion": {"error": str(exc)},
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 1,
            "new_urls": [],
            "scrape_queued": 0,
            "error": str(exc),
        }
