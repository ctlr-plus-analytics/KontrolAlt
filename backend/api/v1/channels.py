"""Channel endpoints — GET /channels, GET /channels/{id}."""

import csv
import io
from datetime import date
from uuid import UUID

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.exceptions import NotFoundError, SupabaseError
from core.logging import get_logger
from core.security import get_current_user
from models.channel import (
    CategoryTagListResponse,
    ChannelDoNotContactUpdateRequest,
    ChannelFilters,
    ChannelDeleteResponse,
    Gate0StatusListResponse,
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

# "Avg Views / Likes": avg_views stores real views for Rumble but average
# reactions/likes per post for Substack (no public view-count API) — see
# CODEBASE_DOCUMENTATION.md. The adjacent Platform column disambiguates.
_EXPORT_HEADERS = [
    "Name", "Platform", "URL", "Subscribers",
    "Niche / Category", "Avg Views / Likes", "Avg Comments",
    "Engagement Rate (%)", "Last Active",
]


def _build_csv_response(rows: list[dict]) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_EXPORT_HEADERS)
    for row in rows:
        tags = row.get("niche_tags") or []
        niche_str = "; ".join(tags) if tags else ""
        eng = row.get("engagement_rate")
        writer.writerow([
            row.get("name") or "",
            row.get("platform") or "",
            row.get("channel_url") or "",
            row.get("subscriber_count") if row.get("subscriber_count") is not None else "",
            niche_str,
            row.get("avg_views") if row.get("avg_views") is not None else "",
            row.get("avg_comments") if row.get("avg_comments") is not None else "",
            f"{eng:.2f}" if eng is not None else "",
            row.get("last_active_date") or "",
        ])
    today = date.today().isoformat()
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="channels_export_{today}.csv"'},
    )


