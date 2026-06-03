"""Pydantic models for Channel entities."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from pydantic import model_validator

from models.gate0 import Gate0Result
from models.scrape import ScrapeLog
from models.velocity import VelocityScore


class Platform(str, Enum):
    """Supported scraping platforms."""

    rumble = "rumble"
    substack = "substack"


class CommentTier(str, Enum):
    """Engagement tier based on average comment count."""

    active = "active"
    sweet_spot = "sweet_spot"
    whale = "whale"


class Gate0Status(str, Enum):
    """Gate 0 compliance check status."""

    clean = "clean"
    needs_review = "needs_review"
    dirty = "dirty"
    pending = "pending"
    unchecked = "unchecked"


class DoNotContactStatus(str, Enum):
    """Manual outreach suppression status for a channel."""

    hired_and_canceled = "Hired and Canceled"
    current_partner = "Current Partner"


class DiscoveryStatus(str, Enum):
    """Channel discovery lifecycle status."""

    new = "new"
    queued = "queued"
    scraped = "scraped"
    failed = "failed"
    dead = "dead"
    blocked = "blocked"


class RecentVideo(BaseModel):
    """Structured recent video metadata for channel detail rendering."""

    title: str
    views: int | None = None
    comments: int | None = None
    published_at: datetime | None = None
    url: str | None = None


class Channel(BaseModel):
    """Full channel representation from the database."""

    id: UUID
    platform: Platform
    channel_url: str
    name: str
    description: str = ""
    subscriber_count: int | None = None
    avg_views: float | None = None
    avg_comments: float | None = None
    comment_tier: CommentTier | None = None
    posts_per_week: float | None = None
    last_active_date: date | None = None
    contact_info: list[str] = Field(default_factory=list)
    niche_tags: list[str] = Field(default_factory=list)
    video_titles: list[str] = Field(default_factory=list)
    recent_videos: list[RecentVideo] = Field(default_factory=list)
    is_active: bool = True
    gate0_status: Gate0Status = Gate0Status.unchecked
    gate0_checked_at: datetime | None = None
    secondary_urls: list[str] = Field(default_factory=list)
    do_not_contact: DoNotContactStatus | None = None
    has_been_scraped: bool = False
    discovery_status: DiscoveryStatus = DiscoveryStatus.new
    last_scrape_error: str | None = None
    dashboard_metrics_complete: bool = False
    dashboard_url_valid: bool = False
    dashboard_eligible: bool = False
    engagement_rate: float | None = None

    # Consolidated velocity fields
    view_velocity_30d: float | None = None
    view_velocity_90d: float | None = None
    comment_velocity_30d: float | None = None
    comment_velocity_90d: float | None = None
    velocity_computed_at: datetime | None = None

    # Consolidated Gate 0 cache fields
    gate0_result_id: UUID | None = None
    gate0_search_query: str | None = None
    gate0_result_status: str | None = None
    gate0_flagged_brand: str | None = None
    gate0_source_url: str | None = None

    ai_summary: str | None = None
    ai_channel_report: str | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChannelWithMetrics(Channel):
    """Channel enriched with joined velocity and Gate 0 data."""

    velocity: VelocityScore | None = None
    gate0: Gate0Result | None = None
    scrape_logs: list[ScrapeLog] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChannelFilters(BaseModel):
    platform: Platform | None = None
    comment_tier: CommentTier | None = None
    gate0_statuses: list[Gate0Status] | None = None
    category_tags: list[str] | None = None
    niche_tags: list[str] | None = None
    search_query: str | None = None
    min_subscriber_count: int | None = None
    max_subscriber_count: int | None = None
    min_avg_views: float | None = None
    max_avg_views: float | None = None
    min_avg_comments: float | None = None
    max_avg_comments: float | None = None
    inactive_filter: bool = False
    last_active_from: date | None = None
    last_active_to: date | None = None
    incomplete_only: bool = False
    sort_by: str = "avg_comments"
    sort_order: str = "desc"
    page: int = 1
    page_size: int = 50

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        allowed = {
            "subscriber_count",
            "avg_views",
            "avg_comments",
            "engagement_rate",
            "view_velocity_30d",
            "view_velocity_90d",
            "last_active_date",
        }
        if v not in allowed:
            raise ValueError(f"sort_by must be one of {allowed}")
        return v

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        if v not in {"asc", "desc"}:
            raise ValueError("sort_order must be asc or desc")
        return v

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        if v > 100:
            raise ValueError("page_size cannot exceed 100")
        if v < 1:
            raise ValueError("page_size must be at least 1")
        return v

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int) -> int:
        if v < 1:
            raise ValueError("page must be at least 1")
        return v

    @field_validator("search_query")
    @classmethod
    def validate_search_query(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("category_tags", "niche_tags", mode="before")
    @classmethod
    def validate_category_tags(cls, v: list[str] | str | None) -> list[str] | None:
        if v is None:
            return None
        values = v if isinstance(v, list) else [v]
        cleaned: list[str] = []
        for raw in values:
            tag = str(raw).strip()
            if tag and tag not in cleaned:
                cleaned.append(tag)
        return cleaned or None

    @model_validator(mode="after")
    def normalize_legacy_niche_tags(self) -> "ChannelFilters":
        if self.category_tags is None and self.niche_tags is not None:
            self.category_tags = self.niche_tags
        if self.niche_tags is None and self.category_tags is not None:
            self.niche_tags = self.category_tags
        return self

    @field_validator("gate0_statuses", mode="before")
    @classmethod
    def validate_gate0_statuses(
        cls, v: list[Gate0Status] | Gate0Status | str | None
    ) -> list[Gate0Status] | None:
        if v is None:
            return None
        values = v if isinstance(v, list) else [v]
        parsed: list[Gate0Status] = []
        for raw in values:
            status = raw if isinstance(raw, Gate0Status) else Gate0Status(str(raw).strip())
            if status not in parsed:
                parsed.append(status)
        return parsed or None

    @field_validator(
        "min_subscriber_count",
        "max_subscriber_count",
        mode="before",
    )
    @classmethod
    def validate_non_negative_int_bounds(
        cls, v: int | str | None
    ) -> int | None:
        if v in (None, ""):
            return None
        numeric = int(v)
        if numeric < 0:
            raise ValueError("metric bounds must be non-negative")
        return numeric

    @field_validator(
        "min_avg_views",
        "max_avg_views",
        "min_avg_comments",
        "max_avg_comments",
        mode="before",
    )
    @classmethod
    def validate_non_negative_float_bounds(
        cls, v: float | str | None
    ) -> float | None:
        if v in (None, ""):
            return None
        numeric = float(v)
        if numeric < 0:
            raise ValueError("metric bounds must be non-negative")
        return numeric

    @model_validator(mode="after")
    def validate_metric_ranges(self) -> "ChannelFilters":
        if (
            self.min_subscriber_count is not None
            and self.max_subscriber_count is not None
            and self.min_subscriber_count > self.max_subscriber_count
        ):
            raise ValueError(
                "min_subscriber_count cannot exceed max_subscriber_count"
            )
        if (
            self.min_avg_views is not None
            and self.max_avg_views is not None
            and self.min_avg_views > self.max_avg_views
        ):
            raise ValueError("min_avg_views cannot exceed max_avg_views")
        if (
            self.min_avg_comments is not None
            and self.max_avg_comments is not None
            and self.min_avg_comments > self.max_avg_comments
        ):
            raise ValueError(
                "min_avg_comments cannot exceed max_avg_comments"
            )
        return self


class PaginatedChannels(BaseModel):
    """Paginated response wrapper for channel listings."""

    data: list[ChannelWithMetrics]
    total: int
    page: int
    page_size: int


class CategoryTagCount(BaseModel):
    """Category tag with total channel count."""

    tag: str
    count: int


class CategoryTagListResponse(BaseModel):
    """Distinct category tag values used for filter options."""

    tags: list[str]
    tag_counts: list[CategoryTagCount] = Field(default_factory=list)


# Backward-compat aliases
NicheTagCount = CategoryTagCount
NicheTagListResponse = CategoryTagListResponse


class Gate0StatusCount(BaseModel):
    """Gate 0 status with total channel count."""

    status: Gate0Status
    count: int


class Gate0StatusListResponse(BaseModel):
    """Gate 0 status options with counts for dropdown filters."""

    status_counts: list[Gate0StatusCount] = Field(default_factory=list)


class ChannelDeleteResponse(BaseModel):
    """Response payload for channel delete operations."""

    message: str
    channel_id: UUID


class ChannelDoNotContactUpdateRequest(BaseModel):
    """Request payload for setting or clearing do-not-contact state."""

    do_not_contact: DoNotContactStatus | None
