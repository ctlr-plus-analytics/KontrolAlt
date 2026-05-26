"""Shared helpers for scrape Celery tasks."""

import asyncio
import hashlib
import logging
import random
from datetime import datetime, timezone
from urllib.parse import urlsplit

from celery import Task
from postgrest.exceptions import APIError

from core.config import scraper_settings
from core.exceptions import CloudflareBlockError, ScraperBlockedError, ScraperClassifiedError
from core.system_settings import get_runtime_settings
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)
_USAGE_KEY_PREFIX = "scraper:usage:bytes:"
_KEYWORD_DISCOVERY_FAILED_SOURCE = "auto_keyword_failed"
_SCRAPE_LOCK_KEY_PREFIX = "scraper:lock:channel:"
_SCRAPE_LOCK_TTL_SECONDS = 20 * 60
_PLATFORM_SLOT_KEY_PREFIX = "scraper:slot:platform:"
_PLATFORM_SLOT_TTL_SECONDS = 20 * 60


def retry_countdown_seconds(task: Task) -> int:
    """Return exponential retry delay with jitter.

    Jitter reduces synchronized retry storms when many tasks fail together.
    """
    runtime = get_runtime_settings()
    retries = int(task.request.retries or 0)
    base = runtime.scrape_retry_base_delay_seconds * (2**retries)
    jitter_factor = random.uniform(
        runtime.scrape_retry_jitter_min,
        runtime.scrape_retry_jitter_max,
    )
    return int(base * jitter_factor)


