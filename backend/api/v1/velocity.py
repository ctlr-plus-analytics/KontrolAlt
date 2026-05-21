"""Velocity endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from core.exceptions import NotFoundError
from core.security import get_current_user
from models.velocity import VelocityScore
from services import velocity_service

router = APIRouter()


@router.get("/{channel_id}", response_model=VelocityScore)
async def get_velocity(
    channel_id: UUID,
    user: dict = Depends(get_current_user),
) -> VelocityScore:
    """Return the latest velocity scores for a channel."""
    try:
        result = await velocity_service.get_velocity(channel_id)
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail="No velocity data yet - collecting history",
        )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No velocity data yet - collecting history",
        )

    return result
