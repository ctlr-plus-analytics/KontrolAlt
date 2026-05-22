"""Compatibility wrapper for legacy seed expansion task name."""

import logging

from postgrest.exceptions import APIError

from worker import celery_app
from core.supabase import get_supabase_client
from tasks.discover_channels import _discover_from_known_channels

logger = logging.getLogger(__name__)


def discover_seed_expansion_now() -> dict[str, object]:
    """Run known-channel discovery and insert channels directly."""
    client = get_supabase_client()
    result = _discover_from_known_channels(client)
    return {key: value for key, value in result.items() if key != "new_urls"}


@celery_app.task(name="scraper.tasks.discover_seed_expansion")
def discover_seed_expansion() -> dict[str, object]:
    """Legacy task alias for known-channel direct discovery."""
    logger.info("Starting seed expansion discovery")
    try:
        result = discover_seed_expansion_now()
        logger.info(
            "Seed expansion complete: discovered=%d inserted=%d refreshed=%d duplicates=%d invalid=%d",
            result["discovered"],
            result["inserted"],
            result["refreshed"],
            result["duplicates"],
            result["invalid"],
        )
        return result
    except (APIError, KeyError, TypeError, ValueError) as exc:
        logger.error("Seed expansion failed: %s", exc, exc_info=True)
        return {
            "source_channels": 0,
            "discovered": 0,
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 1,
            "field_metrics": {},
            "platform_metrics": {},
            "inserted_platform_metrics": {},
            "error": str(exc),
        }