def blocked_retry_countdown_seconds(task: Task) -> int:
    """Return a slower retry delay for anti-bot challenge failures.

    Block/challenge waves often affect many channels at once. A longer cooldown
    lowers synchronized re-hits on the same edge protections.
    """
    runtime = get_runtime_settings()
    base = retry_countdown_seconds(task)
    return max(
        int(runtime.scrape_blocked_retry_min_seconds),
        int(base * float(runtime.scrape_blocked_retry_multiplier)),
    )


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
    if "substack.com" in hostname:
        return "substack"
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
    task: Task | None = None,
) -> None:
    """Log a retry or final failure for an existing channel URL."""
    error_payload = _format_error_payload(error, task)
    try:
        scraper.supabase.table("channels").update(
            {
                "last_scrape_error": error_payload,
                "discovery_status": "blocked"
                if status == "blocked"
                else "failed"
                if status == "failed"
                else "queued",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("channel_url", channel_url).execute()
        # Synchronous channel ID lookup (avoids nested asyncio.run which
        # would crash if an event loop is already running).
        result = (
            scraper.supabase.table("channels")
            .select("id")
            .eq("channel_url", channel_url)
            .maybe_single()
            .execute()
        )
        channel_id = str(result.data["id"]) if result.data else None
        if channel_id is None:
            channel_id_raw = _ensure_channel_for_logging(scraper, channel_url)
            if channel_id_raw is None:
                logger.warning(
                    "Could not log %s scrape attempt; channel URL not found: %s",
                    status,
                    channel_url,
                )
                return
            channel_id = str(channel_id_raw)
        # Synchronous scrape-log insert (avoids nested asyncio.run).
        scraper.supabase.table("scrape_logs").insert(
            {
                "channel_id": channel_id,
                "attempted_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "error_message": error_payload,
            }
        ).execute()
    except (APIError, TypeError, ValueError) as log_error:
        logger.error(
            "Failed to log %s scrape attempt for %s: %s",
            status,
            channel_url,
            log_error,
            exc_info=True,
        )


def _format_error_payload(error: Exception, task: Task | None = None) -> str:
    """Return normalized error string for analytics and alerting."""
    code = _error_code(error)
    retries = int(task.request.retries or 0) if task is not None else 0
    attempt = retries + 1
    terminal = (
        error.terminal
        if isinstance(error, ScraperClassifiedError)
        else status_is_terminal_code(code)
    )
    retryable = (
        error.retryable
        if isinstance(error, ScraperClassifiedError)
        else not terminal
    )
    return (
        f"code={code}; attempt={attempt}; terminal={'true' if terminal else 'false'}; "
        f"retryable={'true' if retryable else 'false'}; detail={error}"
    )


def _error_code(error: Exception) -> str:
    """Map exceptions to stable error codes."""
    if isinstance(error, ScraperClassifiedError):
        return error.reason_code
    if isinstance(error, CloudflareBlockError):
        suffix = error.error_code if error.error_code is not None else error.block_type
        return f"cloudflare_{suffix}"
    if isinstance(error, ScraperBlockedError):
        return "cloudflare_or_blocked"
    if isinstance(error, APIError):
        return "supabase_api_error"
    error_type = type(error).__name__.lower()
    if "timeout" in error_type:
        return "timeout"
    if "playwright" in error_type:
        return "browser_playwright_error"
    if isinstance(error, RuntimeError):
        return "runtime_error"
    if isinstance(error, ValueError):
        return "value_error"
    if isinstance(error, TypeError):
        return "type_error"
    return f"unexpected_{error_type}"


def status_is_terminal_code(code: str) -> bool:
    """Return True for non-recoverable codes."""
    return code in {
        "not_found_404",
        "channel_deleted",
        "channel_banned_or_suspended",
        "channel_unavailable",
    }


def deactivate_channel_for_url(scraper: BaseScraper, channel_url: str) -> bool:
    """Set is_active=false for a channel URL when terminal failures are detected."""
    try:
        result = (
            scraper.supabase.table("channels")
            .update(
                {
                    "is_active": False,
                    "discovery_status": "failed",
                    "last_discovery_source": _KEYWORD_DISCOVERY_FAILED_SOURCE,
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
    """Mark discovered channels as scraped after successful scrape."""
    try:
        scraper.supabase.table("channels").update(
            {
                "is_active": True,
                "has_been_scraped": True,
                "discovery_status": "scraped",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("channel_url", channel_url).execute()
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


def _scrape_lock_key(channel_url: str) -> str:
    digest = hashlib.sha1(channel_url.encode("utf-8")).hexdigest()
    return f"{_SCRAPE_LOCK_KEY_PREFIX}{digest}"


def acquire_scrape_lock(channel_url: str) -> bool:
    """Acquire a short-lived distributed lock for a channel URL."""
    try:
        client = _redis_client()
        return bool(
            client.set(
                _scrape_lock_key(channel_url),
                "1",
                nx=True,
                ex=_SCRAPE_LOCK_TTL_SECONDS,
            )
        )
    except Exception as exc:
        logger.warning("Failed to acquire scrape lock for %s: %s", channel_url, exc)
        return True


def release_scrape_lock(channel_url: str) -> None:
    """Release distributed lock for a channel URL."""
    try:
        _redis_client().delete(_scrape_lock_key(channel_url))
    except Exception as exc:
        logger.warning("Failed to release scrape lock for %s: %s", channel_url, exc)


def try_acquire_platform_slot(platform: str, limit: int) -> bool:
    """Acquire one in-flight slot for a platform, capped by `limit`."""
    if limit <= 0:
        return True
    key = f"{_PLATFORM_SLOT_KEY_PREFIX}{platform}"
    try:
        client = _redis_client()
        total = int(client.incr(key))
        client.expire(key, _PLATFORM_SLOT_TTL_SECONDS)
        if total > limit:
            client.decr(key)
            return False
        return True
    except Exception as exc:
        logger.warning("Failed to acquire platform slot for %s: %s", platform, exc)
        return True


def release_platform_slot(platform: str) -> None:
    """Release one in-flight slot for a platform."""
    key = f"{_PLATFORM_SLOT_KEY_PREFIX}{platform}"
    try:
        client = _redis_client()
        current = client.get(key)
        if current is None:
            return
        if int(current) <= 1:
            client.delete(key)
        else:
            client.decr(key)
    except Exception as exc:
        logger.warning("Failed to release platform slot for %s: %s", platform, exc)


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
    mb = get_runtime_settings().scrape_daily_byte_budget_mb
    if mb <= 0:
        return 0
    return mb * 1024 * 1024
