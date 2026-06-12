-- Replace JSONB ai_channel_report with plain TEXT narrative column.
-- Existing JSONB reports are dropped; they will be regenerated as narrative prose.
ALTER TABLE channels DROP COLUMN IF EXISTS ai_channel_report;
ALTER TABLE channels ADD COLUMN ai_channel_report TEXT DEFAULT NULL;
