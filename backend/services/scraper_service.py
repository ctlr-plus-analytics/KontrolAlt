"""Scraper service for Celery dispatch."""

from datetime import datetime, timezone

from celery import Celery
from core.config import settings
from core.logging import get_logger
from models.scrape import ScrapeTaskResponse
from services import admin_service
from workers.tasks import QUEUE_DISCOVERY
from workers.tasks import TASK_DISCOVER_CHANNELS
from workers.tasks import TASK_RUN_DAILY_SCRAPE

logger = get_logger(__name__)

_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)


async def trigger_full_scrape() -> ScrapeTaskResponse:
    """Trigger a full scrape run across all supported platforms."""
    task = _celery.send_task(TASK_RUN_DAILY_SCRAPE, queue=QUEUE_DISCOVERY)

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

    discovery_task = _celery.send_task(TASK_DISCOVER_CHANNELS, queue=QUEUE_DISCOVERY)
    task_ids = [discovery_task.id]

    logger.info(
        "Discovery workflow triggered: task=%s",
        discovery_task.id,
    )
    return ScrapeTaskResponse(
        message="Discovery workflow triggered",
        task_id=discovery_task.id,
        task_ids=task_ids,
        triggered_at=datetime.now(timezone.utc),
    )
