"""Admin service for runtime settings, audit logs, and manual triggers."""

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
    SystemSettingsPatchRequest,
    SystemSettingsResponse,
)
from workers.tasks import TASK_DISCOVER_CHANNELS
from workers.tasks import TASK_RUN_DAILY_SCRAPE, TASK_RUN_GATE0
from workers.tasks import TASK_RUN_WEEKLY_VELOCITY_SCRAPE

logger = get_logger(__name__)
_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)

_SETTINGS_TABLE = "system_settings"
_AUDIT_TABLE = "admin_actions_audit"
_SETTINGS_SINGLETON_KEY = "global"
_DEFAULT_GATE0_COMPETITORS: list[dict[str, object]] = [
    {"brand": "Noble Gold", "domains": ["noblegold.com"]},
    {"brand": "Birch Gold", "domains": ["birchgold.com"]},
    {"brand": "Patriot Gold", "domains": ["patriotgold.com"]},
    {"brand": "Kirk Elliot", "domains": ["kirkelliot.com"]},
]


def _default_settings_row() -> dict[str, object]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "singleton_key": _SETTINGS_SINGLETON_KEY,
        "daily_scrape_utc_time": "02:00:00",
        "gate0_enabled": True,
        "discovery_enabled": True,
        "lookalike_enabled": True,
        "scrape_platform_priority": ["rumble", "bitchute"],
        "scrape_only_new_or_missing_metrics": True,
        "scrape_rescrape_min_hours": 72,
        "weekly_velocity_enabled": True,
        "weekly_velocity_utc_day": "sun",
        "weekly_velocity_utc_time": "03:00:00",
        "velocity_weekly_min_avg_comments": 20,
        "velocity_weekly_min_avg_views": 0,
        "velocity_weekly_min_subscribers": 0,
        "velocity_weekly_stale_hours": 144,
        "scrape_dispatch_batch_size": 1,
        "scrape_dispatch_pause_seconds": 5,
        "scrape_run_max_channels": 0,
        "scrape_daily_byte_budget_mb": 0,
        "scrape_retry_base_delay_seconds": 120,
        "scrape_retry_jitter_min": 1.0,
        "scrape_retry_jitter_max": 1.8,
        "scrape_circuit_breaker_fail_threshold": 5,
        "scrape_circuit_breaker_window_seconds": 1800,
        "scrape_circuit_breaker_cooldown_seconds": 1800,
        "gate0_daily_queue_limit": 200,
        "gate0_clean_recheck_days": 7,
        "gate0_competitors": _DEFAULT_GATE0_COMPETITORS,
        "scraper_human_delay_min_seconds": 2,
        "scraper_human_delay_max_seconds": 8,
        "scraper_content_wait_min_bytes": 5000,
        "scraper_content_wait_timeout_seconds": 20,
        "scraper_content_wait_poll_seconds": 1.5,
        "discovery_serper_query_limit": 480,
        "discovery_results_per_query": 20,
        "discovery_max_pages_per_query": 8,
        "discovery_insert_limit": 20000,
        "discovery_query_stagnation_limit": 4,
        "discovery_global_stop_no_new": 120,
        "discovery_max_feedback_terms": 36,
        "discovery_new_scrape_limit": 500,
        "discovery_channel_page_size": 1000,
        "discovery_verify_timeout_seconds": 15,
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
    raw_weekly_time = str(row.get("weekly_velocity_utc_time") or "03:00:00")
    competitors = row.get("gate0_competitors")
    if not isinstance(competitors, list):
        competitors = _DEFAULT_GATE0_COMPETITORS
    return SystemSettingsResponse(
        daily_scrape_utc_time=formatted_time,
        gate0_enabled=bool(row.get("gate0_enabled", True)),
        discovery_enabled=bool(row.get("discovery_enabled", True)),
        lookalike_enabled=bool(row.get("lookalike_enabled", True)),
        scrape_platform_priority=list(row.get("scrape_platform_priority") or []),
        scrape_only_new_or_missing_metrics=bool(
            row.get("scrape_only_new_or_missing_metrics", True)
        ),
        scrape_rescrape_min_hours=int(row.get("scrape_rescrape_min_hours") or 72),
        weekly_velocity_enabled=bool(row.get("weekly_velocity_enabled", True)),
        weekly_velocity_utc_day=str(row.get("weekly_velocity_utc_day") or "sun"),
        weekly_velocity_utc_time=raw_weekly_time[:5],
        velocity_weekly_min_avg_comments=float(
            row.get("velocity_weekly_min_avg_comments") or 20
        ),
        velocity_weekly_min_avg_views=float(
            row.get("velocity_weekly_min_avg_views") or 0
        ),
        velocity_weekly_min_subscribers=int(
            row.get("velocity_weekly_min_subscribers") or 0
        ),
        velocity_weekly_stale_hours=int(
            row.get("velocity_weekly_stale_hours") or 144
        ),
        scrape_dispatch_batch_size=int(row.get("scrape_dispatch_batch_size") or 1),
        scrape_dispatch_pause_seconds=float(
            row.get("scrape_dispatch_pause_seconds") or 5
        ),
        scrape_run_max_channels=int(row.get("scrape_run_max_channels") or 0),
        scrape_daily_byte_budget_mb=int(row.get("scrape_daily_byte_budget_mb") or 0),
        scrape_retry_base_delay_seconds=int(
            row.get("scrape_retry_base_delay_seconds") or 120
        ),
        scrape_retry_jitter_min=float(row.get("scrape_retry_jitter_min") or 1.0),
        scrape_retry_jitter_max=float(row.get("scrape_retry_jitter_max") or 1.8),
        scrape_circuit_breaker_fail_threshold=int(
            row.get("scrape_circuit_breaker_fail_threshold") or 5
        ),
        scrape_circuit_breaker_window_seconds=int(
            row.get("scrape_circuit_breaker_window_seconds") or 1800
        ),
        scrape_circuit_breaker_cooldown_seconds=int(
            row.get("scrape_circuit_breaker_cooldown_seconds") or 1800
        ),
        gate0_daily_queue_limit=int(row.get("gate0_daily_queue_limit") or 200),
        gate0_clean_recheck_days=int(row.get("gate0_clean_recheck_days") or 7),
        gate0_competitors=competitors,
        scraper_human_delay_min_seconds=float(
            row.get("scraper_human_delay_min_seconds") or 2
        ),
        scraper_human_delay_max_seconds=float(
            row.get("scraper_human_delay_max_seconds") or 8
        ),
        scraper_content_wait_min_bytes=int(
            row.get("scraper_content_wait_min_bytes") or 5000
        ),
        scraper_content_wait_timeout_seconds=float(
            row.get("scraper_content_wait_timeout_seconds") or 20
        ),
        scraper_content_wait_poll_seconds=float(
            row.get("scraper_content_wait_poll_seconds") or 1.5
        ),
        discovery_serper_query_limit=int(
            row.get("discovery_serper_query_limit") or 480
        ),
        discovery_results_per_query=int(row.get("discovery_results_per_query") or 20),
        discovery_max_pages_per_query=int(
            row.get("discovery_max_pages_per_query") or 8
        ),
        discovery_insert_limit=int(row.get("discovery_insert_limit") or 20000),
        discovery_query_stagnation_limit=int(
            row.get("discovery_query_stagnation_limit") or 4
        ),
        discovery_global_stop_no_new=int(
            row.get("discovery_global_stop_no_new") or 120
        ),
        discovery_max_feedback_terms=int(
            row.get("discovery_max_feedback_terms") or 36
        ),
        discovery_new_scrape_limit=int(row.get("discovery_new_scrape_limit") or 500),
        discovery_channel_page_size=int(
            row.get("discovery_channel_page_size") or 1000
        ),
        discovery_verify_timeout_seconds=float(
            row.get("discovery_verify_timeout_seconds") or 15
        ),
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
    if payload.gate0_competitors is not None:
        updates["gate0_competitors"] = [
            competitor.model_dump(mode="json")
            for competitor in payload.gate0_competitors
        ]
    if payload.discovery_enabled is not None:
        updates["discovery_enabled"] = payload.discovery_enabled
    if payload.lookalike_enabled is not None:
        updates["lookalike_enabled"] = payload.lookalike_enabled
    if payload.scrape_platform_priority is not None:
        updates["scrape_platform_priority"] = payload.scrape_platform_priority
    if payload.scrape_only_new_or_missing_metrics is not None:
        updates["scrape_only_new_or_missing_metrics"] = (
            payload.scrape_only_new_or_missing_metrics
        )
    if payload.scrape_rescrape_min_hours is not None:
        updates["scrape_rescrape_min_hours"] = payload.scrape_rescrape_min_hours
    if payload.weekly_velocity_enabled is not None:
        updates["weekly_velocity_enabled"] = payload.weekly_velocity_enabled
    if payload.weekly_velocity_utc_day is not None:
        updates["weekly_velocity_utc_day"] = payload.weekly_velocity_utc_day
    if payload.weekly_velocity_utc_time is not None:
        updates["weekly_velocity_utc_time"] = f"{payload.weekly_velocity_utc_time}:00"
    if payload.velocity_weekly_min_avg_comments is not None:
        updates["velocity_weekly_min_avg_comments"] = (
            payload.velocity_weekly_min_avg_comments
        )
    if payload.velocity_weekly_min_avg_views is not None:
        updates["velocity_weekly_min_avg_views"] = payload.velocity_weekly_min_avg_views
    if payload.velocity_weekly_min_subscribers is not None:
        updates["velocity_weekly_min_subscribers"] = (
            payload.velocity_weekly_min_subscribers
        )
    if payload.velocity_weekly_stale_hours is not None:
        updates["velocity_weekly_stale_hours"] = payload.velocity_weekly_stale_hours
    operational_fields = (
        "scrape_dispatch_batch_size",
        "scrape_dispatch_pause_seconds",
        "scrape_run_max_channels",
        "scrape_daily_byte_budget_mb",
        "scrape_retry_base_delay_seconds",
        "scrape_retry_jitter_min",
        "scrape_retry_jitter_max",
        "scrape_circuit_breaker_fail_threshold",
        "scrape_circuit_breaker_window_seconds",
        "scrape_circuit_breaker_cooldown_seconds",
        "gate0_daily_queue_limit",
        "gate0_clean_recheck_days",
        "scraper_human_delay_min_seconds",
        "scraper_human_delay_max_seconds",
        "scraper_content_wait_min_bytes",
        "scraper_content_wait_timeout_seconds",
        "scraper_content_wait_poll_seconds",
        "discovery_serper_query_limit",
        "discovery_results_per_query",
        "discovery_max_pages_per_query",
        "discovery_insert_limit",
        "discovery_query_stagnation_limit",
        "discovery_global_stop_no_new",
        "discovery_max_feedback_terms",
        "discovery_new_scrape_limit",
        "discovery_channel_page_size",
        "discovery_verify_timeout_seconds",
    )
    payload_data = payload.model_dump(exclude_unset=True)
    for field in operational_fields:
        if field in payload_data and payload_data[field] is not None:
            updates[field] = payload_data[field]

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


async def trigger_weekly_velocity(
    actor: dict, reason: str | None
) -> AdminTaskTriggerResponse:
    """Admin-triggered weekly clean-lead velocity scrape workflow."""
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
    """Admin-triggered discovery tasks, respecting discovery toggle."""
    if not is_feature_enabled("discovery"):
        return AdminTaskTriggerResponse(
            message="Discovery is disabled in system settings.",
            task_id="",
            task_ids=[],
            triggered_at=datetime.now(timezone.utc),
        )

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
