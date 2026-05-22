"""Velocity service for reading stored velocity scores."""

from uuid import UUID

from postgrest.exceptions import APIError

from core.exceptions import NotFoundError, SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.velocity import VelocityScore

logger = get_logger(__name__)


async def get_velocity(channel_id: UUID) -> VelocityScore | None:
    """Fetch the latest velocity score for a channel.

    Args:
        channel_id: UUID of the channel.

    Returns:
        The latest VelocityScore, or None if no records exist.

    Raises:
        NotFoundError: If no velocity data exists for this channel.
    """
    try:
        result = (
            supabase_admin.table("channels")
            .select("id, view_velocity_30d, view_velocity_90d, comment_velocity_30d, comment_velocity_90d, velocity_computed_at")
            .eq("id", str(channel_id))
            .execute()
        )

        if not result.data:
            raise NotFoundError(
                f"No velocity data for channel {channel_id}"
            )

        row = result.data[0]
        if row.get("velocity_computed_at") is None:
            raise NotFoundError(
                f"No velocity data for channel {channel_id}"
            )

        return VelocityScore(
            id=row["id"],
            channel_id=row["id"],
            computed_at=row["velocity_computed_at"],
            view_velocity_30d=row["view_velocity_30d"],
            view_velocity_90d=row["view_velocity_90d"],
            comment_velocity_30d=row["comment_velocity_30d"],
            comment_velocity_90d=row["comment_velocity_90d"],
        )

    except NotFoundError:
        raise
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Failed to fetch velocity for %s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to fetch velocity: {exc}") from exc
