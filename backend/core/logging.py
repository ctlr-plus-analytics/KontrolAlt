"""Structured logging configuration for the Kontrol_Alt backend."""

import logging
import sys

from core.config import settings

# ---------------------------------------------------------------------------
# Global log format
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _configure_root_logger() -> None:
    """Configure the root logger once at import time."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    root = logging.getLogger()
    # Avoid duplicate handlers if module is re-imported
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)


# Run once on import
_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Usage::

        logger = get_logger(__name__)
        logger.info("Something happened")

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    return logging.getLogger(name)
