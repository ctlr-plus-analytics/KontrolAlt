"""Queue names for scraper Celery task dispatch."""

QUEUE_CLASSIFY = "classify"
QUEUE_DISCOVERY = "discovery"
QUEUE_GATE0 = "gate0"
QUEUE_RUMBLE = "rumble"
QUEUE_SUBSTACK = "substack"


def scrape_queue_for_platform(platform: str) -> str | None:
    """Return the scrape worker queue for a supported platform."""
    if platform == "rumble":
        return QUEUE_RUMBLE
    if platform == "substack":
        return QUEUE_SUBSTACK
    return None
