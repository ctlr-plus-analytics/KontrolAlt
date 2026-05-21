"""Pydantic models for structured API errors."""

from datetime import datetime

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Structured error response returned by the API."""

    error: str
    detail: str
    timestamp: datetime
