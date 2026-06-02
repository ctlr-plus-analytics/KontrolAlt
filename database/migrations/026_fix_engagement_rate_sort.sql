DROP INDEX IF EXISTS idx_channels_engagement_rate;

ALTER TABLE channels
  DROP COLUMN IF EXISTS engagement_rate;

ALTER TABLE channels
  ADD COLUMN engagement_rate DOUBLE PRECISION GENERATED ALWAYS AS (
    CASE
      WHEN subscriber_count > 0 AND avg_comments IS NOT NULL
        THEN (avg_comments::DOUBLE PRECISION / subscriber_count::DOUBLE PRECISION) * 100.0
      ELSE NULL::DOUBLE PRECISION
    END
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_channels_engagement_rate_eligible
  ON channels (engagement_rate DESC)
  WHERE is_active = TRUE AND dashboard_eligible = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_engagement_rate_ineligible
  ON channels (engagement_rate DESC)
  WHERE is_active = TRUE AND dashboard_eligible = FALSE;
