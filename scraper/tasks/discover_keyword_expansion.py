"""Compatibility wrapper for legacy keyword expansion task name."""

import logging

from postgrest.exceptions import APIError

from worker import celery_app
from core.supabase import get_supabase_client
from tasks.discover_channels import _discover_from_keywords, _query_for_keyword
from utils.channel_urls import canonicalize_channel_url

logger = logging.getLogger(__name__)


def _canonicalize_channel_url(raw_url: str) -> tuple[str | None, str | None]:
    """Compatibility helper used by older tests and callers."""
    candidate = canonicalize_channel_url(raw_url)
    if candidate is None:
        return None, None
    return candidate.channel_url, candidate.platform


def discover_keyword_expansion_now(
    *,
    platform: str | None = None,
) -> dict[str, object]:
    """Run taxonomy keyword discovery and insert channels directly."""
    client = get_supabase_client()
    result = _discover_from_keywords(
        client,
        platform=platform,
    )
    return {key: value for key, value in result.items() if key != "new_urls"}


@celery_app.task(name="scraper.tasks.discover_keyword_expansion", queue="discovery")
def discover_keyword_expansion(
    platform: str | None = None,
) -> dict[str, object]:
    """Legacy task alias for taxonomy direct discovery."""
    logger.info("Starting keyword/niche search expansion platform=%s", platform or "all")
    try:
        result = discover_keyword_expansion_now(
            platform=platform,
        )
        logger.info(
            "Keyword expansion complete: queries=%d pages=%d discovered=%d inserted=%d refreshed=%d invalid=%d",
            result["searched_queries"],
            result["pages_fetched"],
            result["discovered"],
            result["inserted"],
            result["refreshed"],
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
            "inserted": 0,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 1,
            "inserted_rumble": 0,
            "inserted_substack": 0,
            "category_metrics": {},
            "feedback_terms": [],
            "error": str(exc),
        }
