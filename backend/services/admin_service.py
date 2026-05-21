"""Admin service for runtime settings, audit logs, and manual triggers."""

from datetime import datetime, timezone
from uuid import UUID

from celery import Celery
from celery.result import AsyncResult
from postgrest.exceptions import APIError

from core.config import settings
from core.exceptions import SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.admin import (
    AdminTaskStatusResponse,
    AdminTaskTriggerResponse,
    Gate0BatchTriggerResponse,
    SystemSettingsPatchRequest,
    SystemSettingsResponse,
)
from workers.tasks import TASK_DISCOVER_KEYWORD_EXPANSION, TASK_DISCOVER_SEED_EXPANSION
from workers.tasks import TASK_RUN_DAILY_SCRAPE, TASK_RUN_GATE0

logger = get_logger(__name__)
_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)

_SETTINGS_TABLE = "system_settings"
_AUDIT_TABLE = "admin_actions_audit"
_SETTINGS_SINGLETON_KEY = "global"


def _default_settings_row() -> dict[str, object]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "singleton_key": _SETTINGS_SINGLETON_KEY,
        "daily_scrape_utc_time": "02:00:00",
        "gate0_enabled": True,
        "discovery_enabled": True,
        "lookalike_enabled": True,
        "scrape_platform_priority": ["rumble", "bitchute"],
        "version": 1,
        "updated_at": now_iso,
        "created_at": now_iso,
    }


def _ensure_settings_row() -> dict[str, object]:
    try:
        result = (
            supabase_admin.table(_SETTINGS_TABLE)
            .select("*")
            .eq("singleton_key", _SETTINGS_SINGLETON_KEY)
            .maybe_single()
            .execute()
        )
        if result.data:
            return result.data

        insert_result = (
            supabase_admin.table(_SETTINGS_TABLE)
            .insert(_default_settings_row())
            .execute()
        )
        data = insert_result.data or []
        if not data:
            raise SupabaseError("Failed to initialize system settings.")
        return data[0]
    except APIError as exc:
        raise SupabaseError(f"Failed to load system settings: {exc}") from exc


def _to_settings_response(row: dict[str, object]) -> SystemSettingsResponse:
    raw_time = str(row.get("daily_scrape_utc_time") or "02:00:00")
    formatted_time = raw_time[:5]
    return SystemSettingsResponse(
        daily_scrape_utc_time=formatted_time,
        gate0_enabled=bool(row.get("gate0_enabled", True)),
        discovery_enabled=bool(row.get("discovery_enabled", True)),
        lookalike_enabled=bool(row.get("lookalike_enabled", True)),
        scrape_platform_priority=list(row.get("scrape_platform_priority") or []),
        version=int(row.get("version") or 1),
        updated_at=row.get("updated_at") or datetime.now(timezone.utc),
        updated_by_email=row.get("updated_by_email"),
    )


async def get_system_settings() -> SystemSettingsResponse:
    """Return current global system settings."""
    row = _ensure_settings_row()
    return _to_settings_response(row)


