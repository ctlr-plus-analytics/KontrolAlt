-- Migration 014: Adjust operational defaults for faster concurrent scraping
-- Sets the default scrape_dispatch_batch_size to 4 in system_settings table.
-- Also updates any existing settings row so it starts dispatching in batches of 4.

ALTER TABLE system_settings
    ALTER COLUMN scrape_dispatch_batch_size SET DEFAULT 4;

UPDATE system_settings
SET scrape_dispatch_batch_size = 4
WHERE singleton_key = 'global';
