"""Shared failure handling for platform scrape Celery tasks."""

from __future__ import annotations

import logging
from collections.abc import Callable

from celery import Task
from core.exceptions import (
    CloudflareBlockError,
    ScraperBlockedError,
    ScraperClassifiedError,
)
from core.proxy import proxy_session_manager
from scrapers.base import BaseScraper

from tasks.scrape_helpers import (
    blocked_retry_countdown_seconds,
    deactivate_channel_for_url,
    has_retries_remaining,
    has_retries_remaining_for_block,
    log_scrape_task_attempt,
    retry_countdown_seconds,
)

KEEP_QUEUED_AFTER_FINAL_RETRY: dict[str, frozenset[str]] = {
    "substack": frozenset(
        {
            "parse_missing_subscriber_count",
            "parse_missing_avg_views",
            "parse_missing_avg_comments",
            "parse_missing_posts_per_week",
            "parse_missing_last_active_date",
        }
    ),
    "rumble": frozenset(),
}


def _task_result(
    result_factory: Callable[..., object],
    *,
    status: str,
    channel_url: str,
    error: Exception,
) -> dict[str, object]:
    return result_factory(
        status=status,
        channel_url=channel_url,
        error=str(error),
    ).model_dump(mode="json")


def _mark_proxy_session_blocked(scraper: BaseScraper, channel_url: str) -> None:
    session_key = getattr(scraper, "_session_key", None)
    session_id = proxy_session_manager.extract_session_id(session_key)
    proxy_session_manager.mark_blocked(session_id or (session_key or channel_url))


def handle_blocked_scrape_error(
    *,
    platform: str,
    scraper: BaseScraper,
    channel_url: str,
    error: ScraperBlockedError,
    task: Task,
    result_factory: Callable[..., object],
    logger: logging.Logger,
) -> dict[str, object]:
    """Retry or finalize a block/challenge scrape failure."""
    if isinstance(error, CloudflareBlockError):
        if error.rotation_helps:
            _mark_proxy_session_blocked(scraper, channel_url)
    else:
        _mark_proxy_session_blocked(scraper, channel_url)

    if not has_retries_remaining_for_block(task):
        log_scrape_task_attempt(scraper, channel_url, "failed", error, task)
        logger.error(
            "%s scrape blocked through final retry: %s - %s",
            platform.title(),
            channel_url,
            error,
        )
        return _task_result(
            result_factory,
            status="failed",
            channel_url=channel_url,
            error=error,
        )

    log_scrape_task_attempt(scraper, channel_url, "blocked", error, task)
    logger.warning(
        "%s scrape blocked (attempt %d): %s - %s",
        platform.title(),
        int(task.request.retries or 0) + 1,
        channel_url,
        error,
    )
    raise task.retry(exc=error, countdown=blocked_retry_countdown_seconds(task))


def handle_classified_scrape_error(
    *,
    platform: str,
    scraper: BaseScraper,
    channel_url: str,
    error: ScraperClassifiedError,
    task: Task,
    result_factory: Callable[..., object],
    logger: logging.Logger,
) -> dict[str, object]:
    """Retry, deactivate, or finalize a classified scrape failure."""
    if error.terminal and not error.retryable:
        deactivate_channel_for_url(scraper, channel_url)
        log_scrape_task_attempt(scraper, channel_url, "failed", error, task)
        logger.error(
            "%s scrape terminal classified failure: %s - %s",
            platform.title(),
            channel_url,
            error,
        )
        return _task_result(
            result_factory,
            status="failed",
            channel_url=channel_url,
            error=error,
        )

    if not has_retries_remaining(task):
        keep_queued_codes = KEEP_QUEUED_AFTER_FINAL_RETRY.get(platform, frozenset())
        final_log_status = (
            "retry" if error.reason_code in keep_queued_codes else "failed"
        )
        log_scrape_task_attempt(scraper, channel_url, final_log_status, error, task)
        logger.error(
            "%s scrape classified failure after retries: %s - %s",
            platform.title(),
            channel_url,
            error,
        )
        return _task_result(
            result_factory,
            status="failed",
            channel_url=channel_url,
            error=error,
        )

    log_scrape_task_attempt(scraper, channel_url, "retry", error, task)
    raise task.retry(exc=error, countdown=retry_countdown_seconds(task))


def handle_retryable_scrape_error(
    *,
    platform: str,
    scraper: BaseScraper,
    channel_url: str,
    error: Exception,
    task: Task,
    result_factory: Callable[..., object],
    logger: logging.Logger,
    unexpected: bool = False,
) -> dict[str, object]:
    """Retry or finalize a generic scrape failure."""
    if not has_retries_remaining(task):
        log_scrape_task_attempt(scraper, channel_url, "failed", error, task)
        if unexpected:
            logger.exception(
                "%s scrape failed with unexpected error after retries: %s",
                platform.title(),
                channel_url,
            )
        else:
            logger.error(
                "%s scrape permanently failed after retries: %s - %s",
                platform.title(),
                channel_url,
                error,
            )
        return _task_result(
            result_factory,
            status="failed",
            channel_url=channel_url,
            error=error,
        )

    log_scrape_task_attempt(scraper, channel_url, "retry", error, task)
    if unexpected:
        logger.exception(
            "%s scrape failed with unexpected error (attempt %d): %s",
            platform.title(),
            int(task.request.retries or 0) + 1,
            channel_url,
        )
    else:
        logger.error(
            "%s scrape failed (attempt %d): %s - %s",
            platform.title(),
            int(task.request.retries or 0) + 1,
            channel_url,
            error,
        )
    raise task.retry(exc=error, countdown=retry_countdown_seconds(task))
