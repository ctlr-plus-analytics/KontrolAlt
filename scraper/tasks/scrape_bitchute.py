"""Celery tasks: scrape BitChute channels."""

import asyncio
import logging

from celery import Task
from patchright.async_api import Error as PlaywrightError
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.circuit_breaker import is_open, record_failure, record_success
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from core.supabase import get_supabase_client
from models import ScrapeTaskArgs, ScrapeTaskResult
from scrapers.bitchute import BitChuteScraper
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


@celery_app.task(
    bind=True,
    max_retries=scraper_settings.scrape_run_max_retries_per_channel,
    default_retry_delay=60,
    name="scraper.tasks.scrape_bitchute_channel",
)
def scrape_bitchute_channel(self: Task, channel_url: str) -> dict[str, object]:
    """Scrape a single BitChute channel and store results.

    Retries once with exponential backoff on failure.

    Args:
        channel_url: Full URL of the BitChute channel.

    Returns:
        A dict with scrape result data.
    """
    args = ScrapeTaskArgs(channel_url=channel_url)
    channel_url = args.channel_url
    logger.info("Starting BitChute scrape: %s", channel_url)
    if is_open("bitchute"):
        logger.warning(
            "Skipping BitChute scrape due to open circuit breaker: %s",
            channel_url,
        )
        return ScrapeTaskResult(
            status="failed",
            channel_url=channel_url,
            error="Circuit breaker open for bitchute",
        ).model_dump(mode="json")
    if not acquire_scrape_lock(channel_url):
        logger.info("Skipping duplicate in-flight BitChute scrape: %s", channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
            error="Duplicate in-flight scrape skipped",
        ).model_dump(mode="json")
    scraper = BitChuteScraper()
    try:
        scraper._session_key = (
            f"{channel_url}|attempt:{int(self.request.retries or 0)}|"
            f"task:{self.request.id}"
        )
        result = asyncio.run(scraper.scrape(channel_url))
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
            logger.warning("Could not record BitChute proxy byte usage: %s", exc)
        release_keyword_discovery_hold(scraper, channel_url)
        record_success("bitchute")
        logger.info("BitChute scrape complete: %s", channel_url)
        return ScrapeTaskResult(
            status="success",
            channel_url=channel_url,
            data=result,
        ).model_dump(mode="json")
    except ScraperBlockedError as exc:
        if not has_retries_remaining_for_block(self):
            record_failure("bitchute")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.error(
                "BitChute scrape blocked through final retry: %s - %s",
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
            "BitChute scrape blocked (attempt %d): %s - %s",
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
            record_failure("bitchute")
            deactivate_channel_for_url(scraper, channel_url)
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.error(
                "BitChute scrape terminal classified failure: %s - %s",
                channel_url,
                exc,
            )
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        if not has_retries_remaining(self):
            record_failure("bitchute")
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
            record_failure("bitchute")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.error(
                "BitChute scrape permanently failed after retries: %s - %s",
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
            "BitChute scrape failed (attempt %d): %s - %s",
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
            record_failure("bitchute")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            logger.exception(
                "BitChute scrape failed with unexpected error after retries: %s",
                channel_url,
            )
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        log_scrape_task_attempt(scraper, channel_url, "retry", exc, self)
        logger.exception(
            "BitChute scrape failed with unexpected error (attempt %d): %s",
            self.request.retries + 1,
            channel_url,
        )
        raise self.retry(
            exc=exc,
            countdown=retry_countdown_seconds(self),
        )
    finally:
        release_scrape_lock(channel_url)


@celery_app.task(name="scraper.tasks.scrape_bitchute_all")
def scrape_bitchute_all() -> dict[str, object]:
    """Fetch all BitChute channel URLs and dispatch individual scrape tasks.

    Returns:
        Dict with count of queued tasks.
    """
    logger.info("Starting batch BitChute scrape")
    try:
        client = get_supabase_client()
        result = (
            client.table("channels")
            .select("channel_url")
            .eq("platform", "bitchute")
            .eq("is_active", True)
            .execute()
        )
        urls = [row["channel_url"] for row in (result.data or [])]
    except APIError as exc:
        logger.error("Failed to fetch BitChute channel URLs: %s", exc)
        return {"queued": 0, "error": str(exc)}

    if is_open("bitchute"):
        logger.warning(
            "Skipping batch BitChute scrape dispatch due to open circuit breaker"
        )
        return {"queued": 0, "skipped": "circuit_breaker_open"}

    for url in urls:
        scrape_bitchute_channel.delay(url)

    logger.info("Queued %d BitChute channel scrapes", len(urls))
    return {"queued": len(urls)}
