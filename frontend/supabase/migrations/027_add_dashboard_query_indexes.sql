CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_avg_comments_eligible
  ON channels (avg_comments DESC)
  WHERE is_active = TRUE AND dashboard_eligible = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_avg_comments_ineligible
  ON channels (avg_comments DESC)
  WHERE is_active = TRUE AND dashboard_eligible = FALSE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_subscriber_count
  ON channels (dashboard_eligible, subscriber_count DESC)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_avg_views
  ON channels (dashboard_eligible, avg_views DESC)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_last_active_date
  ON channels (dashboard_eligible, last_active_date DESC)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_view_velocity_30d
  ON channels (dashboard_eligible, view_velocity_30d DESC)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_view_velocity_90d
  ON channels (dashboard_eligible, view_velocity_90d DESC)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_platform
  ON channels (platform, dashboard_eligible)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_comment_tier
  ON channels (comment_tier, dashboard_eligible)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_gate0_status
  ON channels (gate0_status, dashboard_eligible)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_channels_dashboard_niche_tags
  ON channels USING GIN (niche_tags);

CREATE INDEX IF NOT EXISTS idx_channels_search_name_trgm
  ON channels USING GIN (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_channels_search_url_trgm
  ON channels USING GIN (channel_url gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_channels_search_description_trgm
  ON channels USING GIN (description gin_trgm_ops);
