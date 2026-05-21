"""Redis-backed circuit breaker for platform scrape failures."""

import logging
import os

import redis

from core.config import scraper_settings

logger = logging.getLogger(__name__)

_FAIL_THRESHOLD = int(os.environ.get("SCRAPE_CB_FAIL_THRESHOLD", "5"))
_WINDOW_SECONDS = int(os.environ.get("SCRAPE_CB_WINDOW_SECONDS", "1800"))
_COOLDOWN_SECONDS = int(os.environ.get("SCRAPE_CB_COOLDOWN_SECONDS", "1800"))

_redis_client: redis.Redis | None = None


def _redis_conn() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            scraper_settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


def _fail_key(platform: str) -> str:
    return f"scrape:cb:fail:{platform}"


def _open_key(platform: str) -> str:
    return f"scrape:cb:open:{platform}"


def is_open(platform: str) -> bool:
    """Return True when the breaker is open for a platform."""
    try:
        return bool(_redis_conn().exists(_open_key(platform)))
    except redis.RedisError as exc:
        logger.warning("Circuit breaker read failed for %s: %s", platform, exc)
        return False


def record_failure(platform: str) -> None:
    """Record a failed scrape and open breaker when threshold is exceeded."""
    try:
        conn = _redis_conn()
        key = _fail_key(platform)
        count = int(conn.incr(key))
        conn.expire(key, _WINDOW_SECONDS)
        if count >= _FAIL_THRESHOLD:
            conn.set(_open_key(platform), "1", ex=_COOLDOWN_SECONDS)
            logger.warning(
                "Circuit breaker opened for %s: failures=%d threshold=%d cooldown_s=%d",
                platform,
                count,
                _FAIL_THRESHOLD,
                _COOLDOWN_SECONDS,
            )
    except redis.RedisError as exc:
        logger.warning("Circuit breaker write failed for %s: %s", platform, exc)


def record_success(platform: str) -> None:
    """Reset recent failure counter for a platform after a successful scrape."""
    try:
        conn = _redis_conn()
        conn.delete(_fail_key(platform))
    except redis.RedisError as exc:
        logger.warning("Circuit breaker reset failed for %s: %s", platform, exc)
