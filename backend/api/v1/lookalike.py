"""Lookalike endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends

from core.security import get_current_user, get_current_user_id
from models.lookalike import (
    ChannelLookalikeResponse,
    LookalikeMatch,
    LookalikeSearchRequest,
    LookalikeSearchResponse,
)
from services import lookalike_service

router = APIRouter()


@router.post("/search", response_model=LookalikeSearchResponse)
async def search_lookalikes(
    body: LookalikeSearchRequest,
    user: dict = Depends(get_current_user),
    user_id: str = Depends(get_current_user_id),
) -> LookalikeSearchResponse:
    """Save seed creators and queue a lookalike search."""
    return await lookalike_service.queue_lookalike_search(body, user_id)


@router.get("/results", response_model=list[LookalikeMatch])
async def get_results(
    user: dict = Depends(get_current_user),
    user_id: str = Depends(get_current_user_id),
) -> list[LookalikeMatch]:
    """Return all lookalike match results for the current user."""
    return await lookalike_service.get_lookalike_results_for_user(user_id)


@router.get("/channel/{channel_id}", response_model=ChannelLookalikeResponse)
async def get_channel_lookalikes(
    channel_id: UUID,
    user: dict = Depends(get_current_user),
) -> ChannelLookalikeResponse:
    """Compute lookalike matches for a specific channel."""
    return await lookalike_service.get_lookalikes_for_channel(channel_id)
