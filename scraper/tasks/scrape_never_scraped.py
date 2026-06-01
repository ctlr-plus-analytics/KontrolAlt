"""Celery task to scrape never-scraped Rumble and Substack channels."""

import logging
import random

from postgrest.exceptions import APIError

from core.circuit_breaker import is_open
from core.runtime_settings import get_runtime_settings
from core.supabase import get_supabase_client
from tasks.scrape_rumble import scrape_rumble_channel
from tasks.scrape_substack import scrape_substack_channel
from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="scraper.tasks.scrape_never_scraped_rumble_substack")
def scrape_never_scraped_rumble_substack() -> dict[str, object]:
    """Queue never-scraped, active Rumble and Substack channels."""
    runtime = get_runtime_settings()
    enabled_platforms: set[str] = set()
    if runtime.scrape_platform_slot_limit_rumble != 0:
        enabled_platforms.add("rumble")
    if runtime.scrape_platform_slot_limit_substack != 0:
        enabled_platforms.add("substack")

    if not enabled_platforms:
        logger.info("Skipping never-scraped bootstrap: both platforms disabled")
        return {"queued": 0, "skipped": "platform_disabled"}

    try:
        client = get_supabase_client()
        result = (
            client.table("channels")
            .select("channel_url,platform")
            .in_("platform", list(enabled_platforms))
            .eq("is_active", True)
            .is_("subscriber_count", "null")
            .is_("avg_views", "null")
            .is_("avg_comments", "null")
            .eq("has_been_scraped", False)
            .in_("discovery_status", ["new", "queued"])
            .eq("dashboard_metrics_complete", False)
            .eq("dashboard_url_valid", True)
            .eq("dashboard_eligible", False)
            .execute()
        )
        channels = result.data or []
    except APIError as exc:
        logger.error("Failed to fetch never-scraped channel URLs: %s", exc)
        return {"queued": 0, "error": str(exc)}

    queued = 0
    skipped_breaker = 0
    for i, row in enumerate(channels):
        channel_url = str(row.get("channel_url") or "")
        platform = str(row.get("platform") or "")
        if not channel_url or platform not in {"rumble", "substack"}:
            continue
        if is_open(platform):
            skipped_breaker += 1
            logger.warning(
                "Skipping %s never-scraped channel due to open circuit breaker: %s",
                platform,
                channel_url,
            )
            continue

        stagger_s = int(i * random.uniform(4, 10))
        if platform == "rumble":
            scrape_rumble_channel.apply_async(args=[channel_url], countdown=stagger_s)
        else:
            scrape_substack_channel.apply_async(args=[channel_url], countdown=stagger_s)
        queued += 1

    logger.info(
        "Queued never-scraped bootstrap scrapes: queued=%d skipped_breaker=%d",
        queued,
        skipped_breaker,
    )
    return {"queued": queued, "skipped_breaker": skipped_breaker}

