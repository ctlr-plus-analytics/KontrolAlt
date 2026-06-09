"""Admin service for audit logs and manual task triggers."""

from datetime import datetime, timezone
from uuid import UUID

try:
    import docker as docker_lib
except ImportError:  # pragma: no cover - optional runtime dependency in tests
    docker_lib = None
import redis as redis_lib
from celery import Celery
from celery.exceptions import CeleryError
from celery.result import AsyncResult
from kombu.exceptions import OperationalError
from postgrest.exceptions import APIError

from core.config import settings
from core.exceptions import SupabaseError, WorkerUnavailableError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.admin import (
    AdminTaskStatusResponse,
    AdminTaskTriggerResponse,
    Gate0BatchTriggerResponse,
    PurgeQueueResponse,
    WorkerPreflightResponse,
    WorkerInfo,
    WorkerLogsResponse,
    WorkerStatusResponse,
)
from workers.tasks import (
    QUEUE_CLASSIFY,
    QUEUE_DISCOVERY,
    QUEUE_GATE0,
    TASK_CLASSIFY_CHANNELS,
    TASK_DISCOVER_CHANNELS,
    TASK_SCRAPE_NEVER_SCRAPED_RUMBLE_SUBSTACK,
)
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

_TASK_WORKER_REQUIREMENTS: dict[str, list[str]] = {
    "scrape": [
        "worker-discovery",
        "worker-rumble",
        "worker-substack",
        "worker-gate0",
        "worker-classify",
    ],
    "discovery": ["worker-discovery", "worker-rumble", "worker-substack"],
    "never-scraped-bootstrap": ["worker-discovery", "worker-rumble", "worker-substack"],
    "weekly-velocity": ["worker-discovery", "worker-rumble", "worker-substack"],
    "gate0": ["worker-gate0"],
    "classify-channels": ["worker-classify"],
    "classify-channels-all": ["worker-classify"],
}

_TASK_LABELS: dict[str, str] = {
    "scrape": "Full scrape",
    "discovery": "Discovery",
    "never-scraped-bootstrap": "Never-scraped bootstrap",
    "weekly-velocity": "Weekly velocity",
    "gate0": "Gate 0 batch",
    "classify-channels": "AI classify channels",
    "classify-channels-all": "AI reclassify all channels",
}

def _normalize_competitors(value: object) -> list[dict]:
    """Return a safe competitor list matching the response schema."""
    if not isinstance(value, list):
        return []
    normalized: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        brand_raw = item.get("brand")
        domains_raw = item.get("domains")
        brand = str(brand_raw).strip() if isinstance(brand_raw, str) else ""
        if not brand:
            continue
        domains: list[str] = []
        if isinstance(domains_raw, list):
            for domain in domains_raw:
                if isinstance(domain, str):
                    cleaned = domain.strip()
                    if cleaned:
                        domains.append(cleaned)
        normalized.append({"brand": brand, "domains": domains})
    return normalized


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
    await _require_workers("scrape")
    task = _celery.send_task(TASK_RUN_DAILY_SCRAPE, queue=QUEUE_DISCOVERY)
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
    await _require_workers("weekly-velocity")
    task = _celery.send_task(TASK_RUN_WEEKLY_VELOCITY_SCRAPE, queue=QUEUE_DISCOVERY)
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
    await _require_workers("discovery")
    discovery_task = _celery.send_task(TASK_DISCOVER_CHANNELS, queue=QUEUE_DISCOVERY)
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


async def trigger_never_scraped_bootstrap(
    actor: dict, reason: str | None
) -> AdminTaskTriggerResponse:
    await _require_workers("never-scraped-bootstrap")
    task = _celery.send_task(
        TASK_SCRAPE_NEVER_SCRAPED_RUMBLE_SUBSTACK,
        queue=QUEUE_DISCOVERY,
    )
    _audit(
        actor=actor,
        action="tasks.trigger",
        target="scrape.never_scraped_rumble_substack",
        metadata={"task_ids": [task.id], "reason": reason},
    )
    return AdminTaskTriggerResponse(
        message=f"Never-scraped Rumble/Substack bootstrap triggered: {task.id}",
        task_id=task.id,
        task_ids=[task.id],
        triggered_at=datetime.now(timezone.utc),
    )


