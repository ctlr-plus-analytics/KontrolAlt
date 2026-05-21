"""Pydantic models for VelocityScore entities."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class VelocityScore(BaseModel):
    """Velocity score record for a channel."""

    id: UUID
    channel_id: UUID
    computed_at: datetime
    view_velocity_30d: float | None = None
    view_velocity_90d: float | None = None
    comment_velocity_30d: float | None = None
    comment_velocity_90d: float | None = None

    model_config = {"from_attributes": True}
