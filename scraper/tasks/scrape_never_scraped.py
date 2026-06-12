"""Celery task to scrape never-scraped Rumble and Substack channels."""

import logging
import random

from postgrest.exceptions import APIError

from core.runtime_settings import get_runtime_settings
from core.supabase import get_supabase_client
from tasks.scrape_rumble import scrape_rumble_channel
from tasks.scrape_substack import scrape_substack_channel
from tasks.task_queues import QUEUE_RUMBLE, QUEUE_SUBSTACK
from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="scraper.tasks.scrape_never_scraped_rumble_substack", queue="discovery")
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
    queued_by_platform = {"rumble": 0, "substack": 0}
    queued_tasks: list[dict[str, object]] = []
    for i, row in enumerate(channels):
        channel_url = str(row.get("channel_url") or "")
        platform = str(row.get("platform") or "")
        if not channel_url or platform not in {"rumble", "substack"}:
            continue

        stagger_s = int(i * random.uniform(4, 10))
        if platform == "rumble":
            task = scrape_rumble_channel.apply_async(
                args=[channel_url],
                countdown=stagger_s,
                queue=QUEUE_RUMBLE,
            )
        else:
            task = scrape_substack_channel.apply_async(
                args=[channel_url],
                countdown=stagger_s,
                queue=QUEUE_SUBSTACK,
            )
        queued += 1
        queued_by_platform[platform] += 1
        queued_tasks.append(
            {
                "task_id": getattr(task, "id", None),
                "platform": platform,
                "channel_url": channel_url,
                "countdown_seconds": stagger_s,
            }
        )

    logger.info("Queued never-scraped bootstrap scrapes: queued=%d", queued)
    return {
        "queued": queued,
        "queued_by_platform": queued_by_platform,
        "queued_tasks": queued_tasks,
    }