def _build_excel_response(rows: list[dict]) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Channels"

    header_fill = PatternFill(start_color="1A1A2E", end_color="1A1A2E", fill_type="solid")
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    header_align = Alignment(horizontal="center", vertical="center")

    for col, title in enumerate(_EXPORT_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"

    alt_fill = PatternFill(start_color="F5F4F1", end_color="F5F4F1", fill_type="solid")
    data_font = Font(name="Calibri", size=10)
    link_font = Font(name="Calibri", size=10, color="4472C4", underline="single")
    num_formats = [None, None, None, "#,##0", None, "#,##0", "#,##0.0", "0.00", None]

    for i, row in enumerate(rows):
        r = i + 2
        tags = row.get("niche_tags") or []
        eng = row.get("engagement_rate")
        url = row.get("channel_url") or ""

        values = [
            row.get("name") or "",
            row.get("platform") or "",
            url,
            row.get("subscriber_count"),
            "; ".join(tags) if tags else "",
            row.get("avg_views"),
            row.get("avg_comments"),
            eng,
            row.get("last_active_date") or "",
        ]

        row_fill = alt_fill if i % 2 == 1 else None
        for col, (val, fmt) in enumerate(zip(values, num_formats), 1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = data_font
            if row_fill:
                cell.fill = row_fill
            if fmt:
                cell.number_format = fmt

        if url:
            lc = ws.cell(row=r, column=3)
            lc.hyperlink = url
            lc.font = link_font

    # Auto-fit column widths based on content (sample header + up to 200 rows)
    for col_idx in range(1, len(_EXPORT_HEADERS) + 1):
        max_len = len(_EXPORT_HEADERS[col_idx - 1])
        for r in range(2, min(len(rows) + 2, 202)):
            cell_val = ws.cell(row=r, column=col_idx).value
            if cell_val is not None:
                max_len = max(max_len, len(str(cell_val)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    today = date.today().isoformat()
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="channels_export_{today}.xlsx"'},
    )


@router.get("", response_model=PaginatedChannels)
async def list_channels(
    platform: Platform | None = Query(None),
    comment_tier: CommentTier | None = Query(None),
    gate0_status: Gate0Status | None = Query(None),
    gate0_statuses: list[Gate0Status] | None = Query(None),
    category_tag: str | None = Query(None),
    category_tags: list[str] | None = Query(None),
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
        category_tags=(
            category_tags
            or ([category_tag] if category_tag else None)
            or niche_tags
            or ([niche_tag] if niche_tag else None)
        ),
        niche_tags=(
            category_tags
            or ([category_tag] if category_tag else None)
            or niche_tags
            or ([niche_tag] if niche_tag else None)
        ),
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


@router.get("/niche-tags", response_model=CategoryTagListResponse)
async def list_niche_tags(
    user: dict = Depends(get_current_user),
) -> CategoryTagListResponse:
    """Legacy alias: return distinct category tags for filter dropdowns."""
    tags, tag_counts = await channel_service.list_niche_tags()
    return CategoryTagListResponse(tags=tags, tag_counts=tag_counts)


@router.get("/category-tags", response_model=CategoryTagListResponse)
async def list_category_tags(
    platform: Platform | None = Query(None),
    comment_tier: CommentTier | None = Query(None),
    gate0_statuses: list[Gate0Status] | None = Query(None),
    search_query: str | None = Query(None),
    min_subscriber_count: int | None = Query(None, ge=0),
    max_subscriber_count: int | None = Query(None, ge=0),
    min_avg_views: float | None = Query(None, ge=0),
    max_avg_views: float | None = Query(None, ge=0),
    min_avg_comments: float | None = Query(None, ge=0),
    max_avg_comments: float | None = Query(None, ge=0),
    inactive_filter: bool = Query(False),
    incomplete_only: bool = Query(False),
    last_active_from: date | None = Query(None),
    last_active_to: date | None = Query(None),
    user: dict = Depends(get_current_user),
) -> CategoryTagListResponse:
    """Return distinct category tags and per-tag counts, scoped to active filters."""
    filters = ChannelFilters(
        platform=platform,
        comment_tier=comment_tier,
        gate0_statuses=gate0_statuses,
        search_query=search_query,
        min_subscriber_count=min_subscriber_count,
        max_subscriber_count=max_subscriber_count,
        min_avg_views=min_avg_views,
        max_avg_views=max_avg_views,
        min_avg_comments=min_avg_comments,
        max_avg_comments=max_avg_comments,
        inactive_filter=inactive_filter,
        incomplete_only=incomplete_only,
        last_active_from=last_active_from,
        last_active_to=last_active_to,
    )
    tags, tag_counts = await channel_service.list_niche_tags(filters)
    return CategoryTagListResponse(tags=tags, tag_counts=tag_counts)


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


@router.get("/export")
async def export_channels(
    platform: Platform | None = Query(None),
    comment_tier: CommentTier | None = Query(None),
    gate0_status: Gate0Status | None = Query(None),
    gate0_statuses: list[Gate0Status] | None = Query(None),
    category_tag: str | None = Query(None),
    category_tags: list[str] | None = Query(None),
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
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Download all matching channels as CSV or Excel."""
    filters = ChannelFilters(
        platform=platform,
        comment_tier=comment_tier,
        gate0_statuses=(gate0_statuses or ([gate0_status] if gate0_status else None)),
        category_tags=(
            category_tags
            or ([category_tag] if category_tag else None)
            or niche_tags
            or ([niche_tag] if niche_tag else None)
        ),
        niche_tags=(
            category_tags
            or ([category_tag] if category_tag else None)
            or niche_tags
            or ([niche_tag] if niche_tag else None)
        ),
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
    )
    rows = await channel_service.export_channels(filters)
    return _build_excel_response(rows) if format == "xlsx" else _build_csv_response(rows)


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


@router.patch("/{channel_id}/do-not-contact", response_model=ChannelWithMetrics)
async def update_channel_do_not_contact(
    channel_id: UUID,
    body: ChannelDoNotContactUpdateRequest,
    user: dict = Depends(get_current_user),
) -> ChannelWithMetrics:
    """Set or clear the manual do-not-contact status for a channel."""
    try:
        return await channel_service.update_channel_do_not_contact(
            channel_id,
            body.do_not_contact.value if body.do_not_contact is not None else None,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Channel not found")
    except SupabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
