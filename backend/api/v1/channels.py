"""Channel endpoints — GET /channels, GET /channels/{id}."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from core.exceptions import NotFoundError
from core.logging import get_logger
from core.security import get_current_user
from models.channel import (
    ChannelFilters,
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
    niche_tag: str | None = Query(None),
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
        gate0_status=gate0_status,
        niche_tag=niche_tag,
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
    tags = await channel_service.list_niche_tags()
    return NicheTagListResponse(tags=tags)


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
