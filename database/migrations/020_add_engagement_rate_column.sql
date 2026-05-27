-- Add a stored generated column for engagement rate (avg_views / subscriber_count).
-- This enables server-side sorting by engagement rate in the channel discovery table.
ALTER TABLE channels
  ADD COLUMN IF NOT EXISTS engagement_rate DOUBLE PRECISION
    GENERATED ALWAYS AS (
      CASE WHEN subscriber_count > 0
           THEN avg_views::double precision / subscriber_count
           ELSE NULL
      END
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_channels_engagement_rate ON channels (engagement_rate);
