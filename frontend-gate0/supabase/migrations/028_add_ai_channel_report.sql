-- Add AI-generated channel intelligence report (7-question Q&A)
ALTER TABLE channels
  ADD COLUMN IF NOT EXISTS ai_channel_report JSONB DEFAULT NULL;
