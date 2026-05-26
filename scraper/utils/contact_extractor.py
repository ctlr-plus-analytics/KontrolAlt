"""Regex extraction for emails, outbound URLs, and competitor URLs."""

import re
from urllib.parse import urlsplit

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
_SCHEME_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"{}|\\^`\[\]]+",
    re.IGNORECASE,
)
_BARE_DOMAIN_PATTERN = re.compile(
    r"(?<!@)\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s<>\"{}|\\^`\[\]]*)?",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = ".,;:!?)\"]}'"
_INTERNAL_DOMAINS = {"rumble.com", "bitchute.com"}
_LINKTREE_DOMAINS = {
    "linktree",
    "linktr.ee",
    "beacons",
    "beacons.ai",
    "bio.link",
    "campsite",
    "campsite.bio",
}
_COMPETITOR_DOMAINS = {
    "noblegold.com",
    "birchgold.com",
    "patriotgold.com",
    "kirkelliot.com",
}


def _normalize_url(raw_url: str) -> str:
    """Normalize a matched URL or bare domain for storage."""
    cleaned = raw_url.strip().strip(_TRAILING_PUNCTUATION)
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


def _hostname(url: str) -> str:
    """Return a lowercase hostname for a normalized URL."""
    return (urlsplit(url).hostname or "").lower()


def _is_internal_url(url: str) -> bool:
    """Return True for platform-internal URLs that should not be contacts."""
    hostname = _hostname(url)
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in _INTERNAL_DOMAINS
    )


def extract_emails(text: str) -> list[str]:
    """Extract deduplicated email addresses from text."""
    return sorted(set(_EMAIL_PATTERN.findall(text)))


def extract_urls(text: str) -> list[str]:
    """Extract deduplicated outbound URLs, including bare domains."""
    candidates = set(_SCHEME_URL_PATTERN.findall(text))
    candidates.update(_BARE_DOMAIN_PATTERN.findall(text))

    urls: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_url(candidate)
        try:
            parsed = urlsplit(normalized)
        except ValueError:
            continue
        # Drop anything that didn't produce a valid scheme+netloc (e.g. truncated
        # URLs split at an element boundary by BeautifulSoup's get_text()).
        if not parsed.scheme or not parsed.netloc:
            continue
        if not _is_internal_url(normalized):
            urls.add(normalized)

    return sorted(urls)


def extract_linktree_urls(urls: list[str]) -> list[str]:
    """Filter URLs for link-in-bio platforms called out by the product spec."""
    matched: list[str] = []
    for url in urls:
        url_lower = url.lower()
        if any(domain in url_lower for domain in _LINKTREE_DOMAINS):
            matched.append(url)
    return matched


def is_competitor_url(url: str) -> bool:
    """Return True when a URL contains a competitor domain."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _COMPETITOR_DOMAINS)
