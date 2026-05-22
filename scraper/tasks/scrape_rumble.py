"""Celery tasks: scrape Rumble channels."""

import asyncio
import logging

from celery import Task
from patchright.async_api import Error as PlaywrightError
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.circuit_breaker import record_failure, record_success
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from core.supabase import get_supabase_client
from models import ScrapeTaskArgs, ScrapeTaskResult
from scrapers.rumble import RumbleScraper
from tasks.scrape_helpers import (
    daily_budget_bytes,
    deactivate_channel_for_url,
    get_daily_bytes_used,
    has_retries_remaining_for_block,
    has_retries_remaining,
    log_scrape_task_attempt,
    release_keyword_discovery_hold,
    record_daily_bytes_used,
    retry_countdown_seconds,
)

logger = logging.getLogger(__name__)


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
    logger.info("Starting Rumble scrape: %s", channel_url)
    scraper = RumbleScraper()
    try:
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
            logger.warning("Could not record Rumble proxy byte usage: %s", exc)
        release_keyword_discovery_hold(scraper, channel_url)
        record_success("rumble")
        logger.info("Rumble scrape complete: %s", channel_url)
        return ScrapeTaskResult(
            status="success",
            channel_url=channel_url,
            data=result,
        ).model_dump(mode="json")
    except ScraperBlockedError as exc:
        if not has_retries_remaining_for_block(self):
            record_failure("rumble")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc)
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

        log_scrape_task_attempt(scraper, channel_url, "blocked", exc)
        logger.warning(
            "Rumble scrape blocked (attempt %d): %s - %s",
            self.request.retries + 1,
            channel_url,
            exc,
        )
        raise self.retry(
            exc=exc,
            countdown=retry_countdown_seconds(self),
        )
    except ScraperClassifiedError as exc:
        if exc.terminal and not exc.retryable:
            record_failure("rumble")
            deactivate_channel_for_url(scraper, channel_url)
            log_scrape_task_attempt(scraper, channel_url, "failed", exc)
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
            log_scrape_task_attempt(scraper, channel_url, "failed", exc)
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        log_scrape_task_attempt(scraper, channel_url, "retry", exc)
        raise self.retry(
            exc=exc,
            countdown=retry_countdown_seconds(self),
        )
    except (APIError, PlaywrightError, RuntimeError, TypeError, ValueError) as exc:
        if not has_retries_remaining(self):
            record_failure("rumble")
            log_scrape_task_attempt(scraper, channel_url, "failed", exc)
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

        log_scrape_task_attempt(scraper, channel_url, "retry", exc)
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
            log_scrape_task_attempt(scraper, channel_url, "failed", exc)
            logger.exception(
                "Rumble scrape failed with unexpected error after retries: %s",
                channel_url,
            )
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        log_scrape_task_attempt(scraper, channel_url, "retry", exc)
        logger.exception(
            "Rumble scrape failed with unexpected error (attempt %d): %s",
            self.request.retries + 1,
            channel_url,
        )
        raise self.retry(
            exc=exc,
            countdown=retry_countdown_seconds(self),
        )


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

    for url in urls:
        scrape_rumble_channel.delay(url)

    logger.info("Queued %d Rumble channel scrapes", len(urls))
    return {"queued": len(urls)}
