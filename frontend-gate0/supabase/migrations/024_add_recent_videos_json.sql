-- Store structured recent video metadata for frontend rendering.
ALTER TABLE channels
    ADD COLUMN IF NOT EXISTS recent_videos jsonb NOT NULL DEFAULT '[]'::jsonb;