async def trigger_gate0_batch(
    actor: dict, channel_ids: list[UUID], reason: str | None
) -> Gate0BatchTriggerResponse:
    await _require_workers("gate0")
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
            task = _celery.send_task(
                TASK_RUN_GATE0,
                args=[str(channel_id), True],
                queue=QUEUE_GATE0,
            )
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
        return _normalize_competitors(result.data.get("gate0_competitors"))
    except APIError as exc:
        logger.error("Failed to read gate0 competitors: %s", exc, exc_info=True)
        return []


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

    # Step 1 — SIGKILL active, reserved, and scheduled tasks in worker processes
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
            _celery.control.revoke(task_id, terminate=True, signal="SIGKILL")
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
    # (platform slots, scrape locks, proxy health, RPM counters, byte budget)
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

    # Step 6 — restart worker pools to flush prefetch buffers and zombie processes
    try:
        _celery.control.broadcast("pool_restart", wait=False)
        stats["pool_restarted"] = True
    except Exception as exc:
        logger.warning("Worker pool restart broadcast failed: %s", exc)
        stats["pool_restarted"] = False

    _audit(
        actor=actor,
        action="tasks.purge",
        target="queue.all",
        metadata={"stats": stats, "reason": reason},
    )
    logger.info("Queue purge complete: %s", stats)
    return PurgeQueueResponse(
        message="All tasks killed (SIGKILL); broker queue, Redis scraper state, and worker pools reset.",
        stats=stats,
        purged_at=datetime.now(timezone.utc),
    )


