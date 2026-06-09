"""Pydantic models for admin control-plane actions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

BROAD_TAXONOMY_CATEGORIES = {
    "Prepper / Survival",
    "Financial / Macro",
    "Conservative Politics",
    "Health / Wellness",
    "Homesteading",
    "Crypto / Alternative Assets",
    "Religious / Values-Based",
    "News / Commentary",
    "Unknown / Needs Review",
}

AdminTaskKind = Literal[
    "scrape",
    "discovery",
    "never-scraped-bootstrap",
    "weekly-velocity",
    "gate0",
    "classify-channels",
    "classify-channels-all",
]


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


class KeywordTaxonomyDef(BaseModel):
    niche: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list, min_length=1)

    @field_validator("niche")
    @classmethod
    def validate_niche(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Category must not be empty.")
        if normalized not in BROAD_TAXONOMY_CATEGORIES:
            raise ValueError("Category must be one of the supported broad categories.")
        return normalized

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        normalized = [keyword.strip() for keyword in value if keyword.strip()]
        if len(normalized) == 0:
            raise ValueError("At least one keyword is required.")
        return normalized


class KeywordTaxonomyListResponse(BaseModel):
    taxonomy: list[KeywordTaxonomyDef]


class UpdateKeywordTaxonomyRequest(BaseModel):
    taxonomy: list[KeywordTaxonomyDef]


class ClassifyChannelsTriggerRequest(BaseModel):
    reclassify: bool = False
    reason: str | None = None


class WorkerPreflightRequest(BaseModel):
    task_kind: AdminTaskKind


class WorkerPreflightResponse(BaseModel):
    task_kind: AdminTaskKind
    ready: bool
    message: str
    required_services: list[str] = Field(default_factory=list)
    blocking_services: list[str] = Field(default_factory=list)
    warning_services: list[str] = Field(default_factory=list)
    workers: list["WorkerInfo"] = Field(default_factory=list)
    checked_at: datetime


class PurgeQueueRequest(BaseModel):
    reason: str | None = None


class PurgeQueueResponse(BaseModel):
    message: str
    stats: dict
    purged_at: datetime


class WorkerInfo(BaseModel):
    service: str
    celery_name: str | None = None
    online: bool
    container_status: str
    active_tasks: int = 0
    reserved_tasks: int = 0
    processed_total: int = 0
    concurrency: int | None = None
    pid: int | None = None


class WorkerStatusResponse(BaseModel):
    workers: list[WorkerInfo]
    checked_at: datetime


class WorkerLogsResponse(BaseModel):
    service: str
    lines: list[str]
    tail: int


WorkerPreflightResponse.model_rebuild()
