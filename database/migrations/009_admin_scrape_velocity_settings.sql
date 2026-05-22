-- Add admin-configurable scrape and weekly velocity settings.

alter table system_settings
    add column if not exists scrape_only_new_or_missing_metrics boolean not null default true,
    add column if not exists scrape_rescrape_min_hours integer not null default 72,
    add column if not exists weekly_velocity_enabled boolean not null default true,
    add column if not exists weekly_velocity_utc_day text not null default 'sun',
    add column if not exists weekly_velocity_utc_time time not null default '03:00:00',
    add column if not exists velocity_weekly_min_avg_comments numeric not null default 20,
    add column if not exists velocity_weekly_min_avg_views numeric not null default 0,
    add column if not exists velocity_weekly_min_subscribers integer not null default 0,
    add column if not exists velocity_weekly_stale_hours integer not null default 144;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'system_settings_scrape_rescrape_min_hours_ck'
    ) then
        alter table system_settings
            add constraint system_settings_scrape_rescrape_min_hours_ck
            check (scrape_rescrape_min_hours >= 0);
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'system_settings_weekly_velocity_utc_day_ck'
    ) then
        alter table system_settings
            add constraint system_settings_weekly_velocity_utc_day_ck
            check (weekly_velocity_utc_day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'));
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'system_settings_velocity_weekly_thresholds_ck'
    ) then
        alter table system_settings
            add constraint system_settings_velocity_weekly_thresholds_ck
            check (
                velocity_weekly_min_avg_comments >= 0
                and velocity_weekly_min_avg_views >= 0
                and velocity_weekly_min_subscribers >= 0
                and velocity_weekly_stale_hours >= 0
            );
    end if;
end $$;
