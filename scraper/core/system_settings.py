"""Runtime settings reader for scraper workflows."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx
from postgrest.exceptions import APIError

try:
    from supabase._sync.client import SupabaseException
except ImportError:
    class SupabaseException(Exception):
        """Fallback when tests stub the supabase package."""


from core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
_SETTINGS_TABLE = "system_settings"
_SETTINGS_KEY = "global"
_SETTINGS_CACHE_TTL_SECONDS = 60.0
_cached_settings: RuntimeSettings | None = None
_cached_settings_at: float = 0.0
_HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_GENERIC_GATE0_BRAND_TERMS = {
    "gold",
    "ira",
    "silver",
    "coin",
    "coins",
    "bullion",
    "precious",
    "metals",
}


@dataclass(frozen=True)
class Gate0CompetitorSetting:
    """Runtime Gate 0 competitor definition."""

    brand: str
    domains: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeSettings:
    settings_loaded: bool = True
    daily_scrape_utc_time: str = "02:00"
    gate0_enabled: bool = True
    discovery_enabled: bool = True
    lookalike_enabled: bool = True
    scrape_platform_priority: tuple[str, ...] = ("rumble", "bitchute")
    scrape_only_new_or_missing_metrics: bool = True
    scrape_rescrape_min_hours: int = 72
    weekly_velocity_enabled: bool = True
    weekly_velocity_utc_day: str = "sun"
    weekly_velocity_utc_time: str = "03:00"
    velocity_weekly_min_avg_comments: float = 20.0
    velocity_weekly_min_avg_views: float = 0.0
    velocity_weekly_min_subscribers: int = 0
    velocity_weekly_stale_hours: int = 144
    scrape_dispatch_batch_size: int = 1
    scrape_dispatch_pause_seconds: float = 5.0
    scrape_run_max_channels: int = 0
    scrape_daily_byte_budget_mb: int = 0
    scrape_retry_base_delay_seconds: int = 60
    scrape_retry_jitter_min: float = 0.5
    scrape_retry_jitter_max: float = 1.2
    scrape_blocked_retry_multiplier: float = 2.0
    scrape_blocked_retry_min_seconds: int = 180
    scrape_platform_slot_limit_rumble: int = 1
    scrape_platform_slot_limit_bitchute: int = 1
    scrape_circuit_breaker_fail_threshold: int = 5
    scrape_circuit_breaker_window_seconds: int = 1800
    scrape_circuit_breaker_cooldown_seconds: int = 1800
    gate0_daily_queue_limit: int = 200
    gate0_clean_recheck_days: int = 7
    gate0_competitors: tuple[Gate0CompetitorSetting, ...] = (
        Gate0CompetitorSetting("Noble Gold", ("noblegold.com",)),
        Gate0CompetitorSetting("Birch Gold", ("birchgold.com",)),
        Gate0CompetitorSetting("Patriot Gold", ("patriotgold.com",)),
        Gate0CompetitorSetting("Kirk Elliot", ("kirkelliot.com",)),
    )
    scraper_human_delay_min_seconds: float = 2.0
    scraper_human_delay_max_seconds: float = 8.0
    scraper_content_wait_min_bytes: int = 5000
    scraper_content_wait_timeout_seconds: float = 20.0
    scraper_content_wait_poll_seconds: float = 1.5
    scraper_challenge_second_cycle_enabled: bool = True
    scraper_challenge_second_cycle_pre_reload_delay_seconds: float = 10.0
    scraper_challenge_second_cycle_post_reload_delay_seconds: float = 8.0
    scraper_challenge_second_cycle_wait_timeout_seconds: float = 25.0
    scraper_block_resource_images: bool = True
    scraper_block_resource_media: bool = True
    scraper_block_resource_fonts: bool = True
    discovery_serper_query_limit: int = 480
    discovery_results_per_query: int = 20
    discovery_max_pages_per_query: int = 8
    discovery_insert_limit: int = 20000
    discovery_query_stagnation_limit: int = 4
    discovery_global_stop_no_new: int = 120
    discovery_max_feedback_terms: int = 36
    discovery_new_scrape_limit: int = 500
    discovery_channel_page_size: int = 1000
    discovery_verify_timeout_seconds: float = 15.0
    scrape_confidence_min_view_samples: int = 6
    scrape_confidence_min_comment_samples: int = 4
    scrape_quality_recovery_video_pages: int = 1
    scraper_fallback_concurrency_rumble: int = 3
    scraper_fallback_concurrency_bitchute: int = 1
    scraper_rumble_video_page_fallback_limit: int = 3
    cf_bypass_max_rpm_residential: int = 20
    cf_bypass_max_rpm_bitchute: int = 8
    cf_bypass_delay_min_s: float = 0.8
    cf_bypass_delay_max_s: float = 5.0
    cf_bypass_delay_long_pause_probability: float = 0.08
    cf_bypass_delay_long_pause_max_s: float = 12.0
    cf_bypass_inter_request_base_s: float = 1.2
    cf_bypass_inter_request_variance: float = 0.8
    cf_bypass_scroll_steps_min: int = 4
    cf_bypass_scroll_steps_max: int = 9
    cf_bypass_session_cooldown_seconds: int = 1800
    cf_bypass_origin_check_enabled: bool = False
    cf_bypass_fingerprint_strict_mode: bool = False
    cf_bypass_captcha_skip_enabled: bool = True


def _as_non_negative_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _as_non_negative_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _parse_gate0_competitors(value: object) -> tuple[Gate0CompetitorSetting, ...]:
    if not isinstance(value, list):
        return RuntimeSettings.__dataclass_fields__["gate0_competitors"].default

    competitors: list[Gate0CompetitorSetting] = []
    seen_brands: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        brand = " ".join(str(item.get("brand") or "").strip().split())
        if not brand:
            continue
        brand_terms = {
            term for term in re.findall(r"[a-z0-9]+", brand.lower()) if term
        }
        if brand_terms and brand_terms.issubset(_GENERIC_GATE0_BRAND_TERMS):
            continue
        brand_key = brand.lower()
        if brand_key in seen_brands:
            continue

        raw_domains = item.get("domains") or []
        if not isinstance(raw_domains, list):
            raw_domains = []
        domains: list[str] = []
        seen_domains: set[str] = set()
        for raw_domain in raw_domains:
            domain = str(raw_domain).strip().lower()
            domain = domain.removeprefix("https://").removeprefix("http://")
            domain = domain.split("/", 1)[0]
            if (
                not domain
                or domain in seen_domains
                or not _HOSTNAME_PATTERN.match(domain)
            ):
                continue
            seen_domains.add(domain)
            domains.append(domain)

        seen_brands.add(brand_key)
        competitors.append(Gate0CompetitorSetting(brand, tuple(domains)))

    return tuple(competitors)


def get_runtime_settings() -> RuntimeSettings:
    """Fetch runtime settings with safe defaults on any read error."""
    global _cached_settings, _cached_settings_at
    now = time.monotonic()
    if _cached_settings is not None and now - _cached_settings_at < _SETTINGS_CACHE_TTL_SECONDS:
        return _cached_settings

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
        raw_weekly_time = str(row.get("weekly_velocity_utc_time") or "03:00:00")
        weekly_day = str(row.get("weekly_velocity_utc_day") or "sun").lower()
        if weekly_day not in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
            weekly_day = "sun"
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
        settings = RuntimeSettings(
            daily_scrape_utc_time=raw_time[:5],
            gate0_enabled=bool(row.get("gate0_enabled", True)),
            discovery_enabled=bool(row.get("discovery_enabled", True)),
            lookalike_enabled=bool(row.get("lookalike_enabled", True)),
            scrape_platform_priority=priority,
            scrape_only_new_or_missing_metrics=bool(
                row.get("scrape_only_new_or_missing_metrics", True)
            ),
            scrape_rescrape_min_hours=_as_non_negative_int(
                row.get("scrape_rescrape_min_hours"), 72
            ),
            weekly_velocity_enabled=bool(row.get("weekly_velocity_enabled", True)),
            weekly_velocity_utc_day=weekly_day,
            weekly_velocity_utc_time=raw_weekly_time[:5],
            velocity_weekly_min_avg_comments=_as_non_negative_float(
                row.get("velocity_weekly_min_avg_comments"), 20.0
            ),
            velocity_weekly_min_avg_views=_as_non_negative_float(
                row.get("velocity_weekly_min_avg_views"), 0.0
            ),
            velocity_weekly_min_subscribers=_as_non_negative_int(
                row.get("velocity_weekly_min_subscribers"), 0
            ),
            velocity_weekly_stale_hours=_as_non_negative_int(
                row.get("velocity_weekly_stale_hours"), 144
            ),
            scrape_dispatch_batch_size=max(
                1, _as_non_negative_int(row.get("scrape_dispatch_batch_size"), 1)
            ),
            scrape_dispatch_pause_seconds=_as_non_negative_float(
                row.get("scrape_dispatch_pause_seconds"), 5.0
            ),
            scrape_run_max_channels=_as_non_negative_int(
                row.get("scrape_run_max_channels"), 0
            ),
            scrape_daily_byte_budget_mb=_as_non_negative_int(
                row.get("scrape_daily_byte_budget_mb"), 0
            ),
            scrape_retry_base_delay_seconds=max(
                1,
                _as_non_negative_int(row.get("scrape_retry_base_delay_seconds"), 60),
            ),
            scrape_retry_jitter_min=_as_non_negative_float(
                row.get("scrape_retry_jitter_min"), 0.5
            ),
            scrape_retry_jitter_max=max(
                _as_non_negative_float(row.get("scrape_retry_jitter_min"), 0.5),
                _as_non_negative_float(row.get("scrape_retry_jitter_max"), 1.2),
            ),
            scrape_blocked_retry_multiplier=max(
                1.0,
                _as_non_negative_float(row.get("scrape_blocked_retry_multiplier"), 2.0),
            ),
            scrape_blocked_retry_min_seconds=max(
                1,
                _as_non_negative_int(row.get("scrape_blocked_retry_min_seconds"), 180),
            ),
            scrape_platform_slot_limit_rumble=_as_non_negative_int(
                row.get("scrape_platform_slot_limit_rumble"), 1
            ),
            scrape_platform_slot_limit_bitchute=_as_non_negative_int(
                row.get("scrape_platform_slot_limit_bitchute"), 1
            ),
            scrape_circuit_breaker_fail_threshold=max(
                1,
                _as_non_negative_int(
                    row.get("scrape_circuit_breaker_fail_threshold"), 5
                ),
            ),
            scrape_circuit_breaker_window_seconds=max(
                1,
                _as_non_negative_int(
                    row.get("scrape_circuit_breaker_window_seconds"), 1800
                ),
            ),
            scrape_circuit_breaker_cooldown_seconds=max(
                1,
                _as_non_negative_int(
                    row.get("scrape_circuit_breaker_cooldown_seconds"), 1800
                ),
            ),
            gate0_daily_queue_limit=_as_non_negative_int(
                row.get("gate0_daily_queue_limit"), 200
            ),
            gate0_clean_recheck_days=_as_non_negative_int(
                row.get("gate0_clean_recheck_days"), 7
            ),
            gate0_competitors=_parse_gate0_competitors(
                row.get("gate0_competitors")
            ),
            scraper_human_delay_min_seconds=_as_non_negative_float(
                row.get("scraper_human_delay_min_seconds"), 2.0
            ),
            scraper_human_delay_max_seconds=max(
                _as_non_negative_float(
                    row.get("scraper_human_delay_min_seconds"), 2.0
                ),
                _as_non_negative_float(
                    row.get("scraper_human_delay_max_seconds"), 8.0
                ),
            ),
            scraper_content_wait_min_bytes=_as_non_negative_int(
                row.get("scraper_content_wait_min_bytes"), 5000
            ),
            scraper_content_wait_timeout_seconds=_as_non_negative_float(
                row.get("scraper_content_wait_timeout_seconds"), 20.0
            ),
            scraper_content_wait_poll_seconds=max(
                0.1,
                _as_non_negative_float(
                    row.get("scraper_content_wait_poll_seconds"), 1.5
                ),
            ),
            scraper_challenge_second_cycle_enabled=bool(
                row.get("scraper_challenge_second_cycle_enabled", True)
            ),
            scraper_challenge_second_cycle_pre_reload_delay_seconds=_as_non_negative_float(
                row.get("scraper_challenge_second_cycle_pre_reload_delay_seconds"), 10.0
            ),
            scraper_challenge_second_cycle_post_reload_delay_seconds=_as_non_negative_float(
                row.get("scraper_challenge_second_cycle_post_reload_delay_seconds"), 8.0
            ),
            scraper_challenge_second_cycle_wait_timeout_seconds=max(
                0.1,
                _as_non_negative_float(
                    row.get("scraper_challenge_second_cycle_wait_timeout_seconds"), 25.0
                ),
            ),
            scraper_block_resource_images=bool(
                row.get("scraper_block_resource_images", True)
            ),
            scraper_block_resource_media=bool(
                row.get("scraper_block_resource_media", True)
            ),
            scraper_block_resource_fonts=bool(
                row.get("scraper_block_resource_fonts", True)
            ),
            discovery_serper_query_limit=_as_non_negative_int(
                row.get("discovery_serper_query_limit"), 480
            ),
            discovery_results_per_query=max(
                1, _as_non_negative_int(row.get("discovery_results_per_query"), 20)
            ),
            discovery_max_pages_per_query=max(
                1, _as_non_negative_int(row.get("discovery_max_pages_per_query"), 8)
            ),
            discovery_insert_limit=_as_non_negative_int(
                row.get("discovery_insert_limit"), 20000
            ),
            discovery_query_stagnation_limit=max(
                1,
                _as_non_negative_int(row.get("discovery_query_stagnation_limit"), 4),
            ),
            discovery_global_stop_no_new=max(
                1,
                _as_non_negative_int(row.get("discovery_global_stop_no_new"), 120),
            ),
            discovery_max_feedback_terms=_as_non_negative_int(
                row.get("discovery_max_feedback_terms"), 36
            ),
            discovery_new_scrape_limit=_as_non_negative_int(
                row.get("discovery_new_scrape_limit"), 500
            ),
            discovery_channel_page_size=max(
                1, _as_non_negative_int(row.get("discovery_channel_page_size"), 1000)
            ),
            discovery_verify_timeout_seconds=_as_non_negative_float(
                row.get("discovery_verify_timeout_seconds"), 15.0
            ),
            scrape_confidence_min_view_samples=max(
                1, _as_non_negative_int(row.get("scrape_confidence_min_view_samples"), 6)
            ),
            scrape_confidence_min_comment_samples=max(
                1, _as_non_negative_int(row.get("scrape_confidence_min_comment_samples"), 4)
            ),
            scrape_quality_recovery_video_pages=max(
                1, _as_non_negative_int(row.get("scrape_quality_recovery_video_pages"), 1)
            ),
            scraper_fallback_concurrency_rumble=max(
                1, _as_non_negative_int(row.get("scraper_fallback_concurrency_rumble"), 3)
            ),
            scraper_fallback_concurrency_bitchute=max(
                1, _as_non_negative_int(row.get("scraper_fallback_concurrency_bitchute"), 1)
            ),
            scraper_rumble_video_page_fallback_limit=max(
                1, _as_non_negative_int(row.get("scraper_rumble_video_page_fallback_limit"), 3)
            ),
            cf_bypass_max_rpm_residential=max(
                5, _as_non_negative_int(row.get("cf_bypass_max_rpm_residential"), 20)
            ),
            cf_bypass_max_rpm_bitchute=max(
                3, _as_non_negative_int(row.get("cf_bypass_max_rpm_bitchute"), 8)
            ),
            cf_bypass_delay_min_s=max(
                0.1, _as_non_negative_float(row.get("cf_bypass_delay_min_s"), 0.8)
            ),
            cf_bypass_delay_max_s=max(
                0.5, _as_non_negative_float(row.get("cf_bypass_delay_max_s"), 5.0)
            ),
            cf_bypass_delay_long_pause_probability=min(
                0.5,
                max(
                    0.0,
                    float(row.get("cf_bypass_delay_long_pause_probability", 0.08)),
                ),
            ),
            cf_bypass_delay_long_pause_max_s=max(
                3.0,
                _as_non_negative_float(row.get("cf_bypass_delay_long_pause_max_s"), 12.0),
            ),
            cf_bypass_inter_request_base_s=max(
                0.2, _as_non_negative_float(row.get("cf_bypass_inter_request_base_s"), 1.2)
            ),
            cf_bypass_inter_request_variance=max(
                0.0, _as_non_negative_float(row.get("cf_bypass_inter_request_variance"), 0.8)
            ),
            cf_bypass_scroll_steps_min=max(
                1, _as_non_negative_int(row.get("cf_bypass_scroll_steps_min"), 4)
            ),
            cf_bypass_scroll_steps_max=max(
                2, _as_non_negative_int(row.get("cf_bypass_scroll_steps_max"), 9)
            ),
            cf_bypass_session_cooldown_seconds=max(
                60, _as_non_negative_int(row.get("cf_bypass_session_cooldown_seconds"), 1800)
            ),
            cf_bypass_origin_check_enabled=bool(
                row.get("cf_bypass_origin_check_enabled", False)
            ),
            cf_bypass_fingerprint_strict_mode=bool(
                row.get("cf_bypass_fingerprint_strict_mode", False)
            ),
            cf_bypass_captcha_skip_enabled=bool(
                row.get("cf_bypass_captcha_skip_enabled", True)
            ),
        )
        _cached_settings = settings
        _cached_settings_at = now
        return settings
    except (
        APIError,
        SupabaseException,
        httpx.HTTPError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:
        logger.warning("Failed to load runtime settings; using defaults: %s", exc)
        settings = RuntimeSettings(settings_loaded=False)
        _cached_settings = settings
        _cached_settings_at = now
        return settings
