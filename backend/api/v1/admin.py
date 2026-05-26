"""Admin control-plane endpoints."""

from fastapi import APIRouter, Depends, Query

from core.security import require_admin_user
from models.admin import (
    AdminMeResponse,
    AdminTaskStatusResponse,
    AdminTaskTriggerRequest,
    AdminTaskTriggerResponse,
    Gate0BatchTriggerRequest,
    Gate0BatchTriggerResponse,
    PaginatedAdminAuditResponse,
)
from services import admin_service

router = APIRouter()


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(user: dict = Depends(require_admin_user)) -> AdminMeResponse:
    roles = ["admin"]
    return AdminMeResponse(
        user_id=user.get("id", ""),
        email=user.get("email"),
        roles=roles,
        capabilities=[
            "tasks:trigger",
            "audit:read",
        ],
    )


@router.post("/tasks/scrape-now", response_model=AdminTaskTriggerResponse)
async def trigger_scrape_now(
    body: AdminTaskTriggerRequest,
    user: dict = Depends(require_admin_user),
) -> AdminTaskTriggerResponse:
    return await admin_service.trigger_full_scrape(actor=user, reason=body.reason)


@router.post("/tasks/discovery-now", response_model=AdminTaskTriggerResponse)
async def trigger_discovery_now(
    body: AdminTaskTriggerRequest,
    user: dict = Depends(require_admin_user),
) -> AdminTaskTriggerResponse:
    return await admin_service.trigger_discovery(actor=user, reason=body.reason)


@router.post("/tasks/weekly-velocity-now", response_model=AdminTaskTriggerResponse)
async def trigger_weekly_velocity_now(
    body: AdminTaskTriggerRequest,
    user: dict = Depends(require_admin_user),
) -> AdminTaskTriggerResponse:
    return await admin_service.trigger_weekly_velocity(actor=user, reason=body.reason)


@router.post("/tasks/gate0-now", response_model=Gate0BatchTriggerResponse)
async def trigger_gate0_now(
    body: Gate0BatchTriggerRequest,
    user: dict = Depends(require_admin_user),
) -> Gate0BatchTriggerResponse:
    return await admin_service.trigger_gate0_batch(
        actor=user, channel_ids=body.channel_ids, reason=body.reason
    )


@router.get("/tasks/{task_id}", response_model=AdminTaskStatusResponse)
async def get_task_status(
    task_id: str,
    user: dict = Depends(require_admin_user),
) -> AdminTaskStatusResponse:
    return await admin_service.get_task_status(task_id)


@router.get("/audit", response_model=PaginatedAdminAuditResponse)
async def get_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_admin_user),
) -> PaginatedAdminAuditResponse:
    data, total = await admin_service.list_audit(page=page, page_size=page_size)
    return PaginatedAdminAuditResponse(
        data=data,
        total=total,
        page=page,
        page_size=page_size,
    )
