"""Backend core configuration for environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = (
    _SERVICE_ROOT.parent
    if _SERVICE_ROOT.name in {"backend", "scraper"}
    else _SERVICE_ROOT
)
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    The app will fail fast with a clear validation error if any required
    variable is missing when this class is instantiated.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Redis
    redis_url: str

    # CORS
    frontend_origin: str
    frontend_origin_regex: str | None = None

    # App
    app_env: str = "development"
    log_level: str = "INFO"


# Singleton validates on import and crashes early if vars are missing.
settings = Settings()
