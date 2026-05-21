"""Scraper service for Celery dispatch."""

from datetime import datetime, timezone

from celery import Celery
from core.config import settings
from core.logging import get_logger
from models.scrape import ScrapeTaskResponse
from services import admin_service
from workers.tasks import TASK_DISCOVER_KEYWORD_EXPANSION, TASK_DISCOVER_SEED_EXPANSION
from workers.tasks import TASK_RUN_DAILY_SCRAPE

logger = get_logger(__name__)

_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)


async def trigger_full_scrape() -> ScrapeTaskResponse:
    """Trigger a full scrape run across all supported platforms."""
    task = _celery.send_task(TASK_RUN_DAILY_SCRAPE)

    logger.info(
        "Full scrape workflow triggered: task=%s",
        task.id,
    )
    return ScrapeTaskResponse(
        message=f"Scrape workflow triggered: {task.id}",
        task_id=task.id,
        task_ids=[task.id],
        triggered_at=datetime.now(timezone.utc),
    )


async def trigger_discovery_only() -> ScrapeTaskResponse:
    """Trigger only discovery expansion tasks (no scrape workflow)."""
    if not admin_service.is_feature_enabled("discovery"):
        return ScrapeTaskResponse(
            message="Discovery is disabled in system settings.",
            task_id="",
            task_ids=[],
            triggered_at=datetime.now(timezone.utc),
        )

    seed_task = _celery.send_task(TASK_DISCOVER_SEED_EXPANSION)
    keyword_task = _celery.send_task(TASK_DISCOVER_KEYWORD_EXPANSION)
    task_ids = [seed_task.id, keyword_task.id]

    logger.info(
        "Discovery-only workflow triggered: seed_task=%s keyword_task=%s",
        seed_task.id,
        keyword_task.id,
    )
    return ScrapeTaskResponse(
        message="Discovery-only tasks triggered",
        task_id=seed_task.id,
        task_ids=task_ids,
        triggered_at=datetime.now(timezone.utc),
    )
