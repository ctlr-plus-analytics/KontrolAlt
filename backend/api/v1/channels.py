"""Channel endpoints — GET /channels, GET /channels/{id}."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from core.exceptions import NotFoundError, SupabaseError
from core.logging import get_logger
from core.security import get_current_user
from models.channel import (
    ChannelFilters,
    ChannelDeleteResponse,
    Gate0StatusListResponse,
    NicheTagListResponse,
    ChannelWithMetrics,
    CommentTier,
    Gate0Status,
    PaginatedChannels,
    Platform,
)
from models.channel_intake import (
    BulkChannelIntakeRequest,
    IntakeSummaryResponse,
    ManualChannelIntakeRequest,
    ResolverConfirmRequest,
    ResolverResponse,
    ResolverSeedRequest,
)
from services import channel_service
from services import channel_intake_service

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedChannels)
async def list_channels(
    platform: Platform | None = Query(None),
    comment_tier: CommentTier | None = Query(None),
    gate0_status: Gate0Status | None = Query(None),
    gate0_statuses: list[Gate0Status] | None = Query(None),
    niche_tag: str | None = Query(None),
    niche_tags: list[str] | None = Query(None),
    search_query: str | None = Query(None),
    min_subscriber_count: int | None = Query(None, ge=0),
    max_subscriber_count: int | None = Query(None, ge=0),
    min_avg_views: float | None = Query(None, ge=0),
    max_avg_views: float | None = Query(None, ge=0),
    min_avg_comments: float | None = Query(None, ge=0),
    max_avg_comments: float | None = Query(None, ge=0),
    inactive_filter: bool = Query(False),
    last_active_from: date | None = Query(None),
    last_active_to: date | None = Query(None),
    incomplete_only: bool = Query(False),
    sort_by: str = Query("avg_comments"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: dict = Depends(get_current_user),
) -> PaginatedChannels:
    """Return paginated, filtered channel listings."""
    filters = ChannelFilters(
        platform=platform,
        comment_tier=comment_tier,
        gate0_statuses=(gate0_statuses or ([gate0_status] if gate0_status else None)),
        niche_tags=(niche_tags or ([niche_tag] if niche_tag else None)),
        search_query=search_query,
        min_subscriber_count=min_subscriber_count,
        max_subscriber_count=max_subscriber_count,
        min_avg_views=min_avg_views,
        max_avg_views=max_avg_views,
        min_avg_comments=min_avg_comments,
        max_avg_comments=max_avg_comments,
        inactive_filter=inactive_filter,
        last_active_from=last_active_from,
        last_active_to=last_active_to,
        incomplete_only=incomplete_only,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    records, total = await channel_service.get_channels(filters)
    return PaginatedChannels(
        data=records,
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("/niche-tags", response_model=NicheTagListResponse)
async def list_niche_tags(
    user: dict = Depends(get_current_user),
) -> NicheTagListResponse:
    """Return distinct niche tags for filter dropdowns."""
    tags, tag_counts = await channel_service.list_niche_tags()
    return NicheTagListResponse(tags=tags, tag_counts=tag_counts)


@router.get("/gate0-statuses", response_model=Gate0StatusListResponse)
async def list_gate0_statuses(
    user: dict = Depends(get_current_user),
) -> Gate0StatusListResponse:
    """Return gate0 statuses and counts for filter dropdowns."""
    status_counts = await channel_service.list_gate0_status_counts()
    return Gate0StatusListResponse(status_counts=status_counts)


@router.post("/intake/manual", response_model=IntakeSummaryResponse)
async def intake_manual_channel(
    body: ManualChannelIntakeRequest,
    user: dict = Depends(get_current_user),
) -> IntakeSummaryResponse:
    """Add one channel from frontend intake form."""
    return await channel_intake_service.add_manual_channel(body)


@router.post("/intake/bulk", response_model=IntakeSummaryResponse)
async def intake_bulk_channels(
    body: BulkChannelIntakeRequest,
    user: dict = Depends(get_current_user),
) -> IntakeSummaryResponse:
    """Add many channels from pasted URL list."""
    return await channel_intake_service.add_bulk_channels(body)


@router.post("/intake/resolve", response_model=ResolverResponse)
async def resolve_seed_channels(
    body: ResolverSeedRequest,
    user: dict = Depends(get_current_user),
) -> ResolverResponse:
    """Resolve seed creator names into channel URL candidates for confirmation."""
    return await channel_intake_service.resolve_seed_creators(body)


@router.post("/intake/resolve/confirm", response_model=IntakeSummaryResponse)
async def confirm_resolved_channels(
    body: ResolverConfirmRequest,
    user: dict = Depends(get_current_user),
) -> IntakeSummaryResponse:
    """Insert user-confirmed resolver candidates."""
    return await channel_intake_service.confirm_resolver_selections(body)


@router.get("/{channel_id}", response_model=ChannelWithMetrics)
async def get_channel(
    channel_id: UUID,
    user: dict = Depends(get_current_user),
) -> ChannelWithMetrics:
    """Return a single channel by ID with velocity, Gate 0, and scrape logs."""
    try:
        result = await channel_service.get_channel_by_id(channel_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Channel not found")

    if result is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    return result


@router.delete("/{channel_id}/history", response_model=ChannelDeleteResponse)
async def delete_channel_history(
    channel_id: UUID,
    user: dict = Depends(get_current_user),
) -> ChannelDeleteResponse:
    """Delete channel historical data (snapshots/logs/computed caches)."""
    try:
        await channel_service.delete_channel_history(channel_id)
        return ChannelDeleteResponse(
            message="Channel history deleted",
            channel_id=channel_id,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Channel not found")
    except SupabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{channel_id}", response_model=ChannelDeleteResponse)
async def delete_channel_completely(
    channel_id: UUID,
    user: dict = Depends(get_current_user),
) -> ChannelDeleteResponse:
    """Delete channel and all related records from the database."""
    try:
        await channel_service.delete_channel_completely(channel_id)
        return ChannelDeleteResponse(
            message="Channel deleted completely",
            channel_id=channel_id,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Channel not found")
    except SupabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
