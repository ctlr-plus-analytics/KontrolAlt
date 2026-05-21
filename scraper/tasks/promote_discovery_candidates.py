"""Promote staged discovery candidates into channels after lightweight verification."""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlsplit

import httpx
from postgrest.exceptions import APIError

from worker import celery_app
from core.supabase import get_supabase_client
from tasks.discovery_candidates import (
    promote_candidate_to_channel,
    safe_reject_candidate,
    safe_verify_candidate,
)
from tasks.scrape_bitchute import scrape_bitchute_channel
from tasks.scrape_rumble import scrape_rumble_channel

logger = logging.getLogger(__name__)

_VERIFY_TIMEOUT_SECONDS = float(os.environ.get("DISCOVERY_VERIFY_TIMEOUT_SECONDS", "15"))
_PROMOTE_LIMIT = int(os.environ.get("DISCOVERY_PROMOTE_LIMIT", "1500"))
_MIN_PROMOTE_CONFIDENCE = float(os.environ.get("DISCOVERY_MIN_PROMOTE_CONFIDENCE", "0.62"))
_PROMOTED_SCRAPE_LIMIT = int(os.environ.get("DISCOVERY_PROMOTED_SCRAPE_LIMIT", "500"))


def _is_channel_shaped_url(url: str, platform: str) -> bool:
    """Return whether URL shape matches expected channel path for a platform."""
    split = urlsplit(url)
    path = re.sub(r"/{2,}", "/", split.path or "/").rstrip("/")
    parts = [part for part in path.split("/") if part]
    if platform == "rumble":
        return len(parts) >= 2 and parts[0] in {"c", "user"}
    if platform == "bitchute":
        return len(parts) >= 2 and parts[0] == "channel"
    return False


def _http_verify(url: str) -> tuple[bool, str | None]:
    """Perform lightweight HTTP verification."""
    try:
        with httpx.Client(timeout=_VERIFY_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(url)
        if response.status_code == 404:
            return False, "http_404"
        if response.status_code >= 500:
            return False, f"http_{response.status_code}"
        if response.status_code >= 400:
            return False, f"http_{response.status_code}"
        return True, None
    except httpx.HTTPError as exc:
        return False, f"http_error:{exc.__class__.__name__}"


def promote_discovery_candidates_now() -> dict[str, object]:
    """Synchronously verify and promote staged candidates."""
    client = get_supabase_client()
    candidates_result = (
        client.table("discovery_candidates")
        .select("id,candidate_url,platform,source,source_ref,title,confidence,evidence_count,status")
        .eq("status", "pending")
        .order("confidence", desc=True)
        .order("evidence_count", desc=True)
        .limit(_PROMOTE_LIMIT)
        .execute()
    )
    candidates = candidates_result.data or []

    verified = 0
    promoted = 0
    scrape_queued = 0
    rejected = 0
    skipped_low_confidence = 0

    for candidate in candidates:
        candidate_id = str(candidate["id"])
        url = str(candidate.get("candidate_url") or "")
        platform = str(candidate.get("platform") or "")
        confidence = float(candidate.get("confidence") or 0.0)

        if confidence < _MIN_PROMOTE_CONFIDENCE:
            skipped_low_confidence += 1
            continue

        if not _is_channel_shaped_url(url, platform):
            safe_reject_candidate(
                client=client,
                candidate_id=candidate_id,
                reason="invalid_channel_shape",
            )
            rejected += 1
            continue

        ok, reject_reason = _http_verify(url)
        if not ok:
            safe_reject_candidate(
                client=client,
                candidate_id=candidate_id,
                reason=reject_reason or "verification_failed",
            )
            rejected += 1
            continue

        safe_verify_candidate(client=client, candidate_id=candidate_id)
        verified += 1
        if promote_candidate_to_channel(client=client, candidate=candidate):
            promoted += 1
            if scrape_queued < _PROMOTED_SCRAPE_LIMIT:
                if platform == "rumble":
                    scrape_rumble_channel.delay(url)
                    scrape_queued += 1
                elif platform == "bitchute":
                    scrape_bitchute_channel.delay(url)
                    scrape_queued += 1

    return {
        "scanned": len(candidates),
        "verified": verified,
        "promoted": promoted,
        "scrape_queued": scrape_queued,
        "rejected": rejected,
        "skipped_low_confidence": skipped_low_confidence,
    }


@celery_app.task(name="scraper.tasks.promote_discovery_candidates")
def promote_discovery_candidates() -> dict[str, object]:
    """Run staged-candidate promotion task."""
    logger.info("Starting promotion of staged discovery candidates")
    try:
        result = promote_discovery_candidates_now()
        logger.info(
            "Discovery promotion complete: scanned=%d verified=%d promoted=%d rejected=%d",
            result["scanned"],
            result["verified"],
            result["promoted"],
            result["rejected"],
        )
        return result
    except (APIError, KeyError, TypeError, ValueError) as exc:
        logger.error("Discovery promotion failed: %s", exc, exc_info=True)
        return {
            "scanned": 0,
            "verified": 0,
            "promoted": 0,
            "scrape_queued": 0,
            "rejected": 0,
            "skipped_low_confidence": 0,
            "error": str(exc),
        }

