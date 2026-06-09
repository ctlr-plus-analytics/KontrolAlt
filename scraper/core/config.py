"""Scraper core configuration for environment variables."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = (
    _SERVICE_ROOT.parent
    if _SERVICE_ROOT.name in {"backend", "scraper"}
    else _SERVICE_ROOT
)
_ENV_FILE = _REPO_ROOT / ".env"


class ScraperSettings(BaseSettings):
    """Scraper settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str
    supabase_service_role_key: str

    # Redis
    redis_url: str

    # Proxies (comma-separated). Platform-specific lists override the shared list.
    proxy_list: str
    proxy_list_rumble: str | None = None
    proxy_list_substack: str | None = None
    proxy_session_minutes: int = 10
    proxy_active_since_minutes: int = 0
    proxy_platform_filter: str | None = None

    # Serper search (needed for Gate 0 tasks)
    serp_api_key: str

    # Google AI Studio (optional — needed for AI channel classification)
    google_api_key: str | None = None

    @field_validator("proxy_list")
    @classmethod
    def validate_proxy_list(cls, value: str) -> str:
        """Require at least one configured residential proxy."""
        if not [proxy.strip() for proxy in value.split(",") if proxy.strip()]:
            raise ValueError("PROXY_LIST must contain at least one proxy")
        return value

    @field_validator("proxy_session_minutes")
    @classmethod
    def validate_proxy_session_minutes(cls, value: int) -> int:
        if value < 1 or value > 1440:
            raise ValueError("PROXY_SESSION_MINUTES must be between 1 and 1440")
        return value

    @field_validator("proxy_active_since_minutes")
    @classmethod
    def validate_proxy_active_since_minutes(cls, value: int) -> int:
        if value < 0 or value > 1440:
            raise ValueError("PROXY_ACTIVE_SINCE_MINUTES must be between 0 and 1440")
        return value

# Singleton validates on import.
scraper_settings = ScraperSettings()
