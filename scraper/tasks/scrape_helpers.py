"""Shared helpers for scrape Celery tasks."""

import asyncio
import logging
import random
from datetime import datetime, timezone
from urllib.parse import urlsplit

from celery import Task
from postgrest.exceptions import APIError

from core.config import scraper_settings
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)
_USAGE_KEY_PREFIX = "scraper:usage:bytes:"
_KEYWORD_DISCOVERY_HOLD_SOURCE = "auto_keyword_hold"
_KEYWORD_DISCOVERY_LIVE_SOURCE = "auto_keyword"
_KEYWORD_DISCOVERY_FAILED_SOURCE = "auto_keyword_failed"


def retry_countdown_seconds(task: Task) -> int:
    """Return exponential retry delay with jitter.

    Jitter reduces synchronized retry storms when many tasks fail together.
    """
    retries = int(task.request.retries or 0)
    base = 60 * (2**retries)
    jitter_factor = random.uniform(0.8, 1.2)
    return int(base * jitter_factor)


def has_retries_remaining(task: Task) -> bool:
    """Return True when Celery should retry this task again."""
    max_retries = int(task.max_retries or 0)
    retries = int(task.request.retries or 0)
    return retries < max_retries


def has_retries_remaining_for_block(task: Task) -> bool:
    """Return True when blocked/challenge errors should still retry."""
    retries = int(task.request.retries or 0)
    return retries < scraper_settings.scrape_run_max_retries_per_channel


def _infer_platform(channel_url: str) -> str | None:
    """Infer the supported platform from a channel URL."""
    hostname = (urlsplit(channel_url).hostname or "").lower()
    if "rumble.com" in hostname:
        return "rumble"
    if "bitchute.com" in hostname:
        return "bitchute"
    return None


def _fallback_channel_name(channel_url: str) -> str:
    """Return a stable placeholder name for pre-scrape failure logging."""
    path = urlsplit(channel_url).path.strip("/")
    if path:
        return path.split("/")[-1] or channel_url
    return channel_url


def _ensure_channel_for_logging(
    scraper: BaseScraper, channel_url: str
) -> object | None:
    """Create a minimal channel row so failed scrape attempts can be logged."""
    platform = _infer_platform(channel_url)
    if platform is None:
        return None

    result = (
        scraper.supabase.table("channels")
        .upsert(
            {
                "platform": platform,
                "channel_url": channel_url,
                "name": _fallback_channel_name(channel_url),
                "description": "",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="channel_url",
        )
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]["id"]


def log_scrape_task_attempt(
    scraper: BaseScraper,
    channel_url: str,
    status: str,
    error: Exception,
) -> None:
    """Log a retry or final failure for an existing channel URL."""
    try:
        channel_id = asyncio.run(scraper.get_channel_id(channel_url))
        if channel_id is None:
            channel_id = _ensure_channel_for_logging(scraper, channel_url)
            if channel_id is None:
                logger.warning(
                    "Could not log %s scrape attempt; channel URL not found: %s",
                    status,
                    channel_url,
                )
                return
        asyncio.run(scraper.log_scrape_attempt(channel_id, status, str(error)))
    except (APIError, TypeError, ValueError) as log_error:
        logger.error(
            "Failed to log %s scrape attempt for %s: %s",
            status,
            channel_url,
            log_error,
            exc_info=True,
        )


def deactivate_channel_for_url(scraper: BaseScraper, channel_url: str) -> bool:
    """Set is_active=false for a channel URL when terminal failures are detected."""
    try:
        # If this channel is on keyword-discovery hold, mark it failed so it
        # does not remain in hold and get re-queued by hold-aware dispatch.
        scraper.supabase.table("channels").update(
            {
                "is_active": False,
                "discovery_source": _KEYWORD_DISCOVERY_FAILED_SOURCE,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("channel_url", channel_url).eq(
            "discovery_source", _KEYWORD_DISCOVERY_HOLD_SOURCE
        ).execute()

        result = (
            scraper.supabase.table("channels")
            .update(
                {
                    "is_active": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("channel_url", channel_url)
            .execute()
        )
        return bool(result.data)
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Failed to deactivate channel after terminal scrape error: %s - %s",
            channel_url,
            exc,
            exc_info=True,
        )
        return False


def release_keyword_discovery_hold(scraper: BaseScraper, channel_url: str) -> None:
    """Activate held keyword-discovered channels after successful scrape."""
    try:
        scraper.supabase.table("channels").update(
            {
                "is_active": True,
                "discovery_source": _KEYWORD_DISCOVERY_LIVE_SOURCE,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("channel_url", channel_url).eq(
            "discovery_source", _KEYWORD_DISCOVERY_HOLD_SOURCE
        ).execute()
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Failed to release discovery hold for %s: %s",
            channel_url,
            exc,
            exc_info=True,
        )


def _daily_usage_key() -> str:
    return f"{_USAGE_KEY_PREFIX}{datetime.now(timezone.utc).date().isoformat()}"


def _redis_client():
    from redis import Redis

    return Redis.from_url(scraper_settings.redis_url)


def get_daily_bytes_used() -> int:
    """Return accumulated estimated bytes for current UTC day."""
    client = _redis_client()
    raw = client.get(_daily_usage_key())
    if raw is None:
        return 0
    return int(raw)


def record_daily_bytes_used(bytes_est: int) -> int:
    """Increment and return daily estimated bytes usage."""
    if bytes_est <= 0:
        return get_daily_bytes_used()
    client = _redis_client()
    key = _daily_usage_key()
    total = int(client.incrby(key, int(bytes_est)))
    client.expire(key, 3 * 24 * 3600)
    return total


def daily_budget_bytes() -> int:
    """Return configured daily budget in bytes (0 means unlimited)."""
    mb = scraper_settings.scrape_daily_byte_budget_mb
    if mb <= 0:
        return 0
    return mb * 1024 * 1024
