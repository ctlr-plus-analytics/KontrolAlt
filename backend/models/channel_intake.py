"""Pydantic models for channel intake and seed-name resolution flows."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from models.channel import Platform


class IntakeStatus(str, Enum):
    """Outcome for one intake record."""

    inserted = "inserted"
    duplicate = "duplicate"
    invalid = "invalid"


class ManualChannelIntakeRequest(BaseModel):
    """Request body for manually adding a single channel."""

    platform: Platform
    channel_url: str = Field(min_length=1)
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    trigger_scrape_now: bool = False

    @field_validator("channel_url")
    @classmethod
    def validate_channel_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("channel_url is required")
        return cleaned

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return sorted({tag.strip() for tag in value if tag.strip()})


class BulkChannelIntakeRequest(BaseModel):
    """Request body for bulk URL intake."""

    urls_text: str = Field(min_length=1)
    trigger_scrape_now: bool = False


class IntakeRecordResult(BaseModel):
    """Result for one intake URL."""

    input_value: str
    status: IntakeStatus
    channel_url: str | None = None
    platform: Platform | None = None
    reason: str | None = None
    channel_id: UUID | None = None
    scrape_task_id: str | None = None


class IntakeSummaryResponse(BaseModel):
    """Summary for manual/bulk/confirm channel intake operations."""

    message: str
    inserted: int
    duplicates: int
    invalid: int
    records: list[IntakeRecordResult]


class ResolverSeedRequest(BaseModel):
    """Request body for resolving seed creator names to channel URLs."""

    seed_names: list[str]
    limit_per_seed: int = 5

    @field_validator("seed_names")
    @classmethod
    def validate_seed_names(cls, value: list[str]) -> list[str]:
        cleaned = [name.strip() for name in value if name.strip()]
        if not cleaned:
            raise ValueError("At least one creator name is required")
        if len(cleaned) > 3:
            raise ValueError("Maximum 3 creator names allowed")
        return cleaned

    @field_validator("limit_per_seed")
    @classmethod
    def validate_limit_per_seed(cls, value: int) -> int:
        if value < 1 or value > 10:
            raise ValueError("limit_per_seed must be between 1 and 10")
        return value


class ResolvedChannelCandidate(BaseModel):
    """One resolver match candidate."""

    platform: Platform
    channel_url: str
    channel_name: str
    confidence: float
    source: str


class ResolverSeedResult(BaseModel):
    """Resolver output for one seed name."""

    seed_name: str
    candidates: list[ResolvedChannelCandidate]


class ResolverResponse(BaseModel):
    """Resolver response for all submitted seeds."""

    results: list[ResolverSeedResult]
    unresolved: list[str]


class ResolverConfirmSelection(BaseModel):
    """One user-confirmed resolver selection."""

    seed_name: str
    platform: Platform
    channel_url: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("channel_url")
    @classmethod
    def validate_channel_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("channel_url is required")
        return cleaned

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return sorted({tag.strip() for tag in value if tag.strip()})


class ResolverConfirmRequest(BaseModel):
    """Request body for inserting user-confirmed resolver results."""

    selections: list[ResolverConfirmSelection]
    trigger_scrape_now: bool = False

    @field_validator("selections")
    @classmethod
    def validate_selections(cls, value: list[ResolverConfirmSelection]) -> list[ResolverConfirmSelection]:
        if not value:
            raise ValueError("At least one selection is required")
        return value

