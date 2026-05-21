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
            supabase_admin.table("velocity_scores")
            .select("*")
            .eq("channel_id", str(channel_id))
            .order("computed_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            raise NotFoundError(
                f"No velocity data for channel {channel_id}"
            )

        return VelocityScore(**result.data[0])

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
