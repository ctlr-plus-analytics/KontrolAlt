"""Pydantic models for admin control-plane settings and actions."""

from datetime import datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AdminMeResponse(BaseModel):
    """Authenticated admin identity plus capabilities."""

    user_id: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class SystemSettingsResponse(BaseModel):
    """System-wide runtime settings."""

    daily_scrape_utc_time: str
    gate0_enabled: bool
    discovery_enabled: bool
    lookalike_enabled: bool
    scrape_platform_priority: list[str]
    scrape_only_new_or_missing_metrics: bool
    scrape_rescrape_min_hours: int
    weekly_velocity_enabled: bool
    weekly_velocity_utc_day: str
    weekly_velocity_utc_time: str
    velocity_weekly_min_avg_comments: float
    velocity_weekly_min_avg_views: float
    velocity_weekly_min_subscribers: int
    velocity_weekly_stale_hours: int
    scrape_dispatch_batch_size: int
    scrape_dispatch_pause_seconds: float
    scrape_run_max_channels: int
    scrape_daily_byte_budget_mb: int
    scrape_retry_base_delay_seconds: int
    scrape_retry_jitter_min: float
    scrape_retry_jitter_max: float
    scrape_circuit_breaker_fail_threshold: int
    scrape_circuit_breaker_window_seconds: int
    scrape_circuit_breaker_cooldown_seconds: int
    gate0_daily_queue_limit: int
    gate0_clean_recheck_days: int
    scraper_human_delay_min_seconds: float
    scraper_human_delay_max_seconds: float
    scraper_content_wait_min_bytes: int
    scraper_content_wait_timeout_seconds: float
    scraper_content_wait_poll_seconds: float
    discovery_serper_query_limit: int
    discovery_results_per_query: int
    discovery_max_pages_per_query: int
    discovery_insert_limit: int
    discovery_query_stagnation_limit: int
    discovery_global_stop_no_new: int
    discovery_max_feedback_terms: int
    discovery_new_scrape_limit: int
    discovery_channel_page_size: int
    discovery_verify_timeout_seconds: float
    version: int
    updated_at: datetime
    updated_by_email: str | None = None


