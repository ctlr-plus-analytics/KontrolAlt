-- Add AI-generated channel summary column
ALTER TABLE channels
  ADD COLUMN IF NOT EXISTS ai_summary TEXT DEFAULT NULL;
