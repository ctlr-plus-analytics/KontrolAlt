"""Celery tasks: scrape Substack channels."""

import logging
import random
from urllib.parse import urlsplit

from celery import Task
from playwright.async_api import Error as PlaywrightError
from postgrest.exceptions import APIError

from worker import celery_app
from core.exceptions import CloudflareBlockError, ScraperBlockedError, ScraperClassifiedError
from core.supabase import get_supabase_client
from core.runtime_settings import get_runtime_settings
from models import ScrapeTaskArgs, ScrapeTaskResult
from scrapers.substack import SubstackScraper
from tasks.scrape_failure_policy import (
    handle_blocked_scrape_error,
    handle_classified_scrape_error,
    handle_retryable_scrape_error,
)
from tasks.scrape_helpers import (
    acquire_scrape_lock,
    daily_budget_bytes,
    get_daily_bytes_used,
    release_global_slot,
    release_keyword_discovery_hold,
    release_platform_slot,
    release_scrape_lock,
    record_daily_bytes_used,
    try_acquire_global_slot,
    try_acquire_platform_slot,
)
from tasks.task_queues import QUEUE_SUBSTACK

logger = logging.getLogger(__name__)


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
    queue="substack",
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

    if not acquire_scrape_lock(channel_url):
        logger.info("Skipping duplicate in-flight Substack scrape: %s", channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
            error="Duplicate in-flight scrape skipped",
        ).model_dump(mode="json")

    runtime = get_runtime_settings()
    if not try_acquire_global_slot(runtime.scrape_global_slot_limit):
        release_scrape_lock(channel_url)
        scrape_substack_channel.apply_async(
            args=[channel_url],
            countdown=random.randint(20, 60),
            queue=QUEUE_SUBSTACK,
        )
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
        ).model_dump(mode="json")

    substack_limit = runtime.scrape_platform_slot_limit_substack
    if substack_limit == 0:
        release_global_slot()
        release_scrape_lock(channel_url)
        return ScrapeTaskResult(
            status="skipped",
            channel_url=channel_url,
        ).model_dump(mode="json")

    if not try_acquire_platform_slot("substack", substack_limit):
        release_global_slot()
        release_scrape_lock(channel_url)
        scrape_substack_channel.apply_async(
            args=[channel_url],
            countdown=random.randint(30, 90),
            queue=QUEUE_SUBSTACK,
        )
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
        from core.browser_pool import worker_pool
        result = worker_pool.run(scraper.scrape(channel_url))
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
        logger.info("Substack scrape complete: %s", channel_url)
        return ScrapeTaskResult(
            status="success",
            channel_url=channel_url,
            data=result,
        ).model_dump(mode="json")

    except CloudflareBlockError as exc:
        return handle_blocked_scrape_error(
            platform="substack",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )

    except ScraperBlockedError as exc:
        return handle_blocked_scrape_error(
            platform="substack",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )

    except ScraperClassifiedError as exc:
        return handle_classified_scrape_error(
            platform="substack",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )

    except (APIError, PlaywrightError, RuntimeError, TypeError, ValueError) as exc:
        return handle_retryable_scrape_error(
            platform="substack",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
        )

    except Exception as exc:
        return handle_retryable_scrape_error(
            platform="substack",
            scraper=scraper,
            channel_url=channel_url,
            error=exc,
            task=self,
            result_factory=ScrapeTaskResult,
            logger=logger,
            unexpected=True,
        )
    finally:
        release_platform_slot("substack")
        release_global_slot()
        release_scrape_lock(channel_url)


@celery_app.task(name="scraper.tasks.scrape_substack_all", queue="substack")
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

    for i, url in enumerate(urls):
        stagger_s = int(i * random.uniform(4, 10))
        scrape_substack_channel.apply_async(
            args=[url],
            countdown=stagger_s,
            queue=QUEUE_SUBSTACK,
        )

    logger.info("Queued %d Substack channel scrapes", len(urls))
    return {"queued": len(urls)}
