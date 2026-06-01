"""Service layer for frontend channel intake and seed resolver flows."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from celery import Celery
from postgrest.exceptions import APIError

from core.config import settings
from core.logging import get_logger
from core.supabase import supabase_admin
from models.channel import Platform
from models.channel_intake import (
    BulkChannelIntakeRequest,
    IntakeRecordResult,
    IntakeStatus,
    IntakeSummaryResponse,
    ManualChannelIntakeRequest,
    ResolvedChannelCandidate,
    ResolverConfirmRequest,
    ResolverResponse,
    ResolverSeedRequest,
    ResolverSeedResult,
)
from workers.tasks import (
    TASK_SCRAPE_RUMBLE_CHANNEL,
    TASK_SCRAPE_SUBSTACK_CHANNEL,
)
from workers.tasks import TASK_RUN_GATE0
from services import admin_service

logger = get_logger(__name__)

_celery = Celery(broker=settings.redis_url, backend=settings.redis_url)
_URL_SPLIT_PATTERN = re.compile(r"[\n,]+")


def _matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _default_name_from_url(channel_url: str) -> str:
    path = urlsplit(channel_url).path.strip("/")
    if path:
        return path.split("/")[-1]
    return channel_url


def _slugify_seed(seed_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", seed_name.lower()).strip("-")
    return slug or "creator"


def _canonicalize_supported_url(
    raw_url: str, expected_platform: Platform | None = None
) -> tuple[str | None, Platform | None, str | None]:
    try:
        split = urlsplit(raw_url.strip())
    except ValueError:
        return None, None, "Malformed URL"

    if split.scheme not in {"http", "https"}:
        return None, None, "URL must start with http:// or https://"

    host = (split.hostname or "").lower()
    path = re.sub(r"/{2,}", "/", split.path or "/").rstrip("/")
    if not path:
        path = "/"

    if _matches_domain(host, "rumble.com"):
        platform = Platform.rumble
        canonical = urlunsplit(("https", "rumble.com", path, "", ""))
    elif _matches_domain(host, "substack.com"):
        platform = Platform.substack
        subdomain_handle: str | None = None
        if host not in {"substack.com", "www.substack.com"}:
            parts = host.split(".")
            if len(parts) >= 3 and parts[-2:] == ["substack", "com"]:
                subdomain_handle = parts[0]
        handle_path = path.lstrip("/")
        if subdomain_handle:
            canonical = urlunsplit(
                ("https", "substack.com", f"/@{subdomain_handle}", "", "")
            )
        elif handle_path.startswith("@") and "/" not in handle_path:
            canonical = urlunsplit(
                ("https", "substack.com", f"/{handle_path}", "", "")
            )
        else:
            return None, None, "Substack URL must be https://substack.com/@<handle>"
    else:
        return None, None, "Unsupported platform host"

    if expected_platform is not None and platform != expected_platform:
        return None, None, f"URL host does not match selected platform ({expected_platform.value})"
    return canonical, platform, None


def _dispatch_scrape_task(channel_url: str, platform: Platform) -> str:
    task_map = {
        Platform.rumble: TASK_SCRAPE_RUMBLE_CHANNEL,
        Platform.substack: TASK_SCRAPE_SUBSTACK_CHANNEL,
    }
    task_name = task_map[platform]
    task = _celery.send_task(task_name, args=[channel_url])
    return task.id


def _dispatch_gate0_after_scrape(channel_id: str) -> str | None:
    """Queue a manual Gate 0 check after immediate scrape intake dispatch."""
    if not admin_service.is_feature_enabled("gate0"):
        return None

    try:
        supabase_admin.table("channels").update(
            {
                "gate0_status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", channel_id).execute()
    except APIError as exc:
        logger.warning(
            "Failed to mark channel %s as pending Gate 0: %s",
            channel_id,
            exc,
            exc_info=True,
        )

    try:
        task = _celery.send_task(
            TASK_RUN_GATE0,
            args=[channel_id, True],
            countdown=120,
        )
        return task.id
    except Exception as exc:
        logger.warning(
            "Failed to queue Gate 0 after immediate scrape for %s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        return None


def _upsert_channel(
    channel_url: str,
    platform: Platform,
    tags: list[str] | None,
    notes: str | None,
) -> tuple[IntakeStatus, str | None]:
    existing_result = (
        supabase_admin.table("channels")
        .select("id")
        .eq("channel_url", channel_url)
        .maybe_single()
        .execute()
    )
    existing_data = getattr(existing_result, "data", None)
    if isinstance(existing_data, dict) and existing_data.get("id") is not None:
        return IntakeStatus.duplicate, str(existing_data["id"])

    payload: dict[str, object] = {
        "platform": platform.value,
        "channel_url": channel_url,
        "name": _default_name_from_url(channel_url),
        "description": notes or "",
        "niche_tags": tags or [],
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "discovery_source": "manual_frontend",
        "discovery_confidence": 1.0,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }
    result = (
        supabase_admin.table("channels")
        .insert(payload)
        .execute()
    )
    result_data = getattr(result, "data", None)
    if not isinstance(result_data, list) or not result_data:
        return IntakeStatus.invalid, None
    inserted_id = result_data[0].get("id")
    if inserted_id is None:
        return IntakeStatus.invalid, None
    return IntakeStatus.inserted, str(inserted_id)


def _build_summary(message: str, records: list[IntakeRecordResult]) -> IntakeSummaryResponse:
    inserted = sum(1 for record in records if record.status == IntakeStatus.inserted)
    duplicates = sum(1 for record in records if record.status == IntakeStatus.duplicate)
    invalid = sum(1 for record in records if record.status == IntakeStatus.invalid)
    return IntakeSummaryResponse(
        message=message,
        inserted=inserted,
        duplicates=duplicates,
        invalid=invalid,
        records=records,
    )


async def add_manual_channel(body: ManualChannelIntakeRequest) -> IntakeSummaryResponse:
    """Validate and add a single channel from frontend intake form."""
    canonical_url, platform, error = _canonicalize_supported_url(
        body.channel_url,
        expected_platform=body.platform,
    )
    if canonical_url is None or platform is None:
        return _build_summary(
            "Channel intake complete",
            [
                IntakeRecordResult(
                    input_value=body.channel_url,
                    status=IntakeStatus.invalid,
                    reason=error,
                )
            ],
        )

    try:
        status, channel_id = _upsert_channel(
            canonical_url,
            platform,
            body.tags,
            body.notes,
        )
        scrape_task_id = None
        if body.trigger_scrape_now and status in {
            IntakeStatus.inserted,
            IntakeStatus.duplicate,
        }:
            scrape_task_id = _dispatch_scrape_task(canonical_url, platform)
            if channel_id is not None:
                _dispatch_gate0_after_scrape(channel_id)
        return _build_summary(
            "Channel intake complete",
            [
                IntakeRecordResult(
                    input_value=body.channel_url,
                    status=status,
                    channel_url=canonical_url,
                    platform=platform,
                    channel_id=channel_id,
                    scrape_task_id=scrape_task_id,
                )
            ],
        )
    except APIError as exc:
        logger.error("Manual channel intake failed: %s", exc, exc_info=True)
        return _build_summary(
            "Channel intake complete",
            [
                IntakeRecordResult(
                    input_value=body.channel_url,
                    status=IntakeStatus.invalid,
                    reason=str(exc),
                )
            ],
        )


def _parse_bulk_urls(urls_text: str) -> list[str]:
    parts = _URL_SPLIT_PATTERN.split(urls_text)
    return [part.strip() for part in parts if part.strip()]


async def add_bulk_channels(body: BulkChannelIntakeRequest) -> IntakeSummaryResponse:
    """Bulk insert channels from newline/comma separated URLs."""
    records: list[IntakeRecordResult] = []
    for raw_url in _parse_bulk_urls(body.urls_text):
        canonical_url, platform, error = _canonicalize_supported_url(raw_url)
        if canonical_url is None or platform is None:
            records.append(
                IntakeRecordResult(
                    input_value=raw_url,
                    status=IntakeStatus.invalid,
                    reason=error,
                )
            )
            continue

        try:
            status, channel_id = _upsert_channel(canonical_url, platform, [], None)
            scrape_task_id = None
            if body.trigger_scrape_now and status in {
                IntakeStatus.inserted,
                IntakeStatus.duplicate,
            }:
                scrape_task_id = _dispatch_scrape_task(canonical_url, platform)
                if channel_id is not None:
                    _dispatch_gate0_after_scrape(channel_id)
            records.append(
                IntakeRecordResult(
                    input_value=raw_url,
                    status=status,
                    channel_url=canonical_url,
                    platform=platform,
                    channel_id=channel_id,
                    scrape_task_id=scrape_task_id,
                )
            )
        except APIError as exc:
            logger.error("Bulk intake failed for %s: %s", raw_url, exc, exc_info=True)
            records.append(
                IntakeRecordResult(
                    input_value=raw_url,
                    status=IntakeStatus.invalid,
                    reason=str(exc),
                )
            )

    return _build_summary("Bulk intake complete", records)


def _name_score(seed_name: str, channel_name: str) -> float:
    seed = seed_name.lower().strip()
    channel = channel_name.lower().strip()
    if not seed or not channel:
        return 0.0
    if seed == channel:
        return 1.0
    if seed in channel:
        return 0.84
    seed_tokens = {token for token in re.split(r"\W+", seed) if token}
    channel_tokens = {token for token in re.split(r"\W+", channel) if token}
    if not seed_tokens or not channel_tokens:
        return 0.0
    overlap = len(seed_tokens & channel_tokens)
    return overlap / len(seed_tokens)


def _guess_urls_for_seed(seed_name: str) -> list[ResolvedChannelCandidate]:
    slug = _slugify_seed(seed_name)
    return [
        ResolvedChannelCandidate(
            platform=Platform.rumble,
            channel_url=f"https://rumble.com/c/{slug}",
            channel_name=seed_name,
            confidence=0.35,
            source="guessed",
        ),
        ResolvedChannelCandidate(
            platform=Platform.substack,
            channel_url=f"https://substack.com/@{slug}",
            channel_name=seed_name,
            confidence=0.35,
            source="guessed",
        ),
    ]


async def resolve_seed_creators(
    body: ResolverSeedRequest,
) -> ResolverResponse:
    """Resolve seed creator names to likely channel URLs for user confirmation."""
    try:
        channels_result = (
            supabase_admin.table("channels")
            .select("name,platform,channel_url,is_active")
            .eq("is_active", True)
            .execute()
        )
    except APIError as exc:
        logger.error("Resolver failed to query channels: %s", exc, exc_info=True)
        return ResolverResponse(results=[], unresolved=body.seed_names)

    rows = channels_result.data or []
    results: list[ResolverSeedResult] = []
    unresolved: list[str] = []

    for seed_name in body.seed_names:
        candidates: list[ResolvedChannelCandidate] = []
        for row in rows:
            channel_name = str(row.get("name") or "")
            score = _name_score(seed_name, channel_name)
            if score < 0.45:
                continue

            raw_platform = str(row.get("platform") or "").lower()
            if raw_platform not in {"rumble", "substack"}:
                continue
            candidates.append(
                ResolvedChannelCandidate(
                    platform=Platform(raw_platform),
                    channel_url=str(row.get("channel_url") or ""),
                    channel_name=channel_name,
                    confidence=round(min(score, 1.0), 2),
                    source="existing",
                )
            )

        unique_by_url: dict[str, ResolvedChannelCandidate] = {}
        for candidate in sorted(
            candidates, key=lambda item: item.confidence, reverse=True
        ):
            unique_by_url.setdefault(candidate.channel_url, candidate)
        final_candidates = list(unique_by_url.values())[: body.limit_per_seed]

        if not final_candidates:
            final_candidates = _guess_urls_for_seed(seed_name)
            unresolved.append(seed_name)

        results.append(
            ResolverSeedResult(seed_name=seed_name, candidates=final_candidates)
        )

    return ResolverResponse(results=results, unresolved=unresolved)


async def confirm_resolver_selections(
    body: ResolverConfirmRequest,
) -> IntakeSummaryResponse:
    """Insert user-confirmed resolver selections."""
    records: list[IntakeRecordResult] = []
    for selection in body.selections:
        canonical_url, platform, error = _canonicalize_supported_url(
            selection.channel_url,
            expected_platform=selection.platform,
        )
        if canonical_url is None or platform is None:
            records.append(
                IntakeRecordResult(
                    input_value=selection.channel_url,
                    status=IntakeStatus.invalid,
                    reason=error,
                )
            )
            continue

        try:
            status, channel_id = _upsert_channel(
                canonical_url,
                platform,
                selection.tags,
                selection.notes,
            )
            scrape_task_id = None
            if body.trigger_scrape_now and status in {
                IntakeStatus.inserted,
                IntakeStatus.duplicate,
            }:
                scrape_task_id = _dispatch_scrape_task(canonical_url, platform)
                if channel_id is not None:
                    _dispatch_gate0_after_scrape(channel_id)
            records.append(
                IntakeRecordResult(
                    input_value=selection.channel_url,
                    status=status,
                    channel_url=canonical_url,
                    platform=platform,
                    channel_id=channel_id,
                    scrape_task_id=scrape_task_id,
                )
            )
        except APIError as exc:
            logger.error(
                "Resolver confirm intake failed for %s: %s",
                selection.channel_url,
                exc,
                exc_info=True,
            )
            records.append(
                IntakeRecordResult(
                    input_value=selection.channel_url,
                    status=IntakeStatus.invalid,
                    reason=str(exc),
                )
            )

    return _build_summary("Resolver intake complete", records)
