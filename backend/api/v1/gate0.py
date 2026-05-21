"""Gate 0 endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from core.exceptions import NotFoundError
from core.security import get_current_user
from models.gate0 import Gate0CheckResponse
from services import gate0_service

router = APIRouter()


@router.post("/check/{channel_id}", response_model=Gate0CheckResponse)
async def check_gate0(
    channel_id: UUID,
    user: dict = Depends(get_current_user),
) -> Gate0CheckResponse:
    """Queue a manual Gate 0 compliance check for a channel."""
    try:
        return await gate0_service.queue_gate0_check(channel_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Channel not found")
