"""Admin service for audit logs and manual task triggers."""

from datetime import datetime, timezone
from uuid import UUID

from celery import Celery
from celery.exceptions import CeleryError
from celery.result import AsyncResult
from kombu.exceptions import OperationalError
from postgrest.exceptions import APIError

from core.config import settings
from core.exceptions import SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.admin import (
    AdminTaskStatusResponse,
    AdminTaskTriggerResponse,
    Gate0BatchTriggerResponse,
)
from workers.tasks import TASK_DISCOVER_CHANNELS
from workers.tasks import TASK_RUN_DAILY_SCRAPE, TASK_RUN_GATE0
from workers.tasks import TASK_RUN_WEEKLY_VELOCITY_SCRAPE

logger = get_logger(__name__)
_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)

_AUDIT_TABLE = "admin_actions_audit"


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


async def trigger_full_scrape(actor: dict, reason: str | None) -> AdminTaskTriggerResponse:
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


async def trigger_weekly_velocity(
    actor: dict, reason: str | None
) -> AdminTaskTriggerResponse:
    task = _celery.send_task(TASK_RUN_WEEKLY_VELOCITY_SCRAPE)
    _audit(
        actor=actor,
        action="tasks.trigger",
        target="velocity.weekly",
        metadata={"task_ids": [task.id], "reason": reason},
    )
    return AdminTaskTriggerResponse(
        message=f"Weekly velocity workflow triggered: {task.id}",
        task_id=task.id,
        task_ids=[task.id],
        triggered_at=datetime.now(timezone.utc),
    )


async def trigger_discovery(actor: dict, reason: str | None) -> AdminTaskTriggerResponse:
    discovery_task = _celery.send_task(TASK_DISCOVER_CHANNELS)
    task_ids = [discovery_task.id]
    _audit(
        actor=actor,
        action="tasks.trigger",
        target="discovery.manual",
        metadata={"task_ids": task_ids, "reason": reason},
    )
    return AdminTaskTriggerResponse(
        message="Discovery workflow triggered",
        task_id=discovery_task.id,
        task_ids=task_ids,
        triggered_at=datetime.now(timezone.utc),
    )


async def trigger_gate0_batch(
    actor: dict, channel_ids: list[UUID], reason: str | None
) -> Gate0BatchTriggerResponse:
    task_ids: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for channel_id in channel_ids:
        pending_marked = False
        try:
            supabase_admin.table("channels").update(
                {"gate0_status": "pending", "updated_at": now_iso}
            ).eq("id", str(channel_id)).execute()
            pending_marked = True
        except APIError as exc:
            logger.warning(
                "Failed to mark channel pending for gate0 batch: %s",
                exc,
                exc_info=True,
            )
            continue

        try:
            task = _celery.send_task(TASK_RUN_GATE0, args=[str(channel_id), True])
        except (CeleryError, OperationalError) as exc:
            if pending_marked:
                try:
                    supabase_admin.table("channels").update(
                        {"gate0_status": "unchecked", "updated_at": now_iso}
                    ).eq("id", str(channel_id)).execute()
                except APIError:
                    logger.error(
                        "Failed to clear pending Gate 0 status for %s",
                        channel_id,
                        exc_info=True,
                    )
            logger.warning(
                "Failed to queue Gate 0 task for %s: %s",
                channel_id,
                exc,
                exc_info=True,
            )
            continue
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
    result = AsyncResult(task_id, app=_celery)
    return AdminTaskStatusResponse(
        task_id=task_id,
        state=result.state,
        result=result.result if isinstance(result.result, (dict, list, str, int, float, bool, type(None))) else str(result.result),
        date_done=result.date_done.isoformat() if result.date_done else None,
    )


async def list_audit(page: int, page_size: int) -> tuple[list[dict[str, object]], int]:
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
