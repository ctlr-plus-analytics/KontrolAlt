"""Admin service for audit logs and manual task triggers."""

from datetime import datetime, timezone
from uuid import UUID

import redis as redis_lib
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
    PurgeQueueResponse,
)
from workers.tasks import TASK_CLASSIFY_CHANNELS, TASK_DISCOVER_CHANNELS
from workers.tasks import TASK_RUN_DAILY_SCRAPE, TASK_RUN_GATE0
from workers.tasks import TASK_RUN_WEEKLY_VELOCITY_SCRAPE

logger = get_logger(__name__)
_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)

_AUDIT_TABLE = "admin_actions_audit"
_FEATURE_FIELDS = {
    "gate0": "gate0_enabled",
    "discovery": "discovery_enabled",
    "lookalike": "lookalike_enabled",
}


def is_feature_enabled(feature: str) -> bool:
    """Return runtime feature flag from system_settings with safe fallback."""
    field = _FEATURE_FIELDS.get(feature)
    if field is None:
        return True
    try:
        result = (
            supabase_admin.table("system_settings")
            .select(field)
            .eq("singleton_key", "global")
            .single()
            .execute()
        )
        value = result.data.get(field)
        if isinstance(value, bool):
            return value
    except APIError:
        logger.warning("Feature flag lookup failed for %s; defaulting enabled", feature)
    return True


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


async def get_gate0_competitors() -> list[dict]:
    try:
        result = (
            supabase_admin.table("system_settings")
            .select("gate0_competitors")
            .eq("singleton_key", "global")
            .single()
            .execute()
        )
        return result.data.get("gate0_competitors") or []
    except APIError as exc:
        raise SupabaseError(f"Failed to read gate0 competitors: {exc}") from exc


async def update_gate0_competitors(actor: dict, competitors: list[dict]) -> list[dict]:
    try:
        old_result = (
            supabase_admin.table("system_settings")
            .select("gate0_competitors")
            .eq("singleton_key", "global")
            .single()
            .execute()
        )
        old_value = old_result.data.get("gate0_competitors") or []
    except APIError:
        old_value = []

    try:
        supabase_admin.table("system_settings").update(
            {"gate0_competitors": competitors}
        ).eq("singleton_key", "global").execute()
    except APIError as exc:
        raise SupabaseError(f"Failed to update gate0 competitors: {exc}") from exc

    _audit(
        actor=actor,
        action="settings.update",
        target="gate0_competitors",
        old_value={"gate0_competitors": old_value},
        new_value={"gate0_competitors": competitors},
    )
    return competitors


async def get_keyword_taxonomy() -> list[dict]:
    try:
        result = (
            supabase_admin.table("system_settings")
            .select("keyword_taxonomy")
            .eq("singleton_key", "global")
            .single()
            .execute()
        )
        return result.data.get("keyword_taxonomy") or []
    except APIError as exc:
        raise SupabaseError(f"Failed to read keyword taxonomy: {exc}") from exc


async def update_keyword_taxonomy(actor: dict, taxonomy: list[dict]) -> list[dict]:
    try:
        old_result = (
            supabase_admin.table("system_settings")
            .select("keyword_taxonomy")
            .eq("singleton_key", "global")
            .single()
            .execute()
        )
        old_value = old_result.data.get("keyword_taxonomy") or []
    except APIError:
        old_value = []

    try:
        supabase_admin.table("system_settings").update(
            {"keyword_taxonomy": taxonomy}
        ).eq("singleton_key", "global").execute()
    except APIError as exc:
        raise SupabaseError(f"Failed to update keyword taxonomy: {exc}") from exc

    _audit(
        actor=actor,
        action="settings.update",
        target="keyword_taxonomy",
        old_value={"keyword_taxonomy": old_value},
        new_value={"keyword_taxonomy": taxonomy},
    )
    return taxonomy


def _scan_keys(client: redis_lib.Redis, pattern: str) -> list[bytes]:
    """Scan Redis for all keys matching pattern, returning them as a flat list."""
    keys: list[bytes] = []
    cursor = 0
    while True:
        cursor, batch = client.scan(cursor, match=pattern, count=200)
        keys.extend(batch)
        if cursor == 0:
            break
    return keys


