"""Pydantic models for Gate0Result entities."""

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Gate0ResultStatus(str, Enum):
    """Result status of a Gate 0 compliance check."""

    clean = "clean"
    dirty = "dirty"


class Gate0Result(BaseModel):
    """A single Gate 0 compliance check result."""

    id: UUID
    channel_id: UUID
    checked_at: datetime
    search_query: str
    result_status: Gate0ResultStatus
    flagged_brand: str | None = None
    source_url: str | None = None

    model_config = {"from_attributes": True}


class Gate0CheckResponse(BaseModel):
    """Response returned when a Gate 0 check is queued."""

    channel_id: UUID
    message: str
    task_id: str
    status: Literal["pending"]
    triggered_at: datetime
