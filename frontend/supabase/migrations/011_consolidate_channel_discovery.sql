-- 11. Consolidate channel_discovery view and velocity_scores table into channels table

-- Step 1: Add consolidated fields to the channels table
ALTER TABLE channels
    -- Velocity scores
    ADD COLUMN IF NOT EXISTS view_velocity_30d numeric,
    ADD COLUMN IF NOT EXISTS view_velocity_90d numeric,
    ADD COLUMN IF NOT EXISTS comment_velocity_30d numeric,
    ADD COLUMN IF NOT EXISTS comment_velocity_90d numeric,
    ADD COLUMN IF NOT EXISTS velocity_computed_at timestamptz,
    -- Gate 0 cache fields
    ADD COLUMN IF NOT EXISTS gate0_result_id uuid,
    ADD COLUMN IF NOT EXISTS gate0_search_query text,
    ADD COLUMN IF NOT EXISTS gate0_result_status text,
    ADD COLUMN IF NOT EXISTS gate0_flagged_brand text,
    ADD COLUMN IF NOT EXISTS gate0_source_url text,
    -- Calculated eligibility indicators
    ADD COLUMN IF NOT EXISTS dashboard_metrics_complete boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS dashboard_url_valid boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS dashboard_eligible boolean NOT NULL DEFAULT false;

-- Step 2: Create indexes for optimized dashboard queries
CREATE INDEX IF NOT EXISTS idx_channels_dashboard_eligible ON channels(dashboard_eligible) WHERE dashboard_eligible = true;
CREATE INDEX IF NOT EXISTS idx_channels_view_velocity_30d ON channels(view_velocity_30d DESC NULLS LAST);

-- Step 3: Backfill velocity scores from the existing velocity_scores table
UPDATE channels c
SET
    view_velocity_30d = v.view_velocity_30d,
    view_velocity_90d = v.view_velocity_90d,
    comment_velocity_30d = v.comment_velocity_30d,
    comment_velocity_90d = v.comment_velocity_90d,
    velocity_computed_at = v.computed_at
FROM velocity_scores v
WHERE v.channel_id = c.id;

-- Step 4: Backfill latest Gate 0 check details from gate0_results
WITH latest_gate0 AS (
    SELECT DISTINCT ON (channel_id)
        id,
        channel_id,
        search_query,
        result_status,
        flagged_brand,
        source_url
    FROM gate0_results
    ORDER BY channel_id, checked_at DESC
)
UPDATE channels c
SET
    gate0_result_id = g.id,
    gate0_search_query = g.search_query,
    gate0_result_status = g.result_status,
    gate0_flagged_brand = g.flagged_brand,
    gate0_source_url = g.source_url
FROM latest_gate0 g
WHERE g.channel_id = c.id;

-- Step 5: Define trigger function for eligibility flags
CREATE OR REPLACE FUNCTION calculate_channel_eligibility_flags()
RETURNS TRIGGER AS $$
BEGIN
    -- 1. Check if core engagement metrics are complete
    NEW.dashboard_metrics_complete := (
        NEW.subscriber_count IS NOT NULL
        AND NEW.avg_views IS NOT NULL
        AND NEW.avg_comments IS NOT NULL
        AND NEW.last_active_date IS NOT NULL
    );

    -- 2. Validate URL formats using regular expressions
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
    );

    -- 3. Combine checks to calculate dashboard eligibility
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

-- Step 6: Create before insert or update trigger
DROP TRIGGER IF EXISTS trg_channels_eligibility ON channels;
CREATE TRIGGER trg_channels_eligibility
BEFORE INSERT OR UPDATE ON channels
FOR EACH ROW
EXECUTE FUNCTION calculate_channel_eligibility_flags();

-- Step 7: Update all existing channel records to calculate new boolean flags
UPDATE channels SET updated_at = NOW();

-- Step 8: Clean up by dropping the view and velocity table
DROP VIEW IF EXISTS channel_discovery;
DROP TABLE IF EXISTS velocity_scores;
