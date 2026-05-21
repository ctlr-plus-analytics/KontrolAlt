"""Celery task: discover channels via keyword/niche taxonomy search expansion."""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client
from utils.taxonomy import KEYWORD_TAXONOMY

logger = logging.getLogger(__name__)

_SERPER_SEARCH_URL = "https://google.serper.dev/search"
_QUERY_LIMIT = int(os.environ.get("KEYWORD_EXPANSION_QUERY_LIMIT", "480"))
_RESULTS_PER_QUERY = int(os.environ.get("KEYWORD_EXPANSION_RESULTS_PER_QUERY", "20"))
_SERPER_MAX_PAGES_PER_QUERY = int(os.environ.get("KEYWORD_EXPANSION_MAX_PAGES_PER_QUERY", "8"))
_CANDIDATE_STAGE_LIMIT = int(os.environ.get("KEYWORD_EXPANSION_STAGE_LIMIT", "20000"))
_QUERY_STAGNATION_LIMIT = int(os.environ.get("KEYWORD_EXPANSION_QUERY_STAGNATION_LIMIT", "4"))
_GLOBAL_STOP_NO_NEW_STAGED = int(os.environ.get("KEYWORD_EXPANSION_GLOBAL_STOP_NO_NEW_STAGED", "120"))
_DISCOVERY_CONFIDENCE = 0.72
_MAX_FEEDBACK_TERMS = int(os.environ.get("KEYWORD_EXPANSION_MAX_FEEDBACK_TERMS", "36"))
_DISCOVERY_HOLD_SOURCE = "auto_keyword_hold"


def _canonicalize_channel_url(raw_url: str) -> tuple[str | None, str | None]:
    """Canonicalize supported channel URLs and infer platform."""
    normalized = raw_url.strip()
    if normalized and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        normalized = f"https://{normalized}"

    try:
        split = urlsplit(normalized)
    except ValueError:
        return None, None

    host = (split.hostname or "").lower()
    path = re.sub(r"/{2,}", "/", split.path or "/").rstrip("/")
    if not path:
        return None, None

    if "rumble.com" in host:
        # Typical patterns: /c/<slug> or /user/<slug>
        parts = [part for part in path.split("/") if part]
        if len(parts) < 2 or parts[0] not in {"c", "user"}:
            return None, None
        canonical_path = "/" + "/".join(parts[:2])
        return urlunsplit(("https", "rumble.com", canonical_path, "", "")), "rumble"

    if "bitchute.com" in host:
        # Typical pattern: /channel/<slug>
        parts = [part for part in path.split("/") if part]
        if len(parts) < 2 or parts[0] != "channel":
            return None, None
        canonical_path = "/" + "/".join(parts[:2])
        return urlunsplit(("https", "bitchute.com", canonical_path, "", "")), "bitchute"

    return None, None


def _query_for_keyword(keyword: str, platform: str) -> str:
    """Build a Serper query targeting likely channel URLs by platform."""
    if platform == "rumble":
        return f'site:rumble.com ("{keyword}") ("/c/" OR "/user/")'
    return f'site:bitchute.com ("{keyword}") "/channel/"'


def _keyword_templates(category: str, keyword: str) -> list[str]:
    """Return all base query templates for a category/keyword pair."""
    return [
        _query_for_keyword(keyword, "rumble"),
        _query_for_keyword(keyword, "bitchute"),
        f'site:rumble.com inurl:/c/ ("{keyword}" OR "{category}")',
        f'site:rumble.com inurl:/user/ ("{keyword}" OR "{category}")',
        f'site:bitchute.com inurl:/channel/ ("{keyword}" OR "{category}")',
        f'site:rumble.com intitle:"{keyword}" ("/c/" OR "/user/") -"/video/" -"/embed/"',
        f'site:bitchute.com intitle:"{keyword}" "/channel/" -"/video/" -"/embed/"',
    ]


def _iter_search_queries() -> list[tuple[str, str, str]]:
    """Generate bounded queries with fair round-robin niche coverage."""
    queries: list[tuple[str, str, str]] = []

    categories = list(KEYWORD_TAXONOMY.keys())
    keyword_positions: dict[str, int] = {category: 0 for category in categories}
    template_positions: dict[tuple[str, int], int] = {}

    while len(queries) < _QUERY_LIMIT:
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
                next_keyword_pos = keyword_positions[category]
                next_keyword = keywords[next_keyword_pos]
                templates = _keyword_templates(category, next_keyword)
                template_key = (category, next_keyword_pos)
                template_pos = template_positions.get(template_key, 0)

            if template_pos >= len(templates):
                continue

            queries.append((category, keywords[keyword_positions[category]], templates[template_pos]))
            template_positions[template_key] = template_pos + 1
            progressed = True
            if len(queries) >= _QUERY_LIMIT:
                break

        if not progressed:
            break

    return queries


