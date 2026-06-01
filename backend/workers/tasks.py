"""Celery task name constants for cross-service task dispatch.

The backend uses these constants with ``celery.send_task()`` to dispatch
tasks to the scraper worker without importing the worker directly.
"""

# Daily scraper workflow
TASK_RUN_DAILY_SCRAPE = "scraper.tasks.run_daily_scrape"
TASK_RUN_WEEKLY_VELOCITY_SCRAPE = "scraper.tasks.run_weekly_velocity_scrape"
TASK_SCRAPE_RUMBLE_CHANNEL = "scraper.tasks.scrape_rumble_channel"
TASK_SCRAPE_SUBSTACK_CHANNEL = "scraper.tasks.scrape_substack_channel"
TASK_SCRAPE_NEVER_SCRAPED_RUMBLE_SUBSTACK = (
    "scraper.tasks.scrape_never_scraped_rumble_substack"
)
TASK_DISCOVER_CHANNELS = "scraper.tasks.discover_channels"
TASK_DISCOVER_SEED_EXPANSION = "scraper.tasks.discover_seed_expansion"
TASK_DISCOVER_KEYWORD_EXPANSION = "scraper.tasks.discover_keyword_expansion"

# Gate 0
TASK_RUN_GATE0 = "scraper.tasks.run_gate0"
TASK_RUN_GATE0_ALL = "scraper.tasks.run_gate0_all"

# Lookalike
TASK_FIND_LOOKALIKES = "scraper.tasks.find_lookalikes"

# AI classification
TASK_CLASSIFY_CHANNELS = "scraper.tasks.classify_channels"
