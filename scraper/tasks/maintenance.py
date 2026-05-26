"""Operational maintenance tasks for queue and lock hygiene."""

import logging

from worker import celery_app
from tasks.scrape_helpers import clear_platform_slots

logger = logging.getLogger(__name__)


@celery_app.task(name="scraper.tasks.clear_platform_slots")
def clear_platform_slots_task() -> dict[str, object]:
    """Manually clear platform slot counters in Redis."""
    result = clear_platform_slots()
    logger.info(
        "Maintenance clear_platform_slots: deleted=%s keys=%s",
        result.get("deleted"),
        ",".join(result.get("keys", [])),
    )
    return result

