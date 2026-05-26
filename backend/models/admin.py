"""Pydantic models for admin control-plane actions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AdminMeResponse(BaseModel):
    user_id: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class AdminTaskTriggerRequest(BaseModel):
    reason: str | None = None


class AdminTaskTriggerResponse(BaseModel):
    message: str
    task_id: str
    task_ids: list[str]
    triggered_at: datetime


class Gate0BatchTriggerRequest(BaseModel):
    channel_ids: list[UUID]
    reason: str | None = None


class Gate0BatchTriggerResponse(BaseModel):
    queued: int
    task_ids: list[str]
    triggered_at: datetime


class AdminTaskStatusResponse(BaseModel):
    task_id: str
    state: str
    result: object | None = None
    date_done: str | None = None


class AdminAuditRecord(BaseModel):
    id: UUID
    actor_user_id: UUID
    actor_email: str | None = None
    action: str
    target: str
    old_value: dict | None = None
    new_value: dict | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class PaginatedAdminAuditResponse(BaseModel):
    data: list[AdminAuditRecord]
    total: int
    page: int
    page_size: int


class CompetitorDef(BaseModel):
    brand: str
    domains: list[str]


class CompetitorListResponse(BaseModel):
    competitors: list[CompetitorDef]


class UpdateCompetitorsRequest(BaseModel):
    competitors: list[CompetitorDef]
