"""Redis-backed circuit breaker for platform scrape failures."""

import logging

import redis

from core.config import scraper_settings
from core.runtime_settings import get_runtime_settings

logger = logging.getLogger(__name__)

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
    if not get_runtime_settings().scrape_circuit_breaker_enabled:
        return False
    try:
        return bool(_redis_conn().exists(_open_key(platform)))
    except redis.RedisError as exc:
        logger.warning("Circuit breaker read failed for %s: %s", platform, exc)
        return False


def record_failure(platform: str) -> None:
    """Record a failed scrape and open breaker when threshold is exceeded."""
    if not get_runtime_settings().scrape_circuit_breaker_enabled:
        return
    try:
        conn = _redis_conn()
        runtime = get_runtime_settings()
        key = _fail_key(platform)
        count = int(conn.incr(key))
        conn.expire(key, runtime.scrape_circuit_breaker_window_seconds)
        if count >= runtime.scrape_circuit_breaker_fail_threshold:
            conn.set(
                _open_key(platform),
                "1",
                ex=runtime.scrape_circuit_breaker_cooldown_seconds,
            )
            logger.warning(
                "Circuit breaker opened for %s: failures=%d threshold=%d cooldown_s=%d",
                platform,
                count,
                runtime.scrape_circuit_breaker_fail_threshold,
                runtime.scrape_circuit_breaker_cooldown_seconds,
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


def reset_circuit_breaker(platform: str) -> None:
    """Manually clear the open breaker and failure counter for a platform."""
    try:
        conn = _redis_conn()
        conn.delete(_open_key(platform), _fail_key(platform))
        logger.info("Circuit breaker manually reset for %s", platform)
    except redis.RedisError as exc:
        logger.warning("Circuit breaker manual reset failed for %s: %s", platform, exc)