async def trigger_classify_channels(
    actor: dict, reclassify: bool, reason: str | None
) -> AdminTaskTriggerResponse:
    await _require_workers("classify-channels-all" if reclassify else "classify-channels")
    task = _celery.send_task(
        TASK_CLASSIFY_CHANNELS,
        kwargs={"reclassify": reclassify},
        queue=QUEUE_CLASSIFY,
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


# Ordered list of compose service names and the queue each one consumes.
# beat runs celery beat (not a worker) so queue is None.
_WORKER_SERVICES: list[tuple[str, str | None]] = [
    ("worker-discovery", "discovery"),
    ("worker-classify", "classify"),
    ("worker-gate0", "gate0"),
    ("worker-rumble", "rumble"),
    ("worker-substack", "substack"),
    ("beat", None),
]

# Preferred Celery hostname (set via --hostname in docker-compose.yml).
_SERVICE_TO_CELERY_NAME: dict[str, str] = {
    service: f"celery@{service}"
    for service, queue in _WORKER_SERVICES
    if queue is not None
}


def _docker_client() -> docker_lib.DockerClient | None:
    if docker_lib is None:
        logger.warning("Docker client unavailable: docker package is not installed")
        return None
    try:
        client = docker_lib.from_env()
        client.ping()  # eagerly test the connection
        return client
    except Exception as exc:
        logger.warning("Docker client unavailable: %s", exc)
        return None


def _container_status(client: docker_lib.DockerClient | None, service: str) -> str:
    if client is None:
        return "unknown"
    try:
        containers = client.containers.list(
            all=True, filters={"label": f"com.docker.compose.service={service}"}
        )
        return containers[0].status if containers else "not found"
    except Exception as exc:
        logger.warning("Container status lookup failed for %s: %s", service, exc)
        return "unknown"


def _build_queue_to_worker(queues_map: dict) -> dict[str, str]:
    """Build a queue-name → celery-worker-name map from inspect().active_queues()."""
    result: dict[str, str] = {}
    for worker_name, queue_list in queues_map.items():
        for q in queue_list or []:
            name = q.get("name") if isinstance(q, dict) else None
            if name:
                result[name] = worker_name
    return result


def _collect_worker_statuses() -> tuple[list[WorkerInfo], datetime]:
    """Inspect Celery and Docker once, returning the current worker snapshot."""
    try:
        inspector = _celery.control.inspect(timeout=3.0)
        ping_map: dict = inspector.ping() or {}
        stats_map: dict = inspector.stats() or {}
        active_map: dict = inspector.active() or {}
        reserved_map: dict = inspector.reserved() or {}
        queues_map: dict = inspector.active_queues() or {}
    except Exception as exc:
        logger.warning("Celery inspect failed: %s", exc)
        ping_map = stats_map = active_map = reserved_map = queues_map = {}

    logger.debug("Celery ping_map keys: %s", list(ping_map.keys()))

    queue_to_worker = _build_queue_to_worker(queues_map)
    docker = _docker_client()
    workers: list[WorkerInfo] = []

    for service, queue in _WORKER_SERVICES:
        container_status = _container_status(docker, service)

        if queue is not None:
            preferred = _SERVICE_TO_CELERY_NAME[service]
            celery_name: str | None = preferred if preferred in ping_map else queue_to_worker.get(queue)
            online = celery_name is not None
            worker_stats: dict = stats_map.get(celery_name) or {} if celery_name else {}
            pool_info: dict = worker_stats.get("pool") or {}
            total_info: dict = worker_stats.get("total") or {}
            active_tasks = len(active_map.get(celery_name) or []) if celery_name else 0
            reserved_tasks = len(reserved_map.get(celery_name) or []) if celery_name else 0
            processed_total = sum(total_info.values()) if total_info else 0
            concurrency: int | None = pool_info.get("max-concurrency")
            pid: int | None = worker_stats.get("pid")
            display_celery_name = celery_name
        else:
            online = container_status == "running"
            active_tasks = reserved_tasks = processed_total = 0
            concurrency = pid = None
            display_celery_name = None

        workers.append(WorkerInfo(
            service=service,
            celery_name=display_celery_name,
            online=online,
            container_status=container_status,
            active_tasks=active_tasks,
            reserved_tasks=reserved_tasks,
            processed_total=processed_total,
            concurrency=concurrency,
            pid=pid,
        ))

    return workers, datetime.now(timezone.utc)


def _format_offline_services(services: list[str]) -> str:
    if not services:
        return ""
    if len(services) == 1:
        return services[0]
    return ", ".join(services[:-1]) + f" and {services[-1]}"


def _build_worker_preflight_response(task_kind: str) -> WorkerPreflightResponse:
    required_services = _TASK_WORKER_REQUIREMENTS.get(task_kind, [])
    workers, checked_at = _collect_worker_statuses()
    worker_map = {worker.service: worker for worker in workers}
    offline_services: list[str] = []
    for service in required_services:
        worker = worker_map.get(service)
        if worker is None or not worker.online:
            offline_services.append(service)
    warning_services = [worker.service for worker in workers if not worker.online and worker.service not in required_services]
    ready = len(offline_services) == 0
    task_label = _TASK_LABELS.get(task_kind, task_kind)

    if ready:
        if warning_services:
            message = (
                f"{task_label} can proceed, but "
                f"{_format_offline_services(warning_services)} is offline."
            )
        else:
            message = f"{task_label} preflight passed. All required workers are online."
    else:
        message = (
            f"{task_label} is blocked because "
            f"{_format_offline_services(offline_services)} is offline."
        )
        if warning_services:
            message += f" Additional offline workers: {_format_offline_services(warning_services)}."

    return WorkerPreflightResponse(
        task_kind=task_kind,
        ready=ready,
        message=message,
        required_services=required_services,
        blocking_services=offline_services,
        warning_services=warning_services,
        workers=workers,
        checked_at=checked_at,
    )


async def get_worker_preflight(task_kind: str) -> WorkerPreflightResponse:
    """Check whether the worker containers required for a task are online."""
    return _build_worker_preflight_response(task_kind)


async def _require_workers(task_kind: str) -> None:
    preflight = await get_worker_preflight(task_kind)
    if not preflight.ready:
        raise WorkerUnavailableError(preflight.message)


async def get_worker_statuses() -> WorkerStatusResponse:
    workers, checked_at = _collect_worker_statuses()
    return WorkerStatusResponse(workers=workers, checked_at=checked_at)


async def get_worker_logs(service: str, tail: int) -> WorkerLogsResponse:
    valid = {s for s, _ in _WORKER_SERVICES}
    if service not in valid:
        return WorkerLogsResponse(service=service, lines=["Unknown service."], tail=tail)

    if docker_lib is None:
        return WorkerLogsResponse(
            service=service,
            lines=["Docker package is unavailable in this environment."],
            tail=tail,
        )

    try:
        docker_client_instance = docker_lib.from_env()
        docker_client_instance.ping()
    except Exception as exc:
        logger.warning("Docker unavailable when fetching logs for %s: %s", service, exc)
        return WorkerLogsResponse(
            service=service,
            lines=[f"Docker socket error: {exc}"],
            tail=tail,
        )
    try:
        containers = docker_client_instance.containers.list(
            all=True, filters={"label": f"com.docker.compose.service={service}"}
        )
        if not containers:
            return WorkerLogsResponse(service=service, lines=["Container not found."], tail=tail)
        raw: bytes = containers[0].logs(tail=tail, timestamps=True, stream=False)
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return WorkerLogsResponse(service=service, lines=lines, tail=tail)
    except Exception as exc:
        logger.warning("Failed to fetch logs for %s: %s", service, exc)
        return WorkerLogsResponse(service=service, lines=[f"Error fetching logs: {exc}"], tail=tail)
