"""Unified, lenient channel discovery directly into the channels table."""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone

import httpx
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client
from core.runtime_settings import get_runtime_settings
from tasks.scrape_rumble import scrape_rumble_channel
from tasks.scrape_substack import scrape_substack_channel
from tasks.task_queues import QUEUE_RUMBLE, QUEUE_SUBSTACK
from utils.ai_response import extract_json_object, extract_response_text
from utils.channel_urls import (
    ChannelUrlCandidate,
    canonicalize_channel_url,
    extract_supported_channel_urls,
)
from utils.runtime_taxonomy import get_runtime_keyword_taxonomy

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
_PROGRESS_QUERIES_EVERY = 10
_PROGRESS_PAGES_EVERY = 25
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
_SUBSTACK_HANDLE_PATTERN = re.compile(
    r"\b([A-Za-z0-9][A-Za-z0-9_-]{1,127})\.substack\.com\b",
    re.IGNORECASE,
)
_SUPPORTED_DISCOVERY_PLATFORMS = {"rumble", "substack"}

# Query quality tracking (Redis)
_QSTAT_KEY_PREFIX = "discovery:qstat:"
_QSTAT_TTL_SECONDS = 30 * 24 * 3600

# Pre-classification filter
_PRE_CLASSIFY_BATCH_SIZE = 10
_PRE_CLASSIFY_MAX_CHANNELS = 200
_PRE_CLASSIFY_FILTER_CONFIDENCE = 0.75
_PRE_CLASSIFY_MODEL = "gemini-2.5-flash"

_TARGET_NICHES = frozenset({
    "Prepper / Survival",
    "Financial / Macro",
    "Conservative Politics",
    "Health / Wellness",
    "Homesteading",
    "Crypto / Alternative Assets",
    "Religious / Values-Based",
    "News / Commentary",
})

