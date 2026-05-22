-- Migration 013: Backfill discovery_status to 'scraped' for historically scraped channels
-- This ensures that channels that were successfully scraped in the past meet
-- the dashboard eligibility requirements and show up on the frontend table.

UPDATE channels
SET discovery_status = 'scraped',
    updated_at = NOW()
WHERE has_been_scraped = true
  AND discovery_status = 'new';
