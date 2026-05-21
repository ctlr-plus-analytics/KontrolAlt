"""Domain-specific exceptions for the Kontrol_Alt backend."""


class NotFoundError(Exception):
    """Raised when a requested resource does not exist in the database."""

    pass


class ScraperBlockedError(Exception):
    """Raised when a scraper detects it has been blocked by the target site."""

    pass


class SupabaseError(Exception):
    """Raised when a Supabase query fails unexpectedly."""

    pass
