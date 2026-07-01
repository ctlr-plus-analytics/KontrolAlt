BEGIN;

-- Step 1: Remove case-variant pairs that would conflict after lowercasing.
-- Keeps the row with the higher subscriber_count; deletes the duplicate.
WITH ranked AS (
  SELECT id,
         ROW_NUMBER() OVER (
           PARTITION BY LOWER(channel_url)
           ORDER BY COALESCE(subscriber_count, 0) DESC, created_at ASC
         ) AS rn
  FROM channels
  WHERE platform = 'rumble'
),
to_delete AS (SELECT id FROM ranked WHERE rn > 1)
DELETE FROM channels WHERE id IN (SELECT id FROM to_delete);

-- Step 2: Lowercase all Rumble channel URLs.
-- LOWER('https://rumble.com/c/DrJaneRuby') = 'https://rumble.com/c/drjaneruby'
-- Scheme and host are already lowercase so full LOWER() on the URL is safe.
UPDATE channels
SET channel_url = LOWER(channel_url)
WHERE platform = 'rumble';

COMMIT;
