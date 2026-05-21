"""Pydantic models for admin control-plane settings and actions."""

from datetime import datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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
    expected_version: int

    @field_validator("daily_scrape_utc_time")
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
