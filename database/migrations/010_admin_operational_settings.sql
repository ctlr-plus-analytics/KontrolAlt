-- Add admin-configurable operational limits and scraper pacing settings.

alter table system_settings
    add column if not exists scrape_dispatch_batch_size integer not null default 1,
    add column if not exists scrape_dispatch_pause_seconds numeric not null default 2,
    add column if not exists scrape_run_max_channels integer not null default 0,
    add column if not exists scrape_daily_byte_budget_mb integer not null default 0,
    add column if not exists scrape_retry_base_delay_seconds integer not null default 60,
    add column if not exists scrape_retry_jitter_min numeric not null default 0.8,
    add column if not exists scrape_retry_jitter_max numeric not null default 1.2,
    add column if not exists scrape_circuit_breaker_fail_threshold integer not null default 5,
    add column if not exists scrape_circuit_breaker_window_seconds integer not null default 1800,
    add column if not exists scrape_circuit_breaker_cooldown_seconds integer not null default 1800,
    add column if not exists gate0_daily_queue_limit integer not null default 200,
    add column if not exists gate0_clean_recheck_days integer not null default 7,
    add column if not exists scraper_human_delay_min_seconds numeric not null default 2,
    add column if not exists scraper_human_delay_max_seconds numeric not null default 8,
    add column if not exists scraper_content_wait_min_bytes integer not null default 5000,
    add column if not exists scraper_content_wait_timeout_seconds numeric not null default 20,
    add column if not exists scraper_content_wait_poll_seconds numeric not null default 1.5,
    add column if not exists discovery_serper_query_limit integer not null default 480,
    add column if not exists discovery_results_per_query integer not null default 20,
    add column if not exists discovery_max_pages_per_query integer not null default 8,
    add column if not exists discovery_insert_limit integer not null default 20000,
    add column if not exists discovery_query_stagnation_limit integer not null default 4,
    add column if not exists discovery_global_stop_no_new integer not null default 120,
    add column if not exists discovery_max_feedback_terms integer not null default 36,
    add column if not exists discovery_new_scrape_limit integer not null default 500,
    add column if not exists discovery_channel_page_size integer not null default 1000,
    add column if not exists discovery_verify_timeout_seconds numeric not null default 15,
    add column if not exists discovery_promote_limit integer not null default 1500,
    add column if not exists discovery_min_promote_confidence numeric not null default 0.62,
    add column if not exists discovery_promoted_scrape_limit integer not null default 500;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'system_settings_operational_non_negative_ck'
    ) then
        alter table system_settings
            add constraint system_settings_operational_non_negative_ck
            check (
                scrape_dispatch_batch_size >= 1
                and scrape_dispatch_pause_seconds >= 0
                and scrape_run_max_channels >= 0
                and scrape_daily_byte_budget_mb >= 0
                and scrape_retry_base_delay_seconds >= 1
                and scrape_retry_jitter_min >= 0
                and scrape_retry_jitter_max >= scrape_retry_jitter_min
                and scrape_circuit_breaker_fail_threshold >= 1
                and scrape_circuit_breaker_window_seconds >= 1
                and scrape_circuit_breaker_cooldown_seconds >= 1
                and gate0_daily_queue_limit >= 0
                and gate0_clean_recheck_days >= 0
                and scraper_human_delay_min_seconds >= 0
                and scraper_human_delay_max_seconds >= scraper_human_delay_min_seconds
                and scraper_content_wait_min_bytes >= 0
                and scraper_content_wait_timeout_seconds >= 0
                and scraper_content_wait_poll_seconds > 0
                and discovery_serper_query_limit >= 0
                and discovery_results_per_query >= 1
                and discovery_max_pages_per_query >= 1
                and discovery_insert_limit >= 0
                and discovery_query_stagnation_limit >= 1
                and discovery_global_stop_no_new >= 1
                and discovery_max_feedback_terms >= 0
                and discovery_new_scrape_limit >= 0
                and discovery_channel_page_size >= 1
                and discovery_verify_timeout_seconds >= 0
                and discovery_promote_limit >= 0
                and discovery_min_promote_confidence >= 0
                and discovery_min_promote_confidence <= 1
                and discovery_promoted_scrape_limit >= 0
            );
    end if;
end $$;
