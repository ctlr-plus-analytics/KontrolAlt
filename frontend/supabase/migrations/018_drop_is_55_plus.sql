-- 18. Remove deprecated 55+ audience signal from schema.
-- Older environments may still have a legacy channel_discovery view that selects this column.

DROP VIEW IF EXISTS channel_discovery;

ALTER TABLE channels
    DROP COLUMN IF EXISTS is_55_plus;