_NICHE_LIST_STR = (
    "Prepper/Survival, Financial/Macro, Conservative Politics, Health/Wellness, "
    "Homesteading, Crypto/Alternative Assets, Religious/Values-Based, News/Commentary"
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
    quality_tier: str | None = None,
    serp_title: str | None = None,
    serp_snippet: str | None = None,
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
        if quality_tier and not existing.get("discovery_quality_tier"):
            payload["discovery_quality_tier"] = quality_tier
        if serp_title and not existing.get("discovery_serp_title"):
            payload["discovery_serp_title"] = serp_title[:200]
        if serp_snippet and not existing.get("discovery_serp_snippet"):
            payload["discovery_serp_snippet"] = serp_snippet[:500]

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
    if quality_tier:
        payload["discovery_quality_tier"] = quality_tier
    if serp_title:
        payload["discovery_serp_title"] = serp_title[:200]
    if serp_snippet:
        payload["discovery_serp_snippet"] = serp_snippet[:500]

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
    elif source_platform == "substack":
        for match in _SUBSTACK_HANDLE_PATTERN.finditer(text):
            handle = match.group(1)
            for url in (f"https://substack.com/@{handle}", f"https://{handle}.substack.com"):
                candidate = canonicalize_channel_url(url)
                if candidate is not None:
                    candidates[candidate.channel_url] = candidate
    return list(candidates.values())


def _seed_discovery_confidence(source_field: str, source_quality_tier: str = "low") -> float:
    """Score seed evidence by source field type plus a boost for high-quality seed channels."""
    if source_field in {"contact_info", "secondary_urls"}:
        base = 0.97
    elif source_field == "description":
        base = 0.92
    elif source_field == "video_titles":
        base = 0.84
    else:
        base = 0.90
    tier_boost = {"high": 0.03, "medium": 0.01, "low": 0.0}.get(source_quality_tier, 0.0)
    return min(1.0, base + tier_boost)


def _seed_quality_tier(channel: dict[str, object]) -> str:
    """Derive a quality tier for a seed channel based on its engagement and Gate 0 status."""
    gate0 = channel.get("gate0_status")
    comment_tier = channel.get("comment_tier")
    if gate0 == "clean" and comment_tier in {"whale", "sweet_spot"}:
        return "high"
    if gate0 == "clean" or comment_tier in {"whale", "sweet_spot", "active"}:
        return "medium"
    return "low"


def _score_serp_item_quality(
    item: dict[str, object], position: int
) -> tuple[str, float]:
    """Score a SERP result item for channel quality signal strength.

    Returns (tier, score) where tier is 'high', 'medium', or 'low'.
    """
    score = 0.0

    # SERP position — earlier is stronger signal.
    if position <= 3:
        score += 0.15
    elif position <= 6:
        score += 0.05

    # Subscriber/follower count mention in snippet or title.
    text = f"{item.get('title') or ''} {item.get('snippet') or ''}".lower()
    count_match = re.search(
        r"(\d[\d,.]*)\s*([kKmM])?\s*(subscribers?|followers?|members?)", text
    )
    if count_match:
        raw = count_match.group(1).replace(",", "")
        try:
            n = float(raw)
            multiplier = {"k": 1_000, "m": 1_000_000}.get(
                (count_match.group(2) or "").lower(), 1
            )
            count = n * multiplier
            if count >= 100_000:
                score += 0.30
            elif count >= 10_000:
                score += 0.20
            elif count >= 1_000:
                score += 0.10
        except ValueError:
            pass

    # Direct SERP link signal: presence of a raw URL in the link field.
    if item.get("link"):
        score += 0.10

    # Keyword density in snippet.
    snippet_lower = (item.get("snippet") or "").lower()
    from utils.runtime_taxonomy import get_runtime_keyword_taxonomy
    taxonomy = get_runtime_keyword_taxonomy()
    for keywords in taxonomy.values():
        for kw in keywords[:5]:
            if kw in snippet_lower:
                score += 0.10
                break

    # Recency signal from date field.
    date_str = str(item.get("date") or "")
    if date_str and any(yr in date_str for yr in ["2024", "2025", "2026"]):
        score += 0.05

    if score >= 0.40:
        return "high", score
    if score >= 0.15:
        return "medium", score
    return "low", score


def _record_query_stat(category: str, platform: str, field: str, amount: int = 1) -> None:
    """Increment a Redis counter for query quality tracking."""
    if not category or not platform:
        return
    try:
        from tasks.scrape_helpers import _redis_client
        client = _redis_client()
        key = f"{_QSTAT_KEY_PREFIX}{category}:{platform}"
        client.hincrby(key, field, amount)
        client.expire(key, _QSTAT_TTL_SECONDS)
    except Exception as exc:
        logger.debug("Failed to record query stat: %s", exc)


def _get_category_quality_scores() -> dict[str, float]:
    """Return historical quality score (classified_known / fired) per category."""
    try:
        from tasks.scrape_helpers import _redis_client
        client = _redis_client()
        scores: dict[str, float] = {}
        for key in client.scan_iter(f"{_QSTAT_KEY_PREFIX}*"):
            key_str = key.decode() if isinstance(key, bytes) else key
            suffix = key_str[len(_QSTAT_KEY_PREFIX):]
            parts = suffix.split(":")
            if len(parts) < 2:
                continue
            category = parts[0]
            data = client.hgetall(key)
            fired = int(data.get(b"fired", 0) or data.get("fired", 0) or 0)
            classified = int(
                data.get(b"classified_known", 0) or data.get("classified_known", 0) or 0
            )
            if fired > 0:
                scores[category] = max(scores.get(category, 0.0), classified / fired)
        return scores
    except Exception:
        return {}


def _build_pre_classify_prompt(batch: list[dict[str, object]]) -> str:
    lines = [
        f"NICHES: {_NICHE_LIST_STR}\n",
        "For each channel, decide if it fits any target niche.",
        'Respond with JSON: {"results": [{"id": 0, "on_topic": true, '
        '"niches": ["Niche Name"], "confidence": 0.9}, ...]}\n',
        "CHANNELS:",
    ]
    for i, entry in enumerate(batch):
        title = str(entry.get("serp_title") or "").strip()
        snippet = str(entry.get("serp_snippet") or "")[:300].strip()
        url = str(entry.get("channel_url") or "")
        category = str(entry.get("discovery_category") or "")
        lines.append(f"{i}. URL: {url}")
        if title:
            lines.append(f"   Title: {title}")
        if snippet:
            lines.append(f"   Snippet: {snippet}")
        if category:
            lines.append(f"   Search niche: {category}")
    return "\n".join(lines)


def _parse_pre_classify_response(
    raw_text: str | None,
    batch: list[dict[str, object]],
) -> list[dict[str, object]]:
    data = extract_json_object(raw_text)
    if data is None:
        if raw_text:
            logger.warning(
                "JSON parse failure in AI pre-classification response: %.200s",
                raw_text,
            )
        return []
    items = data.get("results")
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("id")
        if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
            continue
        channel_url = str(batch[idx].get("channel_url") or "")
        raw_niches = item.get("niches")
        niches = (
            [n for n in raw_niches if isinstance(n, str) and n in _TARGET_NICHES]
            if isinstance(raw_niches, list)
            else []
        )
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        out.append({
            "channel_url": channel_url,
            "on_topic": bool(item.get("on_topic", True)),
            "niches": niches,
            "confidence": confidence,
        })
    return out

def _pre_classify_new_urls(
    new_urls: list[dict[str, object]],
    api_key: str,
) -> list[dict[str, object]]:
    """Batch-classify newly discovered channels using SERP data via Google AI.

    Writes discovery_niche_hint to DB. Removes channels from the scrape queue
    when Google AI is confident they are off-topic. High-quality-tier channels skip
    classification (already strong signal). Falls back gracefully on any error.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.debug("google-genai package not installed; skipping pre-classification")
        return new_urls

    # Only classify ambiguous keyword-discovered channels that have SERP text.
    candidates = [
        u for u in new_urls
        if u.get("quality_tier") != "high" and (u.get("serp_title") or u.get("serp_snippet"))
    ][:_PRE_CLASSIFY_MAX_CHANNELS]

    if not candidates:
        return new_urls

    _PRE_CLASSIFY_SYSTEM = (
        "You evaluate whether alternative media channel links target "
        "specific research niches. Respond with valid JSON only."
    )
    ai_client = genai.Client(api_key=api_key)
    supabase = get_supabase_client()
    hint_map: dict[str, list[str]] = {}
    off_topic: set[str] = set()
    now = _utc_now_iso()

    for batch_start in range(0, len(candidates), _PRE_CLASSIFY_BATCH_SIZE):
        batch = candidates[batch_start: batch_start + _PRE_CLASSIFY_BATCH_SIZE]
        prompt = _build_pre_classify_prompt(batch)
        try:
            response = ai_client.models.generate_content(
                model=_PRE_CLASSIFY_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_PRE_CLASSIFY_SYSTEM,
                    response_mime_type="application/json",
                    max_output_tokens=800,
                    temperature=0.0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            results = _parse_pre_classify_response(
                extract_response_text(response), batch
            )
        except Exception as exc:
            logger.warning("Pre-classification batch failed: %s", exc)
            results = []

        for res in results:
            url = str(res.get("channel_url") or "")
            niches = res.get("niches") or []
            on_topic = bool(res.get("on_topic", True))
            confidence = float(res.get("confidence") or 0.0)
            hint_map[url] = niches if niches else ["Unknown / Needs Review"]

            if not on_topic and confidence >= _PRE_CLASSIFY_FILTER_CONFIDENCE:
                off_topic.add(url)

            if url:
                try:
                    supabase.table("channels").update({
                        "discovery_niche_hint": hint_map[url],
                        "updated_at": now,
                    }).eq("channel_url", url).execute()
                except Exception as exc:
                    logger.debug("Failed to write niche hint for %s: %s", url, exc)

        time.sleep(0.10)

    filtered = 0
    result: list[dict[str, object]] = []
    for entry in new_urls:
        channel_url = str(entry.get("channel_url") or "")
        if channel_url in hint_map:
            entry = {**entry, "discovery_niche_hint": hint_map[channel_url]}
        if channel_url in off_topic:
            filtered += 1
            continue
        result.append(entry)

    if filtered:
        logger.info(
            "Pre-classification filtered %d off-topic channels from scrape queue", filtered
        )
    return result


def _normalize_platform_filter(platform: str | None) -> set[str]:
    """Normalize single platform filter to an allowed set."""
    if platform is None:
        return set(_SUPPORTED_DISCOVERY_PLATFORMS)
    normalized = platform.strip().lower()
    if normalized not in _SUPPORTED_DISCOVERY_PLATFORMS:
        raise ValueError(
            f"Unsupported platform '{platform}'. Expected one of: "
            + ", ".join(sorted(_SUPPORTED_DISCOVERY_PLATFORMS))
        )
    return {normalized}


def _query_for_keyword(keyword: str, platform: str) -> str:
    if platform == "rumble":
        return f'site:rumble.com "{keyword}" (inurl:/c/ OR inurl:/user/) -inurl:/v -inurl:/embed/'
    if platform == "substack":
        return f'site:substack.com "{keyword}" (inurl:/@ OR inurl:.substack.com) -inurl:/p/'
    raise ValueError(f"Unsupported platform for keyword query: {platform}")


def _category_phrase(category: str) -> str:
    return category.replace("_", " ")


def _keyword_templates(
    category: str, keyword: str, platforms: set[str] | None = None
) -> list[str]:
    if platforms is None:
        platforms = set(_SUPPORTED_DISCOVERY_PLATFORMS)
    category_phrase = _category_phrase(category)
    templates: list[str] = []

    if "rumble" in platforms:
        templates.extend(
            [
                _query_for_keyword(keyword, "rumble"),
                f'site:rumble.com/c/ "{keyword}" -inurl:/v -inurl:/embed/',
                f'site:rumble.com/user/ "{keyword}" -inurl:/v -inurl:/embed/',
                f'site:rumble.com "{keyword}" "{category_phrase}" -inurl:/v -inurl:/embed/',
                f'site:rumble.com intitle:"{keyword}" -inurl:/v -inurl:/embed/',
                f'"{keyword}" "rumble.com/c/" -inurl:/v -inurl:/embed/',
                f'"{keyword}" "rumble.com/user/" -inurl:/v -inurl:/embed/',
                f'"{keyword}" "Rumble channel"',
            ]
        )
    if "substack" in platforms:
        templates.extend(
            [
                _query_for_keyword(keyword, "substack"),
                f'"{keyword}" "Substack"',
            ]
        )
    return list(dict.fromkeys(templates))


def _iter_search_queries(
    platforms: set[str], keyword_taxonomy: dict[str, list[str]]
) -> list[tuple[str, str, str, str]]:
    queries: list[tuple[str, str, str, str]] = []
    categories = list(keyword_taxonomy.keys())
    # Prioritise categories with historically higher classification success rates.
    quality_scores = _get_category_quality_scores()
    categories.sort(key=lambda cat: quality_scores.get(cat, 0.0), reverse=True)
    keyword_positions: dict[str, int] = {category: 0 for category in categories}
    template_positions: dict[tuple[str, int], int] = {}

    query_limit = min(
        get_runtime_settings().discovery_serper_query_limit, _QUERY_LIMIT
    )
    while len(queries) < query_limit:
        progressed = False
        for category in categories:
            keywords = keyword_taxonomy.get(category, [])
            if not keywords:
                continue

            keyword_pos = keyword_positions[category] % len(keywords)
            keyword = keywords[keyword_pos]
            templates = _keyword_templates(category, keyword, platforms)
            template_key = (category, keyword_pos)
            template_pos = template_positions.get(template_key, 0)

            if template_pos >= len(templates):
                keyword_positions[category] = (keyword_pos + 1) % len(keywords)
                keyword_pos = keyword_positions[category]
                keyword = keywords[keyword_pos]
                templates = _keyword_templates(category, keyword, platforms)
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
    categories: list[str],
) -> None:
    """Append one feedback query per category per pass to preserve niche fairness."""
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
    if '"rumble channel"' in query_lower:
        confidence = min(confidence, 0.58)
    if "rumble.com/c/" in query_lower or "rumble.com/user/" in query_lower:
        confidence = max(confidence, 0.78)
    if _candidate_was_direct_serp_link(item, candidate):
        confidence = max(confidence, 0.82)

    return round(confidence, 2)


def _extract_feedback_terms(item: dict[str, object]) -> list[str]:
    blob = f"{item.get('title') or ''} {item.get('snippet') or ''}".lower()
    tokens = re.findall(r"[a-z][a-z0-9_]{3,20}", blob)
    ignore = {
        "about",
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
        elif platform == "substack":
            queries.append(
                f'site:substack.com "{keyword}" "{category}" "{term}" (inurl:/@ OR inurl:.substack.com) -inurl:/p/'
            )
        else:
            continue
    return queries


def _discover_from_known_channels(client, *, platform: str | None = None) -> dict[str, object]:
    allowed_platforms = _normalize_platform_filter(platform)
    insert_limit = min(get_runtime_settings().discovery_insert_limit, _INSERT_LIMIT)
    columns = (
        "id,channel_url,name,description,video_titles,contact_info,secondary_urls,"
        "gate0_status,comment_tier,niche_tags"
    )

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
    platform_metrics = {"rumble": 0, "substack": 0}
    inserted_platform_metrics = {"rumble": 0, "substack": 0}

    source_channels = 0
    for channel in _iter_channel_rows(client, columns):
        source_channels += 1
        # Do not expand from dirty channels — they may contaminate the seed set.
        if channel.get("gate0_status") == "dirty":
            continue
        source_channel_id = str(channel.get("id") or "")
        source_channel_url = str(channel.get("channel_url") or "")
        seed_tier = _seed_quality_tier(channel)
        for candidate, source_field in _collect_known_channel_candidates(channel):
            if candidate.platform not in allowed_platforms:
                continue
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
                confidence = _seed_discovery_confidence(source_field, seed_tier)
                changed, existed = upsert_discovered_channel(
                    client=client,
                    candidate=candidate,
                    source="auto_seed",
                    source_ref=source_channel_id or None,
                    title=_fallback_name(candidate.channel_url),
                    category=None,
                    confidence=confidence,
                    quality_tier=seed_tier,
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


def _discover_from_keywords(
    client,
    *,
    platform: str | None = None,
) -> dict[str, object]:
    allowed_platforms = _normalize_platform_filter(platform)
    keyword_taxonomy = get_runtime_keyword_taxonomy()
    categories = list(keyword_taxonomy.keys())
    if not categories:
        return {
            "searched_queries": 0,
            "pages_fetched": 0,
            "raw_links": 0,
            "discovered": 0,
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 0,
            "inserted_rumble": 0,
            "inserted_substack": 0,
            "category_metrics": {},
            "feedback_terms": [],
            "new_urls": [],
        }
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
    progress_queries_every = max(
        1,
        int(getattr(scraper_settings, "discovery_progress_queries_every", _PROGRESS_QUERIES_EVERY)),
    )
    progress_pages_every = max(
        1,
        int(getattr(scraper_settings, "discovery_progress_pages_every", _PROGRESS_PAGES_EVERY)),
    )
    discovered = 0
    inserted = 0
    refreshed = 0
    duplicates = 0
    invalid = 0
    searched_queries = 0
    pages_fetched = 0
    raw_links = 0
    no_new_global = 0
    inserted_by_platform = {"rumble": 0, "substack": 0}
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
        for category in categories
    }
    feedback_terms_counter: Counter[str] = Counter()
    new_urls: list[dict[str, str]] = []

    seed_queries = _iter_search_queries(allowed_platforms, keyword_taxonomy)
    active_queries: list[tuple[str, str, str, str]] = list(seed_queries)
    feedback_by_category: dict[str, list[tuple[str, str, str, str]]] = {
        category: [] for category in categories
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
        if searched_queries % progress_queries_every == 0:
            logger.info(
                "Keyword discovery progress: queries=%d pages=%d inserted=%d refreshed=%d invalid=%d target=%d platform=%s",
                searched_queries,
                pages_fetched,
                inserted,
                refreshed,
                invalid,
                insert_limit,
                platform or "all",
            )
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
        # Record query fired for quality feedback loop.
        _stat_platform = "rumble" if "site:rumble.com" in query else "substack"
        _record_query_stat(category, _stat_platform, "fired")
        no_new_for_query = 0
        no_new_for_active_query = True
        terms_for_query: Counter[str] = Counter()

        for page_num in range(1, max_pages_per_query + 1):
            if inserted >= insert_limit:
                break
            pages_fetched += 1
            if pages_fetched % progress_pages_every == 0:
                logger.info(
                    "Keyword discovery page progress: query=%d page=%d total_pages=%d inserted=%d refreshed=%d invalid=%d",
                    searched_queries,
                    page_num,
                    pages_fetched,
                    inserted,
                    refreshed,
                    invalid,
                )
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
                serp_position = int(item.get("position") or 99)
                serp_snippet = str(item.get("snippet") or "")[:500]
                item_quality_tier, _item_score = _score_serp_item_quality(
                    item, serp_position
                )
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
                            quality_tier=item_quality_tier,
                            serp_title=title[:200] if title else None,
                            serp_snippet=serp_snippet or None,
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
                        _record_query_stat(category, candidate.platform, "inserted")
                        new_urls.append(
                            {
                                "channel_url": candidate.channel_url,
                                "platform": candidate.platform,
                                "confidence": confidence,
                                "quality_tier": item_quality_tier,
                                "serp_title": title[:200] if title else None,
                                "serp_snippet": serp_snippet or None,
                                "discovery_category": category,
                            }
                        )

            if new_this_page == 0:
                no_new_for_query += 1
            else:
                no_new_for_query = 0
            if no_new_for_query >= query_stagnation_limit:
                break

        if "site:rumble.com" in query:
            platform = "rumble"
        elif "site:substack.com" in query:
            platform = "substack"
        else:
            platform = "substack"
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
                categories=categories,
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
        "inserted_substack": inserted_by_platform["substack"],
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
    def _scrape_priority(row: dict[str, object]) -> float:
        tier_map = {"high": 1.0, "medium": 0.6, "low": 0.2}
        tier = tier_map.get(str(row.get("quality_tier") or ""), 0.3)
        conf = float(row.get("confidence") or 0.0)
        hint = row.get("discovery_niche_hint")
        niche_signal = (
            1.0
            if isinstance(hint, list) and hint and hint != ["Unknown / Needs Review"]
            else 0.0
        )
        return (tier * 0.4) + (conf * 0.4) + (niche_signal * 0.2)

    seen: set[str] = set()
    client = get_supabase_client()
    priority_rows = sorted(new_urls, key=_scrape_priority, reverse=True)
    for row in priority_rows:
        if queued >= scrape_new_limit:
            break
        channel_url = str(row.get("channel_url") or "")
        platform = str(row.get("platform") or "")
        if not channel_url or channel_url in seen:
            continue
        seen.add(channel_url)
        if platform == "rumble":
            scrape_rumble_channel.apply_async(
                args=[channel_url],
                queue=QUEUE_RUMBLE,
            )
            queued += 1
        elif platform == "substack":
            scrape_substack_channel.apply_async(
                args=[channel_url],
                queue=QUEUE_SUBSTACK,
            )
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


def discover_channels_now(
    *,
    queue_scrapes: bool = False,
    mode: str = "all",
    platform: str | None = None,
) -> dict[str, object]:
    """Run all automatic discovery sources and insert channels directly."""
    normalized_mode = (mode or "all").strip().lower()
    if normalized_mode not in {"all", "seed", "keyword"}:
        raise ValueError("Unsupported mode. Expected one of: all, seed, keyword")

    client = get_supabase_client()
    discovery_failed = False
    if normalized_mode in {"all", "seed"}:
        try:
            seed_result = _discover_from_known_channels(client, platform=platform)
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
    else:
        seed_result = {
            "source_channels": 0,
            "discovered": 0,
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 0,
            "self_links": 0,
            "field_metrics": {},
            "self_link_field_metrics": {},
            "platform_metrics": {},
            "inserted_platform_metrics": {},
            "new_urls": [],
        }

    if normalized_mode in {"all", "keyword"}:
        try:
            keyword_result = _discover_from_keywords(client, platform=platform)
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
                "inserted_substack": 0,
                "category_metrics": {},
                "feedback_terms": [],
                "new_urls": [],
                "error": str(exc),
            }
    else:
        keyword_result = {
            "searched_queries": 0,
            "pages_fetched": 0,
            "raw_links": 0,
            "discovered": 0,
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 0,
            "inserted_rumble": 0,
            "inserted_substack": 0,
            "category_metrics": {},
            "feedback_terms": [],
            "new_urls": [],
        }

    new_urls = [
        *(seed_result.get("new_urls") or []),
        *(keyword_result.get("new_urls") or []),
    ]

    api_key = scraper_settings.google_api_key
    if new_urls and api_key:
        new_urls = _pre_classify_new_urls(new_urls, api_key)

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


@celery_app.task(name="scraper.tasks.discover_channels", queue="discovery")
def discover_channels(
    mode: str = "all",
    platform: str | None = None,
    queue_scrapes: bool = True,
) -> dict[str, object]:
    """Discover supported channels and put them directly into channels."""
    logger.info("Starting unified channel discovery")
    try:
        result = discover_channels_now(
            queue_scrapes=queue_scrapes,
            mode=mode,
            platform=platform,
        )
        logger.info(
            "Unified discovery complete: inserted=%d refreshed=%d duplicates=%d invalid=%d scrape_queued=%d",
            result["inserted"],
            result["refreshed"],
            result["duplicates"],
            result["invalid"],
            result["scrape_queued"],
        )
        return result
    except Exception as exc:
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
