"""Celery tasks: scrape Substack channels."""

import asyncio
import logging
import random
from urllib.parse import urlsplit

from celery import Task
from playwright.async_api import Error as PlaywrightError
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.circuit_breaker import is_open, record_failure, record_success
from core.exceptions import CloudflareBlockError, ScraperBlockedError, ScraperClassifiedError
from core.proxy import proxy_session_manager
from core.supabase import get_supabase_client
from core.runtime_settings import get_runtime_settings
from models import ScrapeTaskArgs, ScrapeTaskResult
from scrapers.substack import SubstackScraper
from tasks.scrape_helpers import (
    acquire_scrape_lock,
    blocked_retry_countdown_seconds,
    daily_budget_bytes,
    deactivate_channel_for_url,
    get_daily_bytes_used,
    has_retries_remaining,
    has_retries_remaining_for_block,
    log_scrape_task_attempt,
    release_keyword_discovery_hold,
    release_scrape_lock,
    retry_countdown_seconds,
    record_daily_bytes_used,
)

logger = logging.getLogger(__name__)

_NON_BREAKER_REASON_CODES = {
    "substack_handle_redirected_to_search",
    "substack_see_subscribers_stub",
    "substack_profile_not_found",
    "substack_too_few_posts",
}


def _should_trip_substack_breaker(exc: ScraperClassifiedError) -> bool:
    """Return True when a classified Substack failure should count toward breaker."""
    return exc.reason_code not in _NON_BREAKER_REASON_CODES


def _is_supported_substack_channel_url(channel_url: str) -> bool:
    parsed = urlsplit(channel_url.strip())
    host = (parsed.hostname or "").lower()
    if host not in {"substack.com", "www.substack.com"}:
        return False
    path = parsed.path.rstrip("/")
    return path.startswith("/@") and len(path) > 2


@celery_app.task(
    bind=True,
    max_retries=get_runtime_settings().scrape_run_max_retries_per_channel,
    default_retry_delay=60,
    name="scraper.tasks.scrape_substack_channel",
)
def scrape_substack_channel(self: Task, channel_url: str) -> dict[str, object]:
    args = ScrapeTaskArgs(channel_url=channel_url)
    channel_url = args.channel_url
    if not _is_supported_substack_channel_url(channel_url):
        logger.warning("Skipping unsupported Substack URL: %s", channel_url)
        return ScrapeTaskResult(
            status="failed",
            channel_url=channel_url,
            error="Unsupported Substack URL shape; expected /@<handle>",
        ).model_dump(mode="json")

    logger.info("Starting Substack scrape: %s", channel_url)
    if is_open("substack"):
        logger.warning(
            "Skipping Substack scrape due to open circuit breaker: %s",
            channel_url,
        )
        return ScrapeTaskResult(
            status="failed",
            channel_url=channel_url,
            error="Circuit breaker open for substack",
        ).model_dump(mode="json")

    if not acquire_scrape_lock(channel_url):
        logger.info("Skipping duplicate in-flight Substack scrape: %s", channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
            error="Duplicate in-flight scrape skipped",
        ).model_dump(mode="json")

    if get_runtime_settings().scrape_platform_slot_limit_substack == 0:
        release_scrape_lock(channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
        ).model_dump(mode="json")

    scraper = SubstackScraper()
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
            logger.warning("Could not record Substack proxy byte usage: %s", exc)

        storage_url = result.get("channel_url", channel_url) if isinstance(result, dict) else channel_url
        release_keyword_discovery_hold(scraper, storage_url)
        record_success("substack")
        logger.info("Substack scrape complete: %s", channel_url)
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
            record_failure("substack")
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
            record_failure("substack")
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

    except ScraperClassifiedError as exc:
        if exc.terminal and not exc.retryable:
            if _should_trip_substack_breaker(exc):
                record_failure("substack")
            deactivate_channel_for_url(scraper, channel_url)
            log_scrape_task_attempt(scraper, channel_url, "failed", exc, self)
            return ScrapeTaskResult(
                status="failed",
                channel_url=channel_url,
                error=str(exc),
            ).model_dump(mode="json")

        if not has_retries_remaining(self):
            if _should_trip_substack_breaker(exc):
                record_failure("substack")
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
            record_failure("substack")
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

    except Exception as exc:
        if not has_retries_remaining(self):
            record_failure("substack")
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
    finally:
        release_scrape_lock(channel_url)


@celery_app.task(name="scraper.tasks.scrape_substack_all")
def scrape_substack_all(never_scraped_only: bool = True) -> dict[str, object]:
    logger.info("Starting batch Substack scrape (never_scraped_only=%s)", never_scraped_only)
    if get_runtime_settings().scrape_platform_slot_limit_substack == 0:
        logger.info("Skipping batch Substack scrape: platform disabled (slot limit=0)")
        return {"queued": 0, "skipped": "platform_disabled"}
    try:
        client = get_supabase_client()
        query = (
            client.table("channels")
            .select("channel_url")
            .eq("platform", "substack")
            .eq("is_active", True)
        )
        if never_scraped_only:
            query = (
                query
                .is_("subscriber_count", "null")
                .is_("avg_views", "null")
                .is_("avg_comments", "null")
                .eq("has_been_scraped", False)
                .in_("discovery_status", ["new", "queued"])
                .eq("dashboard_metrics_complete", False)
                .eq("dashboard_url_valid", True)
                .eq("dashboard_eligible", False)
            )
        result = query.execute()
        urls = [row["channel_url"] for row in (result.data or [])]
    except APIError as exc:
        logger.error("Failed to fetch Substack channel URLs: %s", exc)
        return {"queued": 0, "error": str(exc)}

    if is_open("substack"):
        logger.warning(
            "Skipping batch Substack scrape dispatch due to open circuit breaker"
        )
        return {"queued": 0, "skipped": "circuit_breaker_open"}

    for i, url in enumerate(urls):
        stagger_s = int(i * random.uniform(4, 10))
        scrape_substack_channel.apply_async(args=[url], countdown=stagger_s)

    logger.info("Queued %d Substack channel scrapes", len(urls))
    return {"queued": len(urls)}
