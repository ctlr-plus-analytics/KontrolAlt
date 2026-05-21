"""Runtime settings reader for scraper workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from postgrest.exceptions import APIError

from core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
_SETTINGS_TABLE = "system_settings"
_SETTINGS_KEY = "global"


@dataclass(frozen=True)
class RuntimeSettings:
    daily_scrape_utc_time: str = "02:00"
    gate0_enabled: bool = True
    discovery_enabled: bool = True
    lookalike_enabled: bool = True
    scrape_platform_priority: tuple[str, ...] = ("rumble", "bitchute")


def get_runtime_settings() -> RuntimeSettings:
    """Fetch runtime settings with safe defaults on any read error."""
    try:
        client = get_supabase_client()
        result = (
            client.table(_SETTINGS_TABLE)
            .select("*")
            .eq("singleton_key", _SETTINGS_KEY)
            .maybe_single()
            .execute()
        )
        row = result.data or {}
        raw_time = str(row.get("daily_scrape_utc_time") or "02:00:00")
        priority_raw = row.get("scrape_platform_priority") or ["rumble", "bitchute"]
        if not isinstance(priority_raw, list):
            priority_raw = ["rumble", "bitchute"]
        priority = tuple(
            value
            for value in (str(item).lower() for item in priority_raw)
            if value in {"rumble", "bitchute"}
        )
        if not priority:
            priority = ("rumble", "bitchute")
        return RuntimeSettings(
            daily_scrape_utc_time=raw_time[:5],
            gate0_enabled=bool(row.get("gate0_enabled", True)),
            discovery_enabled=bool(row.get("discovery_enabled", True)),
            lookalike_enabled=bool(row.get("lookalike_enabled", True)),
            scrape_platform_priority=priority,
        )
    except APIError as exc:
        logger.warning("Failed to load runtime settings; using defaults: %s", exc)
        return RuntimeSettings()
