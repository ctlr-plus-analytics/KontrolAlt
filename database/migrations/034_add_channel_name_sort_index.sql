CREATE INDEX IF NOT EXISTS idx_channels_dashboard_name
  ON channels (dashboard_eligible, name)
  WHERE is_active = TRUE;
