"""Pydantic models for LookalikeMatch and SeedCreator entities."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, field_validator

from models.channel import Channel


class MatchType(str, Enum):
    """How a lookalike match was discovered."""

    guest_appearance = "guest_appearance"
    niche_overlap = "niche_overlap"


class SeedCreator(BaseModel):
    """A seed creator entered by a user for lookalike search."""

    id: UUID
    user_id: UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LookalikeMatch(BaseModel):
    """A discovered lookalike match between a seed and a channel."""

    id: UUID
    seed_id: UUID
    matched_channel_id: UUID
    match_type: MatchType
    match_detail: str | None = None
    found_at: datetime
    channel: Channel | None = None
    seed: SeedCreator | None = None

    model_config = {"from_attributes": True}


class LookalikeSearchRequest(BaseModel):
    """Request body for initiating a lookalike search."""

    seed_names: list[str]

    @field_validator("seed_names")
    @classmethod
    def validate_seed_names(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one seed creator name is required")
        if len(v) > 3:
            raise ValueError("Maximum 3 seed creators allowed")
        cleaned = [name.strip() for name in v if name.strip()]
        if not cleaned:
            raise ValueError("Seed creator names cannot be empty")
        return cleaned


class LookalikeSearchResponse(BaseModel):
    """Response returned when a lookalike search is queued."""

    message: str
    task_id: str
    seed_count: int
