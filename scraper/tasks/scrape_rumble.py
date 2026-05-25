"""Celery tasks: scrape Rumble channels."""

import asyncio
import logging
from urllib.parse import urlsplit
from collections import deque

from celery import Task
from playwright.async_api import Error as PlaywrightError
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.circuit_breaker import is_open, record_failure, record_success
from core.exceptions import CloudflareBlockError, ScraperBlockedError, ScraperClassifiedError
from core.proxy import proxy_session_manager
from core.supabase import get_supabase_client
from models import ScrapeTaskArgs, ScrapeTaskResult
from scrapers.rumble import RumbleScraper
from tasks.scrape_helpers import (
    acquire_scrape_lock,
    blocked_retry_countdown_seconds,
    daily_budget_bytes,
    deactivate_channel_for_url,
    get_daily_bytes_used,
    has_retries_remaining_for_block,
    has_retries_remaining,
    log_scrape_task_attempt,
    release_keyword_discovery_hold,
    release_scrape_lock,
    record_daily_bytes_used,
    retry_countdown_seconds,
)

logger = logging.getLogger(__name__)
_KPI_WINDOW = 20
_kpi_description_fallback = deque(maxlen=_KPI_WINDOW)
_kpi_responses = deque(maxlen=_KPI_WINDOW)
_kpi_bytes = deque(maxlen=_KPI_WINDOW)
_kpi_geoip_warning_count = 0


def _is_supported_rumble_channel_url(channel_url: str) -> bool:
    parsed = urlsplit(channel_url.strip())
    host = (parsed.hostname or "").lower()
    if not host.endswith("rumble.com"):
        return False
    path = parsed.path.rstrip("/")
    # Supported channel forms handled by scraper selectors and quality gates.
    return path.startswith("/c/") or path.startswith("/user/")


def _emit_kpi_alerts(channel_url: str, result: dict[str, object]) -> None:
    global _kpi_geoip_warning_count
    metrics = result.get("_scrape_metrics", {}) if isinstance(result, dict) else {}
    responses = int(metrics.get("responses", 0) or 0)
    bytes_est = int(metrics.get("bytes_est", 0) or 0)
    desc_fallback = bool(metrics.get("description_fallback_used", False))
    geoip_enabled = bool(metrics.get("geoip_enabled", True))
    _kpi_responses.append(responses)
    _kpi_bytes.append(bytes_est)
    _kpi_description_fallback.append(1 if desc_fallback else 0)
    if not geoip_enabled:
        _kpi_geoip_warning_count += 1
    if len(_kpi_responses) < 5:
        return

    fallback_rate = sum(_kpi_description_fallback) / len(_kpi_description_fallback)
    avg_responses = sum(_kpi_responses) / len(_kpi_responses)
    avg_bytes = sum(_kpi_bytes) / len(_kpi_bytes)
    if fallback_rate >= 0.30:
        logger.warning(
            "KPI_ALERT description_fallback_rate=%.2f window=%d channel=%s",
            fallback_rate,
            len(_kpi_description_fallback),
            channel_url,
        )
    if responses > avg_responses * 1.6:
        logger.warning(
            "KPI_ALERT responses_per_channel_drift current=%d avg=%.2f window=%d channel=%s",
            responses,
            avg_responses,
            len(_kpi_responses),
            channel_url,
        )
    if bytes_est > avg_bytes * 1.8:
        logger.warning(
            "KPI_ALERT bytes_per_channel_drift current=%d avg=%.0f window=%d channel=%s",
            bytes_est,
            avg_bytes,
            len(_kpi_bytes),
            channel_url,
        )
    if _kpi_geoip_warning_count > 0:
        logger.warning(
            "KPI_ALERT geoip_warning_count=%d",
            _kpi_geoip_warning_count,
        )


