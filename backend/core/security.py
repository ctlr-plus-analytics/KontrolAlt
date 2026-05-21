"""Supabase JWT verification dependency for FastAPI routes."""

from fastapi import Depends, HTTPException, Request, status

try:
    from gotrue.errors import AuthApiError, AuthRetryableError, AuthUnknownError
except ImportError:  # pragma: no cover - defensive for gotrue version drift.
    AuthApiError = RuntimeError
    AuthRetryableError = RuntimeError
    AuthUnknownError = RuntimeError

from core.supabase import supabase_anon


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency that extracts and verifies the Supabase JWT.

    Reads the ``Authorization: Bearer <token>`` header and verifies
    the token via the Supabase SDK ``auth.get_user()`` call.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The Supabase user object as a dict.

    Raises:
        HTTPException: 401 if the header is missing or the token is invalid.
    """
    auth_header: str | None = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
        )

    token = auth_header.removeprefix("Bearer ").strip()

    try:
        response = supabase_anon.auth.get_user(token)
        if response is None or response.user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        # Return the user object as a dict for downstream use
        return {
            "id": str(response.user.id),
            "email": response.user.email,
            "role": response.user.role,
            "app_metadata": getattr(response.user, "app_metadata", {}) or {},
            "user_metadata": response.user.user_metadata,
        }
    except HTTPException:
        raise
    except (AuthApiError, AuthRetryableError, AuthUnknownError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        )


async def get_current_user_id(
    user: dict = Depends(get_current_user),
) -> str:
    """FastAPI dependency that returns only the user ID string.

    Args:
        user: The user dict from ``get_current_user``.

    Returns:
        The user ID as a string.
    """
    return user["id"]


def _metadata_grants_admin(metadata: object) -> bool:
    """Return True when a Supabase metadata dict grants admin access."""
    if not isinstance(metadata, dict):
        return False

    role = metadata.get("role")
    is_admin = metadata.get("is_admin")
    return role == "admin" or is_admin is True or is_admin == "true"


async def require_admin_user(
    user: dict = Depends(get_current_user),
) -> dict:
    """Require an authenticated user with admin metadata."""
    if _metadata_grants_admin(user.get("app_metadata")):
        return user
    if _metadata_grants_admin(user.get("user_metadata")):
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required.",
    )
