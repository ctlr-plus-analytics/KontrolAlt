-- Migration 016: Increase scraper worker throughput defaults.
-- Keeps dispatch batches aligned with the Docker worker concurrency default.

ALTER TABLE system_settings
    ALTER COLUMN scrape_dispatch_batch_size SET DEFAULT 8;

UPDATE system_settings
SET scrape_dispatch_batch_size = 8
WHERE singleton_key = 'global'
  AND scrape_dispatch_batch_size < 8;