@celery_app.task(
    bind=True,
    max_retries=scraper_settings.scrape_run_max_retries_per_channel,
    default_retry_delay=60,
    name="scraper.tasks.scrape_rumble_channel",
)
def scrape_rumble_channel(self: Task, channel_url: str) -> dict[str, object]:
    """Scrape a single Rumble channel and store results.

    Retries once with exponential backoff on failure.

    Args:
        channel_url: Full URL of the Rumble channel.

    Returns:
        A dict with scrape result data.
    """
    args = ScrapeTaskArgs(channel_url=channel_url)
    channel_url = args.channel_url
    if not _is_supported_rumble_channel_url(channel_url):
        logger.warning("Skipping unsupported Rumble URL: %s", channel_url)
        return ScrapeTaskResult(
            status="failed",
            channel_url=channel_url,
            error="Unsupported Rumble URL shape; expected /c/<slug> or /user/<slug>",
        ).model_dump(mode="json")
    logger.info("Starting Rumble scrape: %s", channel_url)
    if is_open("rumble"):
        logger.warning(
            "Skipping Rumble scrape due to open circuit breaker: %s",
            channel_url,
        )
        return ScrapeTaskResult(
            status="failed",
            channel_url=channel_url,
            error="Circuit breaker open for rumble",
        ).model_dump(mode="json")
    if not acquire_scrape_lock(channel_url):
        logger.info("Skipping duplicate in-flight Rumble scrape: %s", channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
            error="Duplicate in-flight scrape skipped",
        ).model_dump(mode="json")
    scraper = RumbleScraper()
    try:
        scraper._session_key = (
            f"{channel_url}|attempt:{int(self.request.retries or 0)}|"
            f"task:{self.request.id}"
        )
        result = asyncio.run(scraper.scrape(channel_url))
        _emit_kpi_alerts(channel_url, result)
        metrics = result.get("_scrape_metrics", {}) if isinstance(result, dict) else {}
        bytes_est = int(metrics.get("bytes_est", 0) or 0)
        try:
            used = record_daily_bytes_used(bytes_est)
            budget = daily_budget_bytes()
            if budget > 0:
                logger.info(
                    "Daily proxy byte budget progress: used=%d budget=%d remaining=%d",
                    used,
                    budget,
                    max(0, budget - used),
                )
            else:
                logger.info("Daily proxy bytes used (no budget cap): %d", get_daily_bytes_used())
        except Exception as exc:
            logger.warning("Could not record Rumble proxy byte usage: %s", exc)
        release_keyword_discovery_hold(scraper, channel_url)
        record_success("rumble")
        logger.info("Rumble scrape complete: %s", channel_url)
        return ScrapeTaskResult(
            status="success",
            channel_url=channel_url,
            data=result,
        ).model_dump(mode="json")
    except CloudflareBlockError as exc:
        if exc.rotation_helps:
            session_id = proxy_session_manager.extract_session_id(scraper._session_key)
            proxy_session_manager.mark_blocked(session_id or (scraper._session_key or channel_url))
        if not has_retries_remaining_for_block(self):
            record_failure("rumble")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")
        log_scrape_task_attempt(scraper, channel_url, "blocked", exc, self)
        raise self.retry(
            exc=exc,
            countdown=blocked_retry_countdown_seconds(self),
        )
    except ScraperBlockedError as exc:
        session_id = proxy_session_manager.extract_session_id(scraper._session_key)
        proxy_session_manager.mark_blocked(session_id or (scraper._session_key or channel_url))
        if not has_retries_remaining_for_block(self):
            record_failure("rumble")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.error(
                "Rumble scrape blocked through final retry: %s - %s",
                channel_url,
                exc,
            )
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        log_scrape_task_attempt(scraper, channel_url, "blocked", exc, self)
        logger.warning(
            "Rumble scrape blocked (attempt %d): %s - %s",
            self.request.retries + 1,
            channel_url,
            exc,
        )
        raise self.retry(
            exc=exc,
            countdown=blocked_retry_countdown_seconds(self),
        )
    except ScraperClassifiedError as exc:
        if exc.terminal and not exc.retryable:
            record_failure("rumble")
            deactivate_channel_for_url(scraper, channel_url)
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.error(
                "Rumble scrape terminal classified failure: %s - %s",
                channel_url,
                exc,
            )
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        if not has_retries_remaining(self):
            record_failure("rumble")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        log_scrape_task_attempt(scraper, channel_url, "retry", exc, self)
        raise self.retry(
            exc=exc,
            countdown=retry_countdown_seconds(self),
        )
    except (APIError, PlaywrightError, RuntimeError, TypeError, ValueError) as exc:
        if not has_retries_remaining(self):
            record_failure("rumble")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.error(
                "Rumble scrape permanently failed after retries: %s - %s",
                channel_url,
                exc,
            )
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        log_scrape_task_attempt(scraper, channel_url, "retry", exc, self)
        logger.error(
            "Rumble scrape failed (attempt %d): %s - %s",
            self.request.retries + 1,
            channel_url,
            exc,
        )
        raise self.retry(
            exc=exc,
            countdown=retry_countdown_seconds(self),
        )
    except Exception as exc:
        if not has_retries_remaining(self):
            record_failure("rumble")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.exception(
                "Rumble scrape failed with unexpected error after retries: %s",
                channel_url,
            )
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        log_scrape_task_attempt(scraper, channel_url, "retry", exc, self)
        logger.exception(
            "Rumble scrape failed with unexpected error (attempt %d): %s",
            self.request.retries + 1,
            channel_url,
        )
        raise self.retry(
            exc=exc,
            countdown=retry_countdown_seconds(self),
        )
    finally:
        release_scrape_lock(channel_url)


@celery_app.task(name="scraper.tasks.scrape_rumble_all")
def scrape_rumble_all() -> dict[str, object]:
    """Fetch all Rumble channel URLs and dispatch individual scrape tasks.

    Returns:
        Dict with count of queued tasks.
    """
    logger.info("Starting batch Rumble scrape")
    try:
        client = get_supabase_client()
        result = (
            client.table("channels")
            .select("channel_url")
            .eq("platform", "rumble")
            .eq("is_active", True)
            .execute()
        )
        urls = [row["channel_url"] for row in (result.data or [])]
    except APIError as exc:
        logger.error("Failed to fetch Rumble channel URLs: %s", exc)
        return {"queued": 0, "error": str(exc)}

    if is_open("rumble"):
        logger.warning(
            "Skipping batch Rumble scrape dispatch due to open circuit breaker"
        )
        return {"queued": 0, "skipped": "circuit_breaker_open"}

    for url in urls:
        scrape_rumble_channel.delay(url)

    logger.info("Queued %d Rumble channel scrapes", len(urls))
    return {"queued": len(urls)}
