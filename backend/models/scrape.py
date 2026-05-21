"""Pydantic models for scrape logs, task responses, and health checks."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ScrapeLog(BaseModel):
    """A single scrape attempt log entry."""

    id: UUID
    channel_id: UUID
    attempted_at: datetime
    status: Literal["success", "blocked", "retry", "failed"]
    error_message: str | None = None

    model_config = {"from_attributes": True}


class ScrapeTaskResponse(BaseModel):
    """Response returned when a scrape job is triggered."""

    message: str
    task_id: str
    task_ids: list[str]
    triggered_at: datetime


class HealthResponse(BaseModel):
    """Response for the /health endpoint."""

    status: str
    timestamp: datetime
    supabase: bool
    redis: bool
    environment: str
