-- Enable Substack as a first-class platform across constraints and eligibility.
-- This migration is intentionally defensive because some environments may have
-- already retired discovery_candidates.

DO $$
BEGIN
    IF to_regclass('public.channels') IS NOT NULL THEN
        ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_platform_check;
        ALTER TABLE channels DROP CONSTRAINT IF EXISTS chk_channels_platform;
        ALTER TABLE channels
            ADD CONSTRAINT chk_channels_platform
            CHECK (platform IN ('rumble', 'bitchute', 'substack'));
    END IF;

    IF to_regclass('public.discovery_candidates') IS NOT NULL THEN
        ALTER TABLE discovery_candidates
            DROP CONSTRAINT IF EXISTS chk_discovery_candidates_platform;
        ALTER TABLE discovery_candidates
            ADD CONSTRAINT chk_discovery_candidates_platform
            CHECK (platform IN ('rumble', 'bitchute', 'substack'));
    END IF;

    IF to_regclass('public.system_settings') IS NOT NULL THEN
        ALTER TABLE system_settings
            ALTER COLUMN scrape_platform_priority
            SET DEFAULT ARRAY['rumble', 'bitchute', 'substack']::text[];

        ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS platform_priority_ck;
        ALTER TABLE system_settings
            ADD CONSTRAINT platform_priority_ck CHECK (
                array_length(scrape_platform_priority, 1) >= 1
                AND scrape_platform_priority <@ ARRAY['rumble', 'bitchute', 'substack']::text[]
            );

        UPDATE system_settings
        SET scrape_platform_priority = ARRAY['rumble', 'bitchute', 'substack']::text[]
        WHERE scrape_platform_priority IS NULL
           OR NOT ('substack' = ANY(scrape_platform_priority));
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION calculate_channel_eligibility_flags()
RETURNS TRIGGER AS $$
BEGIN
    NEW.dashboard_metrics_complete := (
        NEW.subscriber_count IS NOT NULL
        AND NEW.avg_views IS NOT NULL
        AND NEW.avg_comments IS NOT NULL
        AND NEW.last_active_date IS NOT NULL
    );

    NEW.dashboard_url_valid := (
        (
            NEW.platform = 'rumble'
            AND (
                NEW.channel_url ~ '^https://rumble\.com/(c|user)/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
                OR (
                    NEW.channel_url ~ '^https://rumble\.com/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
                    AND NEW.channel_url !~ '^https://rumble\.com/(about|account|blog|category|embed|login|premium|register|search|settings|static|user|videos|v[A-Za-z0-9_-]+)/?$'
                )
            )
        )
        OR (
            NEW.platform = 'bitchute'
            AND NEW.channel_url ~ '^https://bitchute\.com/channel/[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
        )
        OR (
            NEW.platform = 'substack'
            AND NEW.channel_url ~ '^https://substack\.com/@[A-Za-z0-9][A-Za-z0-9_-]{1,127}/?$'
        )
    );

    NEW.dashboard_eligible := (
        NEW.is_active = true
        AND NEW.has_been_scraped = true
        AND NEW.discovery_status = 'scraped'
        AND NEW.dashboard_metrics_complete = true
        AND NEW.dashboard_url_valid = true
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF to_regclass('public.channels') IS NOT NULL THEN
        UPDATE channels
        SET updated_at = NOW()
        WHERE platform IN ('rumble', 'bitchute', 'substack');
    END IF;
END
$$;
