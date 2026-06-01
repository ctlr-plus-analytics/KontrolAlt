-- Track the last time a channel was successfully scraped directly on the
-- channels row, avoiding a channel_snapshots lookup in the daily scrape query.
ALTER TABLE channels
    ADD COLUMN IF NOT EXISTS last_scraped_at timestamptz;

-- Backfill from existing snapshot history.
UPDATE channels c
SET last_scraped_at = (
    SELECT MAX(scraped_at)
    FROM channel_snapshots cs
    WHERE cs.channel_id = c.id
)
WHERE last_scraped_at IS NULL;

-- Index to speed up the never-scraped filter in run_daily_scrape.
CREATE INDEX IF NOT EXISTS idx_channels_last_scraped_at
    ON channels (last_scraped_at)
    WHERE is_active = true;
