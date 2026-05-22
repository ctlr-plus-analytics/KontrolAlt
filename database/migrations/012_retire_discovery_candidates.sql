-- Migration 012: Retire discovery_candidates table and associated settings

-- Step 1: Drop the discovery_candidates table
DROP TABLE IF EXISTS discovery_candidates CASCADE;

-- Step 2: Drop check constraint system_settings_operational_non_negative_ck on system_settings
ALTER TABLE system_settings
    DROP CONSTRAINT IF EXISTS system_settings_operational_non_negative_ck;

-- Step 3: Drop the obsolete settings columns from system_settings
ALTER TABLE system_settings
    DROP COLUMN IF EXISTS discovery_promote_limit,
    DROP COLUMN IF EXISTS discovery_min_promote_confidence,
    DROP COLUMN IF EXISTS discovery_promoted_scrape_limit;

-- Step 4: Recreate the system_settings_operational_non_negative_ck check constraint without the deleted columns
ALTER TABLE system_settings
    ADD CONSTRAINT system_settings_operational_non_negative_ck
    CHECK (
        scrape_dispatch_batch_size >= 1
        AND scrape_dispatch_pause_seconds >= 0
        AND scrape_run_max_channels >= 0
        AND scrape_daily_byte_budget_mb >= 0
        AND scrape_retry_base_delay_seconds >= 1
        AND scrape_retry_jitter_min >= 0
        AND scrape_retry_jitter_max >= scrape_retry_jitter_min
        AND scrape_circuit_breaker_fail_threshold >= 1
        AND scrape_circuit_breaker_window_seconds >= 1
        AND scrape_circuit_breaker_cooldown_seconds >= 1
        AND gate0_daily_queue_limit >= 0
        AND gate0_clean_recheck_days >= 0
        AND scraper_human_delay_min_seconds >= 0
        AND scraper_human_delay_max_seconds >= scraper_human_delay_min_seconds
        AND scraper_content_wait_min_bytes >= 0
        AND scraper_content_wait_timeout_seconds >= 0
        AND scraper_content_wait_poll_seconds > 0
        AND discovery_serper_query_limit >= 0
        AND discovery_results_per_query >= 1
        AND discovery_max_pages_per_query >= 1
        AND discovery_insert_limit >= 0
        AND discovery_query_stagnation_limit >= 1
        AND discovery_global_stop_no_new >= 1
        AND discovery_max_feedback_terms >= 0
        AND discovery_new_scrape_limit >= 0
        AND discovery_channel_page_size >= 1
        AND discovery_verify_timeout_seconds >= 0
    );
