"""Celery task: run Gate 0 compliance check for a channel."""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from celery import Task
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client
from core.system_settings import get_runtime_settings
from models import Gate0TaskResult

logger = logging.getLogger(__name__)

COMPETITOR_BRANDS: list[str] = [
    "Noble Gold",
    "Birch Gold",
    "Patriot Gold",
    "Kirk Elliot",
]
COMPETITOR_DOMAINS: list[str] = [
    "noblegold.com",
    "birchgold.com",
    "patriotgold.com",
    "kirkelliot.com",
]
_SERPER_SEARCH_URL = "https://google.serper.dev/search"
_SERPER_QUOTA_STATUS_CODES = {402, 429}


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
    channel: dict[str, object], manual: bool = False
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
            if age < timedelta(days=7):
                return False, "clean channel checked within the last 7 days"

    return True, None


def _iter_scan_values(channel: dict[str, object]) -> list[str]:
    """Return stored fields that Gate 0 local scan should inspect."""
    contact_info = channel.get("contact_info", []) or []
    secondary_urls = channel.get("secondary_urls", []) or []
    description = str(channel.get("description") or "")

    if isinstance(contact_info, str):
        contact_values = [contact_info]
    else:
        contact_values = [str(value) for value in contact_info]

    if isinstance(secondary_urls, str):
        secondary_values = [secondary_urls]
    else:
        secondary_values = [str(value) for value in secondary_urls]

    values = [*contact_values, *secondary_values]
    values.append(description)
    return values


def _scan_channel_text_for_competitors(
    channel: dict[str, object]
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

        for domain in COMPETITOR_DOMAINS:
            if domain in text_lower:
                return domain, source_url

        for brand in COMPETITOR_BRANDS:
            if brand.lower() in text_lower:
                return brand, source_url

    return None, None


def _scan_serper_results(
    organic_results: object,
) -> tuple[str | None, str | None]:
    """Scan top Serper organic results for competitor brands/domains."""
    if not isinstance(organic_results, list):
        return None, None

    for item in organic_results[:10]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        link = str(item.get("link") or "")
        combined = f"{title} {snippet} {link}".lower()

        for domain in COMPETITOR_DOMAINS:
            if domain in combined:
                return domain, link

        for brand in COMPETITOR_BRANDS:
            if brand.lower() in combined:
                return brand, link

    return None, None


def _run_serper_search(search_query: str) -> tuple[str | None, str | None]:
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
                "num": 10,
            },
        )
        if response.status_code in _SERPER_QUOTA_STATUS_CODES:
            raise RuntimeError("Serper quota exceeded for today")

        response.raise_for_status()
        data = response.json()
        organic_results = data.get("organic", []) if isinstance(data, dict) else []
        return _scan_serper_results(organic_results)


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


def _run_gate0_sync(
    channel_id: str,
    manual: bool = False,
) -> dict[str, object]:
    """Synchronous Gate 0 check implementation."""
    runtime = get_runtime_settings()
    if not runtime.gate0_enabled:
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
    should_run, skip_reason = _should_run_gate0_check(channel, manual=manual)
    if not should_run:
        logger.info("Gate 0 skipped for %s: %s", channel_id, skip_reason)
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason=skip_reason,
        ).model_dump(mode="json")

    channel_name = str(channel.get("name") or "")
    search_query = f'"{channel_name}" "gold IRA"'

    flagged_brand, source_url = _scan_channel_text_for_competitors(channel)
    if flagged_brand is None:
        flagged_brand, source_url = _run_serper_search(search_query)

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
        raise self.retry(exc=exc, countdown=30)
