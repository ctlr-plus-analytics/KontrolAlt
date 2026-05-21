"""Lookalike service - seed persistence, task dispatch, and result reads."""

from datetime import datetime, timezone

from celery import Celery
from celery.exceptions import CeleryError
from postgrest.exceptions import APIError

from core.config import settings
from core.exceptions import SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.lookalike import LookalikeSearchRequest, LookalikeSearchResponse
from services import admin_service
from workers.tasks import TASK_FIND_LOOKALIKES

logger = get_logger(__name__)
_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)


async def queue_lookalike_search(
    body: LookalikeSearchRequest,
    user_id: str,
) -> LookalikeSearchResponse:
    """Save seed creators and queue a worker-side lookalike search."""
    if not admin_service.is_feature_enabled("lookalike"):
        return LookalikeSearchResponse(
            message="Lookalike workflows are disabled in system settings.",
            task_id="",
            seed_count=len(body.seed_names),
        )

    seed_ids: list[str] = []

    for name in body.seed_names:
        try:
            result = (
                supabase_admin.table("seed_creators")
                .upsert(
                    {
                        "user_id": user_id,
                        "name": name,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    on_conflict="user_id,name",
                )
                .execute()
            )
        except APIError as exc:
            logger.error("Failed to upsert seed creator: %s", exc, exc_info=True)
            raise SupabaseError(f"Failed to save seed creator: {exc}") from exc

        if result.data:
            seed_ids.append(result.data[0]["id"])
        else:
            logger.warning("Seed upsert returned no row for user=%s name=%s", user_id, name)

    if not seed_ids:
        logger.error("No seed IDs resolved for lookalike search user=%s", user_id)
        return LookalikeSearchResponse(
            message=(
                "Lookalike search could not start because no valid seeds were persisted. "
                "Please retry."
            ),
            task_id="",
            seed_count=len(body.seed_names),
        )

    try:
        task = _celery.send_task(TASK_FIND_LOOKALIKES, args=[seed_ids])
    except CeleryError as exc:
        logger.error("Failed to queue lookalike task: %s", exc, exc_info=True)
        raise SupabaseError(f"Failed to queue lookalike search: {exc}") from exc

    logger.info(
        "Lookalike search queued user=%s seeds=%s task=%s",
        user_id,
        seed_ids,
        task.id,
    )
    return LookalikeSearchResponse(
        message="Lookalike search queued",
        task_id=task.id,
        seed_count=len(body.seed_names),
    )


async def get_lookalike_results_for_user(user_id: str) -> list[dict[str, object]]:
    """Fetch all lookalike matches for a user's seed creators."""
    try:
        seeds_result = (
            supabase_admin.table("seed_creators")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        seeds = seeds_result.data or []
        if not seeds:
            return []

        seed_ids = [seed["id"] for seed in seeds]
        seed_map = {seed["id"]: seed for seed in seeds}

        matches_result = (
            supabase_admin.table("lookalike_matches")
            .select("*, channels(*)")
            .in_("seed_id", seed_ids)
            .execute()
        )
        matches = matches_result.data or []

        enriched: list[dict[str, object]] = []
        for match in matches:
            channel_data = match.pop("channels", None)
            match["channel"] = channel_data
            match["seed"] = seed_map.get(match.get("seed_id"))
            enriched.append(match)

        return enriched

    except APIError as exc:
        logger.error(
            "Failed to fetch lookalike results for user %s: %s",
            user_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to fetch lookalike results: {exc}") from exc