class SystemSettingsPatchRequest(BaseModel):
    """Partial update payload for system settings."""

    daily_scrape_utc_time: str | None = None
    gate0_enabled: bool | None = None
    discovery_enabled: bool | None = None
    lookalike_enabled: bool | None = None
    scrape_platform_priority: list[Literal["rumble", "bitchute"]] | None = None
    scrape_only_new_or_missing_metrics: bool | None = None
    scrape_rescrape_min_hours: int | None = None
    weekly_velocity_enabled: bool | None = None
    weekly_velocity_utc_day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] | None = None
    weekly_velocity_utc_time: str | None = None
    velocity_weekly_min_avg_comments: float | None = None
    velocity_weekly_min_avg_views: float | None = None
    velocity_weekly_min_subscribers: int | None = None
    velocity_weekly_stale_hours: int | None = None
    scrape_dispatch_batch_size: int | None = None
    scrape_dispatch_pause_seconds: float | None = None
    scrape_run_max_channels: int | None = None
    scrape_daily_byte_budget_mb: int | None = None
    scrape_retry_base_delay_seconds: int | None = None
    scrape_retry_jitter_min: float | None = None
    scrape_retry_jitter_max: float | None = None
    scrape_circuit_breaker_fail_threshold: int | None = None
    scrape_circuit_breaker_window_seconds: int | None = None
    scrape_circuit_breaker_cooldown_seconds: int | None = None
    gate0_daily_queue_limit: int | None = None
    gate0_clean_recheck_days: int | None = None
    scraper_human_delay_min_seconds: float | None = None
    scraper_human_delay_max_seconds: float | None = None
    scraper_content_wait_min_bytes: int | None = None
    scraper_content_wait_timeout_seconds: float | None = None
    scraper_content_wait_poll_seconds: float | None = None
    discovery_serper_query_limit: int | None = None
    discovery_results_per_query: int | None = None
    discovery_max_pages_per_query: int | None = None
    discovery_insert_limit: int | None = None
    discovery_query_stagnation_limit: int | None = None
    discovery_global_stop_no_new: int | None = None
    discovery_max_feedback_terms: int | None = None
    discovery_new_scrape_limit: int | None = None
    discovery_channel_page_size: int | None = None
    discovery_verify_timeout_seconds: float | None = None
    expected_version: int

    @field_validator("daily_scrape_utc_time", "weekly_velocity_utc_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("daily_scrape_utc_time must be HH:MM in UTC.")
        hour, minute = parts
        if not hour.isdigit() or not minute.isdigit():
            raise ValueError("daily_scrape_utc_time must be HH:MM in UTC.")
        parsed = time(hour=int(hour), minute=int(minute))
        return parsed.strftime("%H:%M")

    @field_validator(
        "scrape_rescrape_min_hours",
        "scrape_dispatch_batch_size",
        "scrape_run_max_channels",
        "scrape_daily_byte_budget_mb",
        "scrape_retry_base_delay_seconds",
        "scrape_circuit_breaker_fail_threshold",
        "scrape_circuit_breaker_window_seconds",
        "scrape_circuit_breaker_cooldown_seconds",
        "gate0_daily_queue_limit",
        "gate0_clean_recheck_days",
        "scraper_content_wait_min_bytes",
        "discovery_serper_query_limit",
        "discovery_results_per_query",
        "discovery_max_pages_per_query",
        "discovery_insert_limit",
        "discovery_query_stagnation_limit",
        "discovery_global_stop_no_new",
        "discovery_max_feedback_terms",
        "discovery_new_scrape_limit",
        "discovery_channel_page_size",
        "velocity_weekly_min_subscribers",
        "velocity_weekly_stale_hours",
    )
    @classmethod
    def validate_non_negative_int(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("value must be non-negative")
        return value

    @field_validator(
        "velocity_weekly_min_avg_comments",
        "velocity_weekly_min_avg_views",
        "scrape_dispatch_pause_seconds",
        "scrape_retry_jitter_min",
        "scrape_retry_jitter_max",
        "scraper_human_delay_min_seconds",
        "scraper_human_delay_max_seconds",
        "scraper_content_wait_timeout_seconds",
        "scraper_content_wait_poll_seconds",
        "discovery_verify_timeout_seconds",
    )
    @classmethod
    def validate_non_negative_float(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("value must be non-negative")
        return value

    @field_validator(
        "scrape_dispatch_batch_size",
        "scrape_retry_base_delay_seconds",
        "scrape_circuit_breaker_fail_threshold",
        "scrape_circuit_breaker_window_seconds",
        "scrape_circuit_breaker_cooldown_seconds",
        "discovery_results_per_query",
        "discovery_max_pages_per_query",
        "discovery_query_stagnation_limit",
        "discovery_global_stop_no_new",
        "discovery_channel_page_size",
    )
    @classmethod
    def validate_positive_int(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("value must be at least 1")
        return value

    @model_validator(mode="after")
    def validate_ranges(self) -> "SystemSettingsPatchRequest":
        if (
            self.scrape_retry_jitter_min is not None
            and self.scrape_retry_jitter_max is not None
            and self.scrape_retry_jitter_min > self.scrape_retry_jitter_max
        ):
            raise ValueError("scrape_retry_jitter_min cannot exceed max")
        if (
            self.scraper_human_delay_min_seconds is not None
            and self.scraper_human_delay_max_seconds is not None
            and self.scraper_human_delay_min_seconds
            > self.scraper_human_delay_max_seconds
        ):
            raise ValueError("human delay min cannot exceed max")
        return self


class AdminTaskTriggerRequest(BaseModel):
    """Optional metadata for manual task triggers."""

    reason: str | None = None


class AdminTaskTriggerResponse(BaseModel):
    """Response when one or more tasks are queued."""

    message: str
    task_id: str
    task_ids: list[str]
    triggered_at: datetime


class Gate0BatchTriggerRequest(BaseModel):
    """Queue Gate 0 checks for selected channels."""

    channel_ids: list[UUID]
    reason: str | None = None


class Gate0BatchTriggerResponse(BaseModel):
    """Result of batch Gate 0 queue operation."""

    queued: int
    task_ids: list[str]
    triggered_at: datetime


class AdminTaskStatusResponse(BaseModel):
    """Task execution status from Celery backend."""

    task_id: str
    state: str
    result: object | None = None
    date_done: str | None = None


class AdminAuditRecord(BaseModel):
    """Single admin audit row."""

    id: UUID
    actor_user_id: UUID
    actor_email: str | None = None
    action: str
    target: str
    old_value: dict | None = None
    new_value: dict | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class PaginatedAdminAuditResponse(BaseModel):
    """Paginated admin audit list."""

    data: list[AdminAuditRecord]
    total: int
    page: int
    page_size: int
