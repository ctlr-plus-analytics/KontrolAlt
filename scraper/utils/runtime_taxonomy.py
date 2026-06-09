"""Runtime DB-backed keyword taxonomy loader with lightweight caching."""

from __future__ import annotations

import logging
import time
from copy import deepcopy

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60
_DEFAULT_KEYWORD_TAXONOMY: dict[str, list[str]] = {
    "Prepper / Survival": [
        "prepper",
        "prepping",
        "emergency preparedness",
        "food storage",
        "self reliance",
        "survival",
    ],
    "Financial / Macro": [
        "gold",
        "retirement",
        "social security",
        "fixed income",
        "recession",
        "inflation",
        "debt",
    ],
    "Conservative Politics": [
        "free speech",
        "censorship",
        "constitutional",
        "second amendment",
        "2a",
    ],
    "Health / Wellness": [
        "wellness",
        "health",
        "nutrition",
        "fitness",
        "supplements",
    ],
    "Homesteading": [
        "homestead",
        "homesteading",
        "gardening",
        "farm",
    ],
    "Crypto / Alternative Assets": [
        "bitcoin",
        "crypto",
        "ethereum",
        "blockchain",
    ],
    "Religious / Values-Based": [
        "christian",
        "faith",
        "biblical",
        "church",
        "values",
    ],
    "News / Commentary": [
        "news",
        "commentary",
        "analysis",
        "journalism",
        "podcast",
    ],
}
_taxonomy_cache: dict[str, object] = {
    "loaded_at": 0.0,
    "taxonomy": None,
}


def _normalize_taxonomy(raw: object) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if not isinstance(raw, list):
        return normalized
    for item in raw:
        if not isinstance(item, dict):
            continue
        niche = str(item.get("niche") or "").strip()
        if not niche:
            continue
        keywords_raw = item.get("keywords")
        if not isinstance(keywords_raw, list):
            continue
        keywords = [str(keyword).strip().lower() for keyword in keywords_raw if str(keyword).strip()]
        if not keywords:
            continue
        deduped: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            if keyword in seen:
                continue
            seen.add(keyword)
            deduped.append(keyword)
        if deduped:
            normalized[niche] = deduped
    return normalized


def _load_runtime_keyword_taxonomy_from_db() -> dict[str, list[str]]:
    """Load the runtime taxonomy from Supabase."""
    from core.supabase import get_supabase_client

    client = get_supabase_client()
    result = (
        client.table("system_settings")
        .select("keyword_taxonomy")
        .eq("singleton_key", "global")
        .single()
        .execute()
    )
    raw = (result.data or {}).get("keyword_taxonomy")
    return _normalize_taxonomy(raw)


def _default_keyword_taxonomy() -> dict[str, list[str]]:
    return deepcopy(_DEFAULT_KEYWORD_TAXONOMY)


def get_runtime_keyword_taxonomy(force_refresh: bool = False) -> dict[str, list[str]]:
    now = time.time()
    cached = _taxonomy_cache.get("taxonomy")
    loaded_at = float(_taxonomy_cache.get("loaded_at") or 0.0)
    if not force_refresh and isinstance(cached, dict) and (now - loaded_at) < _CACHE_TTL_SECONDS:
        return deepcopy(cached)

    normalized: dict[str, list[str]] = {}
    try:
        normalized = _load_runtime_keyword_taxonomy_from_db()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to load runtime keyword taxonomy from DB: %s", exc)

    if not normalized:
        normalized = _default_keyword_taxonomy()

    _taxonomy_cache["loaded_at"] = now
    _taxonomy_cache["taxonomy"] = normalized
    return deepcopy(normalized)
