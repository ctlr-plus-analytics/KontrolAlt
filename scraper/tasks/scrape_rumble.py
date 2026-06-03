"""Celery tasks: scrape Rumble channels."""

import logging
import random
from urllib.parse import urlsplit
from collections import deque


from celery import Task
from playwright.async_api import Error as PlaywrightError
from postgrest.exceptions import APIError

from worker import celery_app
from core.exceptions import CloudflareBlockError, ScraperBlockedError, ScraperClassifiedError
from core.supabase import get_supabase_client
from core.runtime_settings import get_runtime_settings
from models import ScrapeTaskArgs, ScrapeTaskResult
from scrapers.rumble import RumbleScraper
from tasks.scrape_failure_policy import (
    handle_blocked_scrape_error,
    handle_classified_scrape_error,
    handle_retryable_scrape_error,
)
from tasks.scrape_helpers import (
    acquire_scrape_lock,
    daily_budget_bytes,
    get_daily_bytes_used,
    release_keyword_discovery_hold,
    release_scrape_lock,
    record_daily_bytes_used,
    try_acquire_global_slot,
    try_acquire_platform_slot,
    release_global_slot,
    release_platform_slot,
)
from tasks.task_queues import QUEUE_RUMBLE

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
    max_retries=get_runtime_settings().scrape_run_max_retries_per_channel,
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
        scraper = RumbleScraper()
        return handle_classified_scrape_error(
            platform="rumble",
            scraper=scraper,
            channel_url=channel_url,
            error=ScraperClassifiedError(
                "unsupported_rumble_url_shape",
                "Unsupported Rumble URL shape; expected /c/<slug> or /user/<slug>",
                terminal=True,
                retryable=False,
            ),
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )
    logger.info("Starting Rumble scrape: %s", channel_url)
    if not acquire_scrape_lock(channel_url):
        logger.info("Skipping duplicate in-flight Rumble scrape: %s", channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
            error="Duplicate in-flight scrape skipped",
        ).model_dump(mode="json")
    runtime = get_runtime_settings()
    if not try_acquire_global_slot(runtime.scrape_global_slot_limit):
        release_scrape_lock(channel_url)
        scrape_rumble_channel.apply_async(
            args=[channel_url],
            countdown=random.randint(20, 60),
            queue=QUEUE_RUMBLE,
        )
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
        ).model_dump(mode="json")
    rumble_limit = runtime.scrape_platform_slot_limit_rumble
    if rumble_limit == 0:
        release_global_slot()
        release_scrape_lock(channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
        ).model_dump(mode="json")
    if not try_acquire_platform_slot("rumble", rumble_limit):
        release_global_slot()
        release_scrape_lock(channel_url)
        scrape_rumble_channel.apply_async(
            args=[channel_url],
            countdown=random.randint(30, 90),
            queue=QUEUE_RUMBLE,
        )
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
        ).model_dump(mode="json")
    scraper = RumbleScraper()
    try:
        scraper._session_key = (
            f"{channel_url}|attempt:{int(self.request.retries or 0)}|"
            f"task:{self.request.id}"
        )
        from core.browser_pool import worker_pool
        result = worker_pool.run(scraper.scrape(channel_url))
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
        logger.info("Rumble scrape complete: %s", channel_url)
        return ScrapeTaskResult(
            status="success",
            channel_url=channel_url,
            data=result,
        ).model_dump(mode="json")
    except CloudflareBlockError as exc:
        return handle_blocked_scrape_error(
            platform="rumble",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )
    except ScraperBlockedError as exc:
        return handle_blocked_scrape_error(
            platform="rumble",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )
    except ScraperClassifiedError as exc:
        return handle_classified_scrape_error(
            platform="rumble",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )
    except (APIError, PlaywrightError, RuntimeError, TypeError, ValueError) as exc:
        return handle_retryable_scrape_error(
            platform="rumble",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )
    except Exception as exc:
        return handle_retryable_scrape_error(
            platform="rumble",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
            unexpected=True,
        )
    finally:
        release_platform_slot("rumble")
        release_global_slot()
        release_scrape_lock(channel_url)


@celery_app.task(name="scraper.tasks.scrape_rumble_all")
def scrape_rumble_all(never_scraped_only: bool = True) -> dict[str, object]:
    """Fetch all Rumble channel URLs and dispatch individual scrape tasks.

    Returns:
        Dict with count of queued tasks.
    """
    logger.info("Starting batch Rumble scrape (never_scraped_only=%s)", never_scraped_only)
    if get_runtime_settings().scrape_platform_slot_limit_rumble == 0:
        logger.info("Skipping batch Rumble scrape: platform disabled (slot limit=0)")
        return {"queued": 0, "skipped": "platform_disabled"}
    try:
        client = get_supabase_client()
        query = (
            client.table("channels")
            .select("channel_url")
            .eq("platform", "rumble")
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
        logger.error("Failed to fetch Rumble channel URLs: %s", exc)
        return {"queued": 0, "error": str(exc)}

    for i, url in enumerate(urls):
        # Stagger each task by 4-10 s per position. Rumble is less aggressive
        # still sensitive to simultaneous request spikes.
        stagger_s = int(i * random.uniform(4, 10))
        scrape_rumble_channel.apply_async(
            args=[url],
            countdown=stagger_s,
            queue=QUEUE_RUMBLE,
        )

    logger.info("Queued %d Rumble channel scrapes", len(urls))
    return {"queued": len(urls)}
