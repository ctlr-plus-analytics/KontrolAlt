-- Migration 019: Accept canonical Substack URL variants used by scraper
-- and recompute dashboard eligibility flags.

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
            AND NEW.channel_url ~ '^https://substack\.com/@[A-Za-z0-9][A-Za-z0-9._-]{0,127}(/posts)?/?$'
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

-- Recompute derived flags for existing rows with the updated URL validity rule.
UPDATE channels
SET updated_at = NOW()
WHERE platform = 'substack';
