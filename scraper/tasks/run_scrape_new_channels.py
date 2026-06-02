"""Celery task orchestration for scraping only never-scraped channels.

Workflow: scrape never-scraped channels → classify → Gate 0.
No discovery step — use run_daily_scrape for the full pipeline.
"""

import logging

from celery import chord

from worker import celery_app
from core.supabase import get_supabase_client
from core.runtime_settings import get_runtime_settings
from tasks.run_daily_scrape import (
    _enabled_platforms,
    _prioritize_channels_for_scrape,
    _stage_scrape_signatures,
    run_post_scrape_tasks,
)
from tasks.scrape_rumble import scrape_rumble_channel
from tasks.scrape_substack import scrape_substack_channel

logger = logging.getLogger(__name__)


@celery_app.task(name="scraper.tasks.run_scrape_new_channels")
def run_scrape_new_channels() -> dict[str, object]:
    """Scrape all never-scraped channels, then classify and run Gate 0.

    Fetches only channels where has_been_scraped is False, dispatches scrapes
    via a Celery chord, and triggers run_post_scrape_tasks as the callback.
    """
    logger.info("Starting new-channel scrape workflow")

    try:
        client = get_supabase_client()
        result = (
            client.table("channels")
            .select(
                "id,channel_url,platform,subscriber_count,avg_views,avg_comments,"
                "last_active_date,has_been_scraped,discovery_status,discovery_source,"
                "last_scraped_at,discovery_confidence,discovery_quality_tier,"
                "discovery_evidence_count,discovery_niche_hint"
            )
            .eq("is_active", True)
            .eq("has_been_scraped", False)
            .execute()
        )
        channels = _prioritize_channels_for_scrape(result.data or [])
    except Exception as exc:
        logger.error("Failed to fetch never-scraped channels: %s", exc, exc_info=True)
        return {"queued": 0, "error": str(exc)}

    enabled_platforms = _enabled_platforms()
    scrape_signatures = []
    for channel in channels:
        channel_url = str(channel.get("channel_url") or "")
        platform = str(channel.get("platform") or "")
        if not channel_url:
            continue
        if platform not in enabled_platforms:
            continue
        if platform == "rumble":
            scrape_signatures.append((platform, scrape_rumble_channel.s(channel_url)))
        elif platform == "substack":
            scrape_signatures.append((platform, scrape_substack_channel.s(channel_url)))
        else:
            logger.warning("Unsupported platform skipped: %s", platform)

    max_channels = get_runtime_settings().scrape_run_max_channels
    if max_channels > 0:
        scrape_signatures = scrape_signatures[:max_channels]

    if not scrape_signatures:
        logger.info("No never-scraped channels found; running post-scrape tasks directly")
        post_task = run_post_scrape_tasks.delay()
        return {"queued": 0, "post_scrape_task_id": post_task.id}

    staged = _stage_scrape_signatures(scrape_signatures)
    workflow = chord(staged)(run_post_scrape_tasks.si())
    logger.info(
        "Queued new-channel scrape workflow: scrapes=%d callback=%s",
        len(staged),
        workflow.id,
    )
    return {
        "queued": len(staged),
        "workflow_task_id": workflow.id,
    }
