"""Celery task: auto-discover and promote channels from known-channel content."""

import logging
import os
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from postgrest.exceptions import APIError

from worker import celery_app
from core.supabase import get_supabase_client
from tasks.discovery_candidates import stage_candidate

logger = logging.getLogger(__name__)

SUPPORTED_HOSTS = {
    "rumble.com": "rumble",
    "www.rumble.com": "rumble",
    "bitchute.com": "bitchute",
    "www.bitchute.com": "bitchute",
}
URL_PATTERN = re.compile(r"https?://[^\s<>\]\"')]+", re.IGNORECASE)
BARE_SUPPORTED_URL_PATTERN = re.compile(
    r"\b(?:www\.)?(?:rumble\.com|bitchute\.com)/[^\s<>\]\"')]+",
    re.IGNORECASE,
)
RUMBLE_SLUG_PATTERN = re.compile(
    r"\b(?:rumble\.com/)?(?:c|user)/([a-zA-Z0-9_\-]{3,64})\b",
    re.IGNORECASE,
)
BITCHUTE_SLUG_PATTERN = re.compile(
    r"\b(?:bitchute\.com/)?channel/([a-zA-Z0-9_\-]{3,64})\b",
    re.IGNORECASE,
)
_DISCOVERY_CONFIDENCE = 0.86
_CANDIDATE_STAGE_LIMIT = int(os.environ.get("SEED_EXPANSION_STAGE_LIMIT", "5000"))


def _normalize_text_values(value: object) -> list[str]:
    """Normalize arbitrary text-ish values into a flat list of strings."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int, float))]
    return []


def _extract_urls(text: str) -> list[str]:
    """Extract candidate URLs from a text blob."""
    urls = {match.group(0).rstrip(".,;:!?") for match in URL_PATTERN.finditer(text)}
    for match in BARE_SUPPORTED_URL_PATTERN.finditer(text):
        candidate = match.group(0).rstrip(".,;:!?")
        if not candidate.lower().startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        urls.add(candidate)
    return list(urls)


def _canonicalize_supported_channel_url(raw_url: str) -> tuple[str | None, str | None]:
    """Return canonical channel URL + platform for supported hosts only."""
    normalized = raw_url.strip()
    if normalized and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        normalized = f"https://{normalized}"

    try:
        split = urlsplit(normalized)
    except ValueError:
        return None, None

    host = split.hostname.lower() if split.hostname else ""
    platform = SUPPORTED_HOSTS.get(host)
    if platform is None:
        return None, None

    cleaned_path = re.sub(r"/{2,}", "/", split.path or "/").rstrip("/")
    if not cleaned_path:
        cleaned_path = "/"

    allowed_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(split.query, keep_blank_values=False):
        if platform == "rumble" and key in {"channel", "username"}:
            allowed_query.append((key, value))

    canonical = urlunsplit(
        (
            "https",
            host.replace("www.", ""),
            cleaned_path,
            "&".join(f"{k}={v}" for k, v in allowed_query),
            "",
        )
    )
    return canonical, platform


def _collect_candidate_urls(channel: dict[str, object]) -> set[tuple[str, str]]:
    """Extract and canonicalize candidate URLs from one channel row."""
    blobs: list[str] = []
    blobs.extend(_normalize_text_values(channel.get("video_titles")))
    blobs.extend(_normalize_text_values(channel.get("contact_info")))
    blobs.extend(_normalize_text_values(channel.get("secondary_urls")))
    blobs.extend(_normalize_text_values(channel.get("description")))
    blobs.extend(_normalize_text_values(channel.get("channel_url")))

    candidates: set[tuple[str, str]] = set()
    for blob in blobs:
        for raw_url in _extract_urls(blob):
            canonical, platform = _canonicalize_supported_channel_url(raw_url)
            if canonical is None or platform is None:
                continue
            candidates.add((canonical, platform))
        for match in RUMBLE_SLUG_PATTERN.finditer(blob):
            slug = match.group(1).strip()
            if slug:
                candidates.add((f"https://rumble.com/c/{slug}", "rumble"))
                candidates.add((f"https://rumble.com/user/{slug}", "rumble"))
        for match in BITCHUTE_SLUG_PATTERN.finditer(blob):
            slug = match.group(1).strip()
            if slug:
                candidates.add((f"https://bitchute.com/channel/{slug}", "bitchute"))
    return candidates


def _discover_from_known_channels_sync() -> dict[str, object]:
    """Discover and stage candidate channels from known content."""
    client = get_supabase_client()
    source_rows = (
        client.table("channels")
        .select(
            "id,channel_url,platform,name,description,video_titles,contact_info,secondary_urls"
        )
        .execute()
    )
    channels = source_rows.data or []

    existing_rows = client.table("channels").select("channel_url").execute()
    known_urls: set[str] = set()
    for row in existing_rows.data or []:
        raw = str(row.get("channel_url") or "")
        canonical, _ = _canonicalize_supported_channel_url(raw)
        if canonical:
            known_urls.add(canonical)

    discovered = 0
    staged = 0
    already_staged = 0
    duplicates = 0
    invalid = 0

    for channel in channels:
        if staged >= _CANDIDATE_STAGE_LIMIT:
            break
        source_channel_id = str(channel.get("id"))
        source_name = str(channel.get("name") or "")

        for candidate_url, platform in _collect_candidate_urls(channel):
            if staged >= _CANDIDATE_STAGE_LIMIT:
                break
            discovered += 1

            if candidate_url in known_urls:
                duplicates += 1
                continue

            try:
                did_stage, existed = stage_candidate(
                    client=client,
                    candidate_url=candidate_url,
                    platform=platform,
                    source="seed",
                    source_ref=source_channel_id,
                    title=candidate_url.rstrip("/").split("/")[-1] or candidate_url,
                    category=None,
                    confidence=_DISCOVERY_CONFIDENCE,
                )
            except APIError:
                invalid += 1
                continue

            if did_stage:
                known_urls.add(candidate_url)
                if existed:
                    already_staged += 1
                else:
                    staged += 1
                logger.info(
                    "Seed expansion staged %s candidate: %s (source=%s)",
                    platform,
                    candidate_url,
                    source_name or source_channel_id,
                )

    return {
        "source_channels": len(channels),
        "discovered": discovered,
        "staged": staged,
        "already_staged": already_staged,
        "duplicates": duplicates,
        "invalid": invalid,
    }


def discover_seed_expansion_now() -> dict[str, object]:
    """Run seed expansion synchronously for in-process orchestration hooks."""
    return _discover_from_known_channels_sync()


@celery_app.task(name="scraper.tasks.discover_seed_expansion")
def discover_seed_expansion() -> dict[str, object]:
    """Auto-discover channels from known-channel content and promote immediately."""
    logger.info("Starting seed expansion discovery")
    try:
        result = _discover_from_known_channels_sync()
        logger.info(
            "Seed expansion finished: discovered=%d staged=%d duplicates=%d invalid=%d",
            result["discovered"],
            result["staged"],
            result["duplicates"],
            result["invalid"],
        )
        return result
    except (APIError, KeyError, TypeError, ValueError) as exc:
        logger.error("Seed expansion failed: %s", exc, exc_info=True)
        return {
            "source_channels": 0,
            "discovered": 0,
            "staged": 0,
            "already_staged": 0,
            "duplicates": 0,
            "invalid": 1,
            "error": str(exc),
        }