def _audit(
    actor: dict,
    action: str,
    target: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        supabase_admin.table(_AUDIT_TABLE).insert(
            {
                "actor_user_id": actor.get("id"),
                "actor_email": actor.get("email"),
                "action": action,
                "target": target,
                "old_value": old_value,
                "new_value": new_value,
                "metadata": metadata or {},
            }
        ).execute()
    except APIError as exc:
        logger.warning("Failed to write admin audit: %s", exc, exc_info=True)


async def update_system_settings(
    payload: SystemSettingsPatchRequest, actor: dict
) -> SystemSettingsResponse:
    """Patch global settings with optimistic locking."""
    current_row = _ensure_settings_row()
    current_version = int(current_row.get("version") or 1)
    if current_version != payload.expected_version:
        raise ValueError("Settings version conflict. Refresh and retry.")

    updates: dict[str, object] = {
        "updated_by": actor.get("id"),
        "updated_by_email": actor.get("email"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "version": current_version + 1,
    }
    if payload.daily_scrape_utc_time is not None:
        updates["daily_scrape_utc_time"] = f"{payload.daily_scrape_utc_time}:00"
    if payload.gate0_enabled is not None:
        updates["gate0_enabled"] = payload.gate0_enabled
    if payload.discovery_enabled is not None:
        updates["discovery_enabled"] = payload.discovery_enabled
    if payload.lookalike_enabled is not None:
        updates["lookalike_enabled"] = payload.lookalike_enabled
    if payload.scrape_platform_priority is not None:
        updates["scrape_platform_priority"] = payload.scrape_platform_priority

    try:
        result = (
            supabase_admin.table(_SETTINGS_TABLE)
            .update(updates)
            .eq("singleton_key", _SETTINGS_SINGLETON_KEY)
            .eq("version", current_version)
            .execute()
        )
        data = result.data or []
        if not data:
            raise ValueError("Settings update failed due to concurrent change.")
        updated_row = data[0]
    except APIError as exc:
        raise SupabaseError(f"Failed to update system settings: {exc}") from exc

    _audit(
        actor=actor,
        action="settings.update",
        target="system_settings.global",
        old_value=current_row,
        new_value=updated_row,
    )
    return _to_settings_response(updated_row)


def is_feature_enabled(feature: str) -> bool:
    """Read a feature flag from settings for dispatch-time checks."""
    row = _ensure_settings_row()
    if feature == "gate0":
        return bool(row.get("gate0_enabled", True))
    if feature == "discovery":
        return bool(row.get("discovery_enabled", True))
    if feature == "lookalike":
        return bool(row.get("lookalike_enabled", True))
    return True


async def trigger_full_scrape(actor: dict, reason: str | None) -> AdminTaskTriggerResponse:
    """Admin-triggered full scrape workflow."""
    task = _celery.send_task(TASK_RUN_DAILY_SCRAPE)
    _audit(
        actor=actor,
        action="tasks.trigger",
        target="scrape.full",
        metadata={"task_ids": [task.id], "reason": reason},
    )
    return AdminTaskTriggerResponse(
        message=f"Scrape workflow triggered: {task.id}",
        task_id=task.id,
        task_ids=[task.id],
        triggered_at=datetime.now(timezone.utc),
    )


async def trigger_discovery(actor: dict, reason: str | None) -> AdminTaskTriggerResponse:
    """Admin-triggered discovery tasks, respecting discovery toggle."""
    if not is_feature_enabled("discovery"):
        return AdminTaskTriggerResponse(
            message="Discovery is disabled in system settings.",
            task_id="",
            task_ids=[],
            triggered_at=datetime.now(timezone.utc),
        )

    seed_task = _celery.send_task(TASK_DISCOVER_SEED_EXPANSION)
    keyword_task = _celery.send_task(TASK_DISCOVER_KEYWORD_EXPANSION)
    task_ids = [seed_task.id, keyword_task.id]
    _audit(
        actor=actor,
        action="tasks.trigger",
        target="discovery.manual",
        metadata={"task_ids": task_ids, "reason": reason},
    )
    return AdminTaskTriggerResponse(
        message="Discovery-only tasks triggered",
        task_id=seed_task.id,
        task_ids=task_ids,
        triggered_at=datetime.now(timezone.utc),
    )


async def trigger_gate0_batch(
    actor: dict, channel_ids: list[UUID], reason: str | None
) -> Gate0BatchTriggerResponse:
    """Queue Gate 0 checks for selected channels, respecting gate0 toggle."""
    if not is_feature_enabled("gate0"):
        return Gate0BatchTriggerResponse(
            queued=0,
            task_ids=[],
            triggered_at=datetime.now(timezone.utc),
        )

    task_ids: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for channel_id in channel_ids:
        try:
            supabase_admin.table("channels").update(
                {"gate0_status": "pending", "updated_at": now_iso}
            ).eq("id", str(channel_id)).execute()
        except APIError as exc:
            logger.warning(
                "Failed to mark channel pending for gate0 batch: %s",
                exc,
                exc_info=True,
            )
        task = _celery.send_task(TASK_RUN_GATE0, args=[str(channel_id), True])
        task_ids.append(task.id)

    _audit(
        actor=actor,
        action="tasks.trigger",
        target="gate0.batch",
        metadata={
            "channel_ids": [str(value) for value in channel_ids],
            "task_ids": task_ids,
            "reason": reason,
        },
    )
    return Gate0BatchTriggerResponse(
        queued=len(task_ids),
        task_ids=task_ids,
        triggered_at=datetime.now(timezone.utc),
    )


async def get_task_status(task_id: str) -> AdminTaskStatusResponse:
    """Return current Celery backend state for a task id."""
    result = AsyncResult(task_id, app=_celery)
    return AdminTaskStatusResponse(
        task_id=task_id,
        state=result.state,
        result=result.result if isinstance(result.result, (dict, list, str, int, float, bool, type(None))) else str(result.result),
        date_done=result.date_done.isoformat() if result.date_done else None,
    )


async def list_audit(page: int, page_size: int) -> tuple[list[dict[str, object]], int]:
    """Return paginated admin audit rows."""
    start = (page - 1) * page_size
    end = start + page_size - 1
    try:
        result = (
            supabase_admin.table(_AUDIT_TABLE)
            .select("*", count="exact")
            .order("created_at", desc=True)
            .range(start, end)
            .execute()
        )
        return result.data or [], int(result.count or 0)
    except APIError as exc:
        raise SupabaseError(f"Failed to load admin audit: {exc}") from exc