def _search_serper(query: str, page: int = 1) -> list[dict[str, object]]:
    """Run one Serper query and return top organic results."""
    with httpx.Client(timeout=20.0) as http:
        response = http.post(
            _SERPER_SEARCH_URL,
            headers={
                "X-API-KEY": scraper_settings.serp_api_key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": _RESULTS_PER_QUERY, "page": page},
        )
        response.raise_for_status()
        payload = response.json()
        organic = payload.get("organic", []) if isinstance(payload, dict) else []
        if not isinstance(organic, list):
            return []
        return organic[:_RESULTS_PER_QUERY]


def _extract_candidate_links(item: dict[str, object]) -> list[str]:
    """Extract primary and sitelink URLs from one Serper organic item."""
    links: list[str] = []
    primary = str(item.get("link") or "").strip()
    if primary:
        links.append(primary)

    sitelinks = item.get("sitelinks")
    if isinstance(sitelinks, list):
        for sitelink in sitelinks:
            if not isinstance(sitelink, dict):
                continue
            nested_link = str(sitelink.get("link") or "").strip()
            if nested_link:
                links.append(nested_link)
    return links


def _extract_feedback_terms(item: dict[str, object]) -> list[str]:
    """Extract lightweight feedback terms from SERP title/snippet text."""
    blob = f"{item.get('title') or ''} {item.get('snippet') or ''}".lower()
    tokens = re.findall(r"[a-z][a-z0-9_]{3,20}", blob)
    ignore = {
        "rumble",
        "bitchute",
        "channel",
        "video",
        "watch",
        "official",
        "home",
        "about",
    }
    return [t for t in tokens if t not in ignore]


def _feedback_queries(
    *,
    platform: str,
    category: str,
    keyword: str,
    terms: list[str],
) -> list[str]:
    """Build extra high-recall feedback queries from mined terms."""
    if not terms:
        return []
    selected = terms[:_MAX_FEEDBACK_TERMS]
    queries: list[str] = []
    for term in selected:
        if platform == "rumble":
            queries.append(
                f'site:rumble.com ("/c/" OR "/user/") ("{keyword}" OR "{category}") "{term}" -"/video/"'
            )
        else:
            queries.append(
                f'site:bitchute.com "/channel/" ("{keyword}" OR "{category}") "{term}" -"/video/"'
            )
    return queries


def _discover_keyword_expansion_sync() -> dict[str, object]:
    """Discover and directly insert channels from taxonomy-driven search."""
    client = get_supabase_client()
    existing_result = client.table("channels").select("channel_url").execute()
    known_urls: set[str] = set()
    for row in existing_result.data or []:
        canonical, _platform = _canonicalize_channel_url(str(row.get("channel_url") or ""))
        if canonical:
            known_urls.add(canonical)

    discovered = 0
    staged = 0
    already_staged = 0
    duplicates = 0
    invalid = 0
    searched_queries = 0
    staged_by_platform = {"rumble": 0, "bitchute": 0}
    pages_fetched = 0
    raw_links = 0
    no_new_global = 0
    feedback_terms_counter: Counter[str] = Counter()

    seed_queries = _iter_search_queries()
    active_queries: list[tuple[str, str, str]] = list(seed_queries)
    query_idx = 0

    while query_idx < len(active_queries):
        category, keyword, query = active_queries[query_idx]
        query_idx += 1
        if staged >= _CANDIDATE_STAGE_LIMIT:
            break
        searched_queries += 1
        no_new_for_query = 0
        terms_for_query: Counter[str] = Counter()

        for page_num in range(1, _SERPER_MAX_PAGES_PER_QUERY + 1):
            if staged >= _CANDIDATE_STAGE_LIMIT:
                break
            pages_fetched += 1
            new_this_page = 0
            try:
                organic_results = _search_serper(query, page=page_num)
            except (httpx.HTTPError, ValueError) as exc:
                logger.error(
                    "Keyword expansion search failed for query=%s page=%d: %s",
                    query,
                    page_num,
                    exc,
                )
                break

            for item in organic_results:
                title = str(item.get("title") or "").strip()
                terms_for_query.update(_extract_feedback_terms(item))
                feedback_terms_counter.update(_extract_feedback_terms(item))
                links = _extract_candidate_links(item)
                raw_links += len(links)
                for link in links:
                    canonical_url, platform = _canonicalize_channel_url(link)
                    if canonical_url is None or platform is None:
                        invalid += 1
                        continue

                    discovered += 1
                    if canonical_url in known_urls:
                        duplicates += 1
                        continue

                    now_iso = datetime.now(timezone.utc).isoformat()
                    payload = {
                        "platform": platform,
                        "channel_url": canonical_url,
                        "name": title or canonical_url.rstrip("/").split("/")[-1],
                        "description": "",
                        # Hold: hidden from frontend until scrape succeeds.
                        "is_active": False,
                        "discovery_source": _DISCOVERY_HOLD_SOURCE,
                        "discovery_confidence": _DISCOVERY_CONFIDENCE,
                        "discovered_at": now_iso,
                        "updated_at": now_iso,
                    }
                    try:
                        upsert_result = (
                            client.table("channels")
                            .upsert(payload, on_conflict="channel_url")
                            .execute()
                        )
                    except APIError:
                        invalid += 1
                        continue

                    if upsert_result.data:
                        known_urls.add(canonical_url)
                        staged += 1
                        staged_by_platform[platform] += 1
                        new_this_page += 1

            if new_this_page == 0:
                no_new_for_query += 1
            else:
                no_new_for_query = 0

            if no_new_for_query >= _QUERY_STAGNATION_LIMIT:
                break

        if staged >= _CANDIDATE_STAGE_LIMIT:
            break

        if not terms_for_query:
            no_new_global += 1
        else:
            no_new_global = 0

        if query_idx >= len(seed_queries):
            # Append feedback queries after base set has been consumed.
            platform = "rumble" if "site:rumble.com" in query else "bitchute"
            feedback_queries = _feedback_queries(
                platform=platform,
                category=category,
                keyword=keyword,
                terms=[term for term, _count in terms_for_query.most_common(_MAX_FEEDBACK_TERMS)],
            )
            for feedback_query in feedback_queries:
                if len(active_queries) >= _QUERY_LIMIT * 2:
                    break
                active_queries.append((category, keyword, feedback_query))

        if no_new_global >= _GLOBAL_STOP_NO_NEW_STAGED:
            logger.info("Keyword expansion stopping due to global stagnation")
            break

    return {
        "searched_queries": searched_queries,
        "pages_fetched": pages_fetched,
        "raw_links": raw_links,
        "discovered": discovered,
        "staged": staged,
        "already_staged": already_staged,
        "duplicates": duplicates,
        "invalid": invalid,
        "staged_rumble": staged_by_platform["rumble"],
        "staged_bitchute": staged_by_platform["bitchute"],
        "feedback_terms": [term for term, _ in feedback_terms_counter.most_common(10)],
    }


def discover_keyword_expansion_now() -> dict[str, object]:
    """Run keyword expansion synchronously for orchestration hooks."""
    return _discover_keyword_expansion_sync()


@celery_app.task(name="scraper.tasks.discover_keyword_expansion")
def discover_keyword_expansion() -> dict[str, object]:
    """Run taxonomy-driven keyword expansion and directly insert channels."""
    logger.info("Starting keyword/niche search expansion")
    try:
        result = _discover_keyword_expansion_sync()
        logger.info(
            "Keyword expansion complete: queries=%d pages=%d discovered=%d staged=%d duplicates=%d invalid=%d",
            result["searched_queries"],
            result["pages_fetched"],
            result["discovered"],
            result["staged"],
            result["duplicates"],
            result["invalid"],
        )
        return result
    except (APIError, KeyError, TypeError, ValueError) as exc:
        logger.error("Keyword expansion failed: %s", exc, exc_info=True)
        return {
            "searched_queries": 0,
            "pages_fetched": 0,
            "raw_links": 0,
            "discovered": 0,
            "staged": 0,
            "already_staged": 0,
            "duplicates": 0,
            "invalid": 1,
            "staged_rumble": 0,
            "staged_bitchute": 0,
            "feedback_terms": [],
            "error": str(exc),
        }
