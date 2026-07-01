BEGIN;

-- Hard backstop: prevent duplicate channel_url inserts at the DB level.
-- Run AFTER the manual dedup SQL (Steps 1-4 from chat) has already cleaned
-- existing /c/ vs /user/ pairs so no duplicates remain.
ALTER TABLE channels
  ADD CONSTRAINT channels_channel_url_unique UNIQUE (channel_url);

COMMIT;
