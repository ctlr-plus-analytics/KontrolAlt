"""Supabase client singleton for the scraper service."""

from supabase import Client, create_client

from core.config import scraper_settings

_client: Client | None = None


def get_supabase_client() -> Client:
    """Return a cached Supabase client using the service role key."""
    global _client
    if _client is None:
        _client = create_client(
            scraper_settings.supabase_url,
            scraper_settings.supabase_service_role_key,
        )
    return _client
