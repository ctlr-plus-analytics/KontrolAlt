-- Remove deprecated runtime settings table now that settings are file-based in scraper runtime_settings.py.

drop table if exists system_settings cascade;