async def purge_queues(actor: dict, reason: str | None) -> PurgeQueueResponse:
    """Discard all queued/reserved/active Celery tasks and clear Redis scraper state.

    Intended as a troubleshooting reset. Safe to call at any time; partial
    failures are logged but do not prevent remaining cleanup steps.
    """
    client = redis_lib.Redis.from_url(settings.redis_url, decode_responses=False)
    stats: dict[str, object] = {}

    # Step 1 — revoke active, reserved, and scheduled tasks via control channel
    try:
        inspector = _celery.control.inspect(timeout=3.0)
        active_map = inspector.active() or {}
        reserved_map = inspector.reserved() or {}
        scheduled_map = inspector.scheduled() or {}

        task_ids: set[str] = set()
        for task_list in [*active_map.values(), *reserved_map.values()]:
            for task in task_list:
                task_ids.add(task["id"])
        for task_list in scheduled_map.values():
            for entry in task_list:
                task_ids.add(entry["request"]["id"])

        for task_id in task_ids:
            _celery.control.revoke(task_id, terminate=True)
        stats["revoked"] = len(task_ids)
    except Exception as exc:
        logger.warning("Task revocation step failed: %s", exc)
        stats["revoked"] = 0
        stats["revoke_error"] = str(exc)

    # Step 2 — purge the broker queue via Celery's control API
    try:
        purged = _celery.control.purge()
        stats["broker_purged"] = purged
    except Exception as exc:
        logger.warning("Broker purge step failed: %s", exc)
        stats["broker_purged"] = 0
        stats["broker_error"] = str(exc)

    # Step 3 — delete queue and late-ack in-flight keys directly in Redis
    try:
        deleted = client.delete("celery", "unacked", "unacked_index")
        stats["direct_keys_deleted"] = int(deleted)
    except Exception as exc:
        logger.warning("Direct Redis key deletion failed: %s", exc)
        stats["direct_keys_deleted"] = 0

    # Step 4 — scan and delete all scraper:* state keys
    # (platform slots, scrape locks, circuit breakers, proxy health, RPM counters, byte budget)
    try:
        scraper_keys = _scan_keys(client, "scraper:*")
        if scraper_keys:
            client.delete(*scraper_keys)
        stats["scraper_keys_deleted"] = len(scraper_keys)
    except Exception as exc:
        logger.warning("Scraper key cleanup failed: %s", exc)
        stats["scraper_keys_deleted"] = 0

    # Step 5 — scan and delete Celery result backend keys
    try:
        result_keys = _scan_keys(client, "celery-task-meta-*")
        if result_keys:
            client.delete(*result_keys)
        stats["result_keys_deleted"] = len(result_keys)
    except Exception as exc:
        logger.warning("Result key cleanup failed: %s", exc)
        stats["result_keys_deleted"] = 0

    _audit(
        actor=actor,
        action="tasks.purge",
        target="queue.all",
        metadata={"stats": stats, "reason": reason},
    )
    logger.info("Queue purge complete: %s", stats)
    return PurgeQueueResponse(
        message="All queued, reserved, and active tasks cleared; Redis scraper state reset.",
        stats=stats,
        purged_at=datetime.now(timezone.utc),
    )


async def trigger_classify_channels(
    actor: dict, reclassify: bool, reason: str | None
) -> AdminTaskTriggerResponse:
    task = _celery.send_task(
        TASK_CLASSIFY_CHANNELS,
        kwargs={"reclassify": reclassify},
    )
    mode = "reclassify_all" if reclassify else "unclassified_only"
    _audit(
        actor=actor,
        action="tasks.trigger",
        target=f"classify_channels.{mode}",
        metadata={"task_ids": [task.id], "reclassify": reclassify, "reason": reason},
    )
    label = "full reclassification" if reclassify else "unclassified channels"
    return AdminTaskTriggerResponse(
        message=f"Channel classification triggered ({label}): {task.id}",
        task_id=task.id,
        task_ids=[task.id],
        triggered_at=datetime.now(timezone.utc),
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
