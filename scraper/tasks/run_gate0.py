"""Celery task: run Gate 0 compliance check for a channel."""

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from celery import Task
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client
from core.runtime_settings import Gate0CompetitorSetting, get_runtime_settings
from models import Gate0TaskResult

logger = logging.getLogger(__name__)

_SERPER_SEARCH_URL = "https://google.serper.dev/search"
_SERPER_QUOTA_STATUS_CODES = {402, 429}
_URLISH_PATTERN = re.compile(
    r"https?://[^\s<>\"{}|\\^`\[\]]+|(?<!@)\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>\"{}|\\^`\[\]]*)?",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = ".,;:!?)\"]}'"


def _load_competitors() -> tuple[Gate0CompetitorSetting, ...]:
    """Read Gate 0 competitors from system_settings. Returns empty tuple on failure."""
    try:
        client = get_supabase_client()
        result = (
            client.table("system_settings")
            .select("gate0_competitors")
            .eq("singleton_key", "global")
            .single()
            .execute()
        )
        raw = (result.data or {}).get("gate0_competitors")
        if isinstance(raw, list):
            return tuple(
                Gate0CompetitorSetting(
                    str(item["brand"]),
                    tuple(str(d) for d in (item.get("domains") or [])),
                )
                for item in raw
                if isinstance(item, dict) and item.get("brand")
            )
    except Exception:
        logger.warning("Failed to load gate0 competitors from DB", exc_info=True)
    return ()


def _parse_datetime(value: object) -> datetime | None:
    """Parse a Supabase timestamp into an aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _should_run_gate0_check(
    channel: dict[str, object],
    manual: bool = False,
    clean_recheck_days: int = 7,
) -> tuple[bool, str | None]:
    """Return whether a Gate 0 task should consume search quota."""
    if manual:
        return True, None

    status = channel.get("gate0_status")
    if status == "dirty":
        return False, "dirty channels are not rechecked automatically"

    if status == "clean":
        checked_at = _parse_datetime(channel.get("gate0_checked_at"))
        if checked_at is not None:
            age = datetime.now(timezone.utc) - checked_at
            if age < timedelta(days=clean_recheck_days):
                return (
                    False,
                    f"clean channel checked within the last {clean_recheck_days} days",
                )

    return True, None


def _iter_scan_values(channel: dict[str, object]) -> list[str]:
    """Return stored fields that Gate 0 local scan should inspect."""
    contact_info = channel.get("contact_info", []) or []
    secondary_urls = channel.get("secondary_urls", []) or []
    video_titles = channel.get("video_titles", []) or []
    description = str(channel.get("description") or "")
    name = str(channel.get("name") or "")
    channel_url = str(channel.get("channel_url") or "")

    if isinstance(contact_info, str):
        contact_values = [contact_info]
    else:
        contact_values = [str(value) for value in contact_info]

    if isinstance(secondary_urls, str):
        secondary_values = [secondary_urls]
    else:
        secondary_values = [str(value) for value in secondary_urls]

    if isinstance(video_titles, str):
        title_values = [video_titles]
    else:
        title_values = [str(t) for t in video_titles if t]

    values = [*contact_values, *secondary_values]
    values.append(description)
    if name:
        values.append(name)
    if channel_url:
        values.append(channel_url)
    values.extend(title_values)
    return values


def _extract_channel_handle(channel_url: str) -> str | None:
    """Extract a short searchable handle from a channel URL."""
    m = re.search(r"rumble\.com/(?:c|user)/([^/?#]+)", channel_url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"substack\.com/@([^/?#]+)", channel_url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b([a-z0-9-]+)\.substack\.com", channel_url, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _scan_channel_text_for_competitors(
    channel: dict[str, object],
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> tuple[str | None, str | None]:
    """Scan stored channel text and URLs for competitor references."""
    channel_url = str(channel.get("channel_url") or "")

    for text in _iter_scan_values(channel):
        text_lower = text.lower()
        source_url = (
            text
            if text_lower.startswith(("http://", "https://"))
            else channel_url
        )

        match, matched_source_url = _scan_text_for_competitors(
            text,
            competitors,
            source_url,
        )
        if match is not None:
            return match, matched_source_url

    return None, None


def _contains_domain(text_lower: str, domain: str) -> bool:
    """Match a hostname or subdomain without matching unrelated longer words."""
    pattern = rf"(?<![a-z0-9-]){re.escape(domain.lower())}(?![a-z0-9-])"
    return re.search(pattern, text_lower) is not None


def _contains_brand(text_lower: str, brand: str) -> bool:
    """Match brand phrases on word boundaries."""
    pattern = rf"(?<![a-z0-9]){re.escape(brand.lower())}(?![a-z0-9])"
    return re.search(pattern, text_lower) is not None


def _normalize_evidence_url(raw_url: str) -> str:
    cleaned = raw_url.strip().strip(_TRAILING_PUNCTUATION)
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


def _source_url_for_domain(text: str, fallback_url: str | None, domain: str) -> str:
    """Return the most specific URL containing the matched competitor domain."""
    if fallback_url and _contains_domain(fallback_url.lower(), domain):
        return fallback_url

    for candidate in _URLISH_PATTERN.findall(text):
        normalized = _normalize_evidence_url(candidate)
        if _contains_domain(normalized.lower(), domain):
            return normalized

    return f"https://{domain}"


def _scan_text_for_competitors(
    text: str,
    competitors: tuple[Gate0CompetitorSetting, ...],
    source_url: str | None,
) -> tuple[str | None, str | None]:
    """Return the first competitor reference in a text blob."""
    text_lower = text.lower()
    for competitor in competitors:
        for domain in competitor.domains:
            if _contains_domain(text_lower, domain):
                return domain, _source_url_for_domain(text, source_url, domain)

        if _contains_brand(text_lower, competitor.brand):
            return competitor.brand, None

    return None, None


def _scan_serper_results(
    organic_results: object,
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> tuple[str | None, str | None]:
    """Scan top Serper organic results for competitor brands/domains."""
    if not isinstance(organic_results, list):
        return None, None

    for item in organic_results[:20]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        link = str(item.get("link") or "")
        match, source_url = _scan_text_for_competitors(
            f"{title} {snippet} {link}",
            competitors,
            link,
        )
        if match is not None:
            return match, source_url

    return None, None


def _run_serper_search(
    search_query: str,
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> tuple[str | None, str | None]:
    """Run the Serper portion of Gate 0 and return any competitor hit."""
    with httpx.Client(timeout=15.0) as http:
        response = http.post(
            _SERPER_SEARCH_URL,
            headers={
                "X-API-KEY": scraper_settings.serp_api_key,
                "Content-Type": "application/json",
            },
            json={
                "q": search_query,
                "num": 20,
            },
        )
        if response.status_code in _SERPER_QUOTA_STATUS_CODES:
            raise RuntimeError("Serper quota exceeded for today")

        response.raise_for_status()
        data = response.json()
        organic_results = data.get("organic", []) if isinstance(data, dict) else []
        return _scan_serper_results(organic_results, competitors)


def _build_search_queries(
    channel_name: str,
    channel_handle: str | None,
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> list[str]:
    """Return ordered Serper queries for Gate 0, most general first.

    Queries are tried with early-exit on the first hit, so per-competitor and
    affiliate queries only fire when the broad search finds nothing.
    """
    handle_differs = bool(
        channel_handle and channel_handle.lower() != channel_name.lower()
    )
    queries: list[str] = []

    queries.append(f'"{channel_name}" "gold IRA"')
    if handle_differs:
        queries.append(f'"{channel_handle}" "gold IRA"')

    for competitor in competitors:
        queries.append(f'"{channel_name}" "{competitor.brand}"')
        if handle_differs:
            queries.append(f'"{channel_handle}" "{competitor.brand}"')

    for competitor in competitors:
        for domain in competitor.domains[:2]:
            queries.append(f'site:{domain} "{channel_name}"')
            if handle_differs:
                queries.append(f'site:{domain} "{channel_handle}"')

    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def _run_serper_search_multi(
    queries: list[str],
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> tuple[str | None, str | None, str]:
    """Run Serper queries in order, stopping at the first competitor hit.

    Returns (flagged_brand, source_url, winning_query). winning_query is the
    first query when no hit is found.
    """
    first_query = queries[0] if queries else ""
    for query in queries:
        brand, url = _run_serper_search(query, competitors)
        if brand is not None:
            return brand, url, query
    return None, None, first_query


def _persist_gate0_result(
    channel: dict[str, object],
    search_query: str,
    flagged_brand: str | None,
    source_url: str | None,
) -> dict[str, object]:
    """Insert a Gate 0 result and update channel status."""
    client = get_supabase_client()
    channel_id = str(channel["id"])
    result_status = "dirty" if flagged_brand else "clean"
    now = datetime.now(timezone.utc).isoformat()

    gate0_record = {
        "channel_id": channel_id,
        "checked_at": now,
        "search_query": search_query,
        "result_status": result_status,
        "flagged_brand": flagged_brand,
        "source_url": source_url,
    }
    insert_res = client.table("gate0_results").insert(gate0_record).execute()
    gate0_id = None
    if insert_res.data:
        gate0_id = insert_res.data[0].get("id")

    client.table("channels").update(
        {
            "gate0_status": result_status,
            "gate0_checked_at": now,
            "gate0_result_id": gate0_id,
            "gate0_search_query": search_query,
            "gate0_result_status": result_status,
            "gate0_flagged_brand": flagged_brand,
            "gate0_source_url": source_url,
            "updated_at": now,
        }
    ).eq("id", channel_id).execute()

    logger.info(
        "Gate 0 complete for %s: %s (brand=%s)",
        channel_id,
        result_status,
        flagged_brand,
    )
    return gate0_record


def _mark_gate0_unchecked(channel_id: str, reason: str) -> None:
    """Clear a stuck pending status so the channel can be retried later."""
    now = datetime.now(timezone.utc).isoformat()
    get_supabase_client().table("channels").update(
        {
            "gate0_status": "unchecked",
            "updated_at": now,
        }
    ).eq("id", channel_id).execute()
    logger.warning("Gate 0 marked unchecked for %s: %s", channel_id, reason)


def _run_gate0_sync(
    channel_id: str,
    manual: bool = False,
) -> dict[str, object]:
    """Synchronous Gate 0 check implementation."""
    runtime = get_runtime_settings()
    if not runtime.settings_loaded:
        _mark_gate0_unchecked(channel_id, "runtime settings unavailable")
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason="runtime_settings_unavailable",
        ).model_dump(mode="json")

    if not runtime.gate0_enabled:
        _mark_gate0_unchecked(channel_id, "gate0 disabled")
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason="gate0_disabled",
        ).model_dump(mode="json")

    client = get_supabase_client()
    ch_result = (
        client.table("channels")
        .select("*")
        .eq("id", channel_id)
        .maybe_single()
        .execute()
    )
    if ch_result.data is None:
        raise ValueError(f"Channel {channel_id} not found")

    channel = ch_result.data
    should_run, skip_reason = _should_run_gate0_check(
        channel,
        manual=manual,
        clean_recheck_days=runtime.gate0_clean_recheck_days,
    )
    if not should_run:
        logger.info("Gate 0 skipped for %s: %s", channel_id, skip_reason)
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason=skip_reason,
        ).model_dump(mode="json")

    channel_name = str(channel.get("name") or "")
    channel_url_str = str(channel.get("channel_url") or "")
    channel_handle = _extract_channel_handle(channel_url_str)
    competitors = _load_competitors()
    if not competitors:
        _mark_gate0_unchecked(channel_id, "no gate0 competitors configured")
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason="no_gate0_competitors_configured",
        ).model_dump(mode="json")

    flagged_brand, source_url = _scan_channel_text_for_competitors(
        channel,
        competitors,
    )
    search_queries = _build_search_queries(channel_name, channel_handle, competitors)
    primary_query = search_queries[0] if search_queries else f'"{channel_name}" "gold IRA"'
    if flagged_brand is None:
        flagged_brand, source_url, search_query = _run_serper_search_multi(
            search_queries,
            competitors,
        )
    else:
        search_query = primary_query

    gate0_record = _persist_gate0_result(
        channel,
        search_query,
        flagged_brand,
        source_url,
    )
    return Gate0TaskResult(
        channel_id=channel_id,
        checked_at=str(gate0_record["checked_at"]),
        search_query=search_query,
        result_status=str(gate0_record["result_status"]),
        flagged_brand=flagged_brand,
        source_url=source_url,
    ).model_dump(mode="json")


@celery_app.task(
    bind=True,
    max_retries=2,
    name="scraper.tasks.run_gate0",
)
def run_gate0(
    self: Task, channel_id: str, manual: bool = False
) -> dict[str, object]:
    """Run a Gate 0 compliance check for a channel."""
    logger.info("Running Gate 0 for channel %s", channel_id)
    try:
        return _run_gate0_sync(
            channel_id,
            manual=manual,
        )
    except (APIError, httpx.HTTPError, RuntimeError, ValueError) as exc:
        logger.error("Gate 0 failed for %s: %s", channel_id, exc, exc_info=True)
        if self.request.retries >= self.max_retries:
            try:
                _mark_gate0_unchecked(channel_id, str(exc))
            except APIError:
                logger.error(
                    "Failed to clear Gate 0 pending status for %s",
                    channel_id,
                    exc_info=True,
                )
            return Gate0TaskResult(
                channel_id=channel_id,
                skipped=True,
                reason=f"gate0_failed: {exc}",
            ).model_dump(mode="json")
        raise self.retry(exc=exc, countdown=30)
