from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gate0CompetitorSetting:
    brand: str
    domains: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeSettings:
    settings_loaded: bool = True
    daily_scrape_utc_time: str = "02:00"
    gate0_enabled: bool = True
    discovery_enabled: bool = False
    lookalike_enabled: bool = True
    scrape_platform_priority: tuple[str, ...] = ("substack", "rumble", "bitchute")
    scrape_only_new_or_missing_metrics: bool = True
    scrape_rescrape_min_hours: int = 72
    weekly_velocity_enabled: bool = True
    weekly_velocity_utc_day: str = "sun"
    weekly_velocity_utc_time: str = "03:00"
    velocity_weekly_min_avg_comments: float = 20.0
    velocity_weekly_min_avg_views: float = 0.0
    velocity_weekly_min_subscribers: int = 0
    velocity_weekly_stale_hours: int = 144
    scrape_dispatch_batch_size: int = 3
    scrape_dispatch_pause_seconds: float = 5.0
    scrape_run_max_channels: int = 0
    scrape_daily_byte_budget_mb: int = 0
    scrape_run_max_retries_per_channel: int = 1
    scrape_retry_base_delay_seconds: int = 60
    scrape_retry_jitter_min: float = 0.5
    scrape_retry_jitter_max: float = 1.2
    scrape_blocked_retry_multiplier: float = 2.0
    scrape_blocked_retry_min_seconds: int = 180
    scrape_platform_slot_limit_rumble: int = 0
    scrape_platform_slot_limit_bitchute: int = 0
    scrape_platform_slot_limit_substack: int = -1
    scrape_global_slot_limit: int = -1
    scrape_lock_ttl_seconds: int = 600
    scrape_platform_slot_ttl_seconds: int = 600
    scrape_circuit_breaker_fail_threshold: int = 5
    scrape_circuit_breaker_window_seconds: int = 1800
    scrape_circuit_breaker_cooldown_seconds: int = 1800
    gate0_daily_queue_limit: int = 200
    gate0_clean_recheck_days: int = 7
    scraper_human_delay_min_seconds: float = 2.0
    scraper_human_delay_max_seconds: float = 8.0
    scraper_content_wait_min_bytes: int = 5000
    scraper_content_wait_timeout_seconds: float = 20.0
    scraper_content_wait_poll_seconds: float = 1.5
    scraper_challenge_second_cycle_enabled: bool = True
    scraper_challenge_second_cycle_pre_reload_delay_seconds: float = 10.0
    scraper_challenge_second_cycle_post_reload_delay_seconds: float = 8.0
    scraper_challenge_second_cycle_wait_timeout_seconds: float = 25.0
    scraper_block_resource_images: bool = False
    scraper_block_resource_media: bool = True
    scraper_block_resource_fonts: bool = False
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


_RUNTIME_SETTINGS = RuntimeSettings()


def get_runtime_settings() -> RuntimeSettings:
    return _RUNTIME_SETTINGS
