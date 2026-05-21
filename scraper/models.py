"""Pydantic models shared across scraper tasks and services."""

from pydantic import BaseModel, Field


class ChannelSnapshotData(BaseModel):
    """Row payload for channel_snapshots inserts."""

    channel_id: str
    scraped_at: str
    subscriber_count: int | None = None
    avg_views: int | None = None
    avg_comments: int | None = None


class ScrapeTaskArgs(BaseModel):
    """Validated input for a scrape task."""

    channel_url: str = Field(min_length=1)


class ScrapeTaskResult(BaseModel):
    """Standard response payload for scrape tasks."""

    status: str
    channel_url: str
    data: dict[str, object] | None = None
    error: str | None = None


class VelocityTaskResult(BaseModel):
    """Response payload for per-channel velocity computations."""

    status: str
    channel_id: str
    computed_at: str
    view_velocity_30d: float | None = None
    view_velocity_90d: float | None = None
    comment_velocity_30d: float | None = None
    comment_velocity_90d: float | None = None


class Gate0TaskResult(BaseModel):
    """Response payload for Gate 0 checks."""

    channel_id: str
    skipped: bool = False
    reason: str | None = None
    checked_at: str | None = None
    search_query: str | None = None
    result_status: str | None = None
    flagged_brand: str | None = None
    source_url: str | None = None


class LookalikeTaskResult(BaseModel):
    """Response payload for lookalike discovery tasks."""

    matches_found: int
    error: str | None = None
