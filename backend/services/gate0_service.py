"""Gate 0 service for dispatching compliance checks."""

from datetime import datetime, timezone
from uuid import UUID

from celery import Celery
from celery.exceptions import CeleryError
from kombu.exceptions import OperationalError
from postgrest.exceptions import APIError

from core.config import settings
from core.exceptions import NotFoundError, SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.gate0 import Gate0CheckResponse
from services import admin_service
from workers.tasks import QUEUE_GATE0, TASK_RUN_GATE0

logger = get_logger(__name__)

_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)


def _mark_gate0_unchecked(channel_id: UUID) -> None:
    supabase_admin.table("channels").update(
        {
            "gate0_status": "unchecked",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", str(channel_id)).execute()


async def queue_gate0_check(channel_id: UUID) -> Gate0CheckResponse:
    """Queue a manual Gate 0 compliance check for a channel."""
    if not admin_service.is_feature_enabled("gate0"):
        return Gate0CheckResponse(
            channel_id=channel_id,
            message="Gate 0 is disabled in system settings.",
            task_id="",
            status="unchecked",
            triggered_at=datetime.now(timezone.utc),
        )

    try:
        channel_result = (
            supabase_admin.table("channels")
            .select("id")
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )
        if channel_result.data is None:
            raise NotFoundError(f"Channel {channel_id} not found")

        supabase_admin.table("channels").update(
            {
                "gate0_status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", str(channel_id)).execute()
    except NotFoundError:
        raise
    except APIError as exc:
        logger.error(
            "Failed to update gate0 status for %s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to update gate0 status: {exc}") from exc

    try:
        task = _celery.send_task(
            TASK_RUN_GATE0,
            args=[str(channel_id), True],
            queue=QUEUE_GATE0,
        )
    except (CeleryError, OperationalError) as exc:
        try:
            _mark_gate0_unchecked(channel_id)
        except APIError:
            logger.error(
                "Failed to clear pending Gate 0 status after dispatch failure for %s",
                channel_id,
                exc_info=True,
            )
        logger.error(
            "Failed to queue Gate 0 check for channel=%s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to queue Gate 0 check: {exc}") from exc

    logger.info("Gate 0 check queued for channel=%s task=%s", channel_id, task.id)
    return Gate0CheckResponse(
        channel_id=channel_id,
        message="Gate 0 check queued",
        task_id=task.id,
        status="pending",
        triggered_at=datetime.now(timezone.utc),
    )
