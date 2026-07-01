"""Supported platform channel URL extraction and canonicalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class ChannelUrlCandidate:
    """A canonical supported channel URL found in unstructured text."""

    channel_url: str
    platform: str


URL_PATTERN = re.compile(r"https?://[^\s<>\]\"')]+", re.IGNORECASE)
BARE_SUPPORTED_URL_PATTERN = re.compile(
    r"\b(?:www\.)?(?:rumble\.com|substack\.com)/[^\s<>\]\"')]+",
    re.IGNORECASE,
)
SUBSTACK_SUBDOMAIN_PATTERN = re.compile(
    r"\b([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\.substack\.com\b",
    re.IGNORECASE,
)
RUMBLE_HANDLE_PATTERN = re.compile(
    r"\brumble\s*[:/@-]+\s*@?([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\b",
    re.IGNORECASE,
)
RUMBLE_PATH_MENTION_PATTERN = re.compile(
    r"\brumble\s+(?:com\s+)?(?:/)?(c|user)\b\s*/?\s*([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\b",
    re.IGNORECASE,
)
RUMBLE_CONTEXT_HANDLE_PATTERN = re.compile(
    r"\brumble\b(?:\s+(?:channel|profile|page|handle))?\s+"
    r"(?:at|as|under|handle|profile|channel|page)\s+@?"
    r"([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\b",
    re.IGNORECASE,
)
SUBSTACK_HANDLE_PATTERN = re.compile(
    r"\bsubstack\s*[:/@-]+\s*@?([a-zA-Z0-9][a-zA-Z0-9._-]{1,127})\b",
    re.IGNORECASE,
)
SUBSTACK_PATH_MENTION_PATTERN = re.compile(
    r"\bsubstack\s+(?:com\s+)?(?:/)?@([a-zA-Z0-9][a-zA-Z0-9._-]{1,127})\b",
    re.IGNORECASE,
)

_RUMBLE_SYSTEM_PATHS = {
    "about",
    "account",
    "blog",
    "category",
    "embed",
    "login",
    "premium",
    "register",
    "search",
    "settings",
    "static",
    "user",
    "videos",
}
_RUMBLE_RESERVED_ROOT_SLUGS = _RUMBLE_SYSTEM_PATHS | {
    "and",
    "api",
    "app",
    "channel",
    "channels",
    "contact",
    "download",
    "downloads",
    "for",
    "from",
    "help",
    "home",
    "jobs",
    "live",
    "news",
    "of",
    "on",
    "privacy",
    "support",
    "that",
    "the",
    "to",
    "tv",
    "watch",
    "with",
}
_SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,127}$")
_SUBSTACK_HANDLE_SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,127}$")


def _strip_trailing_punctuation(raw_url: str) -> str:
    return raw_url.strip().rstrip(".,;:!?")


def _normalize_scheme(raw_url: str) -> str:
    normalized = _strip_trailing_punctuation(raw_url)
    if normalized and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        normalized = f"https://{normalized}"
    return normalized


def _clean_parts(path: str) -> list[str]:
    cleaned_path = re.sub(r"/{2,}", "/", path or "/").strip("/")
    return [part for part in cleaned_path.split("/") if part]


def _is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_PATTERN.match(slug))


def _is_valid_rumble_root_slug(slug: str) -> bool:
    return _is_valid_slug(slug) and slug.lower() not in _RUMBLE_RESERVED_ROOT_SLUGS


def _canonicalize_rumble(parts: list[str]) -> str | None:
    if not parts:
        return None

    first = parts[0].lower()
    if first.startswith("v") and len(first) > 1:
        return None

    if first in {"c", "user"}:
        if len(parts) < 2 or not _is_valid_slug(parts[1]):
            return None
        return f"/{first}/{parts[1].lower()}"

    if first in _RUMBLE_SYSTEM_PATHS:
        return None

    return None


def _canonicalize_substack(parts: list[str]) -> str | None:
    if not parts:
        return None
    first = parts[0]
    if not first.startswith("@"):
        return None
    handle = first[1:]
    if not _SUBSTACK_HANDLE_SLUG_PATTERN.match(handle):
        return None
    return f"/@{handle}"


def canonicalize_channel_url(raw_url: str) -> ChannelUrlCandidate | None:
    """Return a canonical supported Rumble/Substack channel URL, if present."""
    normalized = _normalize_scheme(raw_url)
    if not normalized:
        return None

    try:
        split = urlsplit(normalized)
    except ValueError:
        return None

    host = (split.hostname or "").lower()
    parts = _clean_parts(split.path)

    if host in {"rumble.com", "www.rumble.com"}:
        path = _canonicalize_rumble(parts)
        if path is None:
            return None
        return ChannelUrlCandidate(
            channel_url=urlunsplit(("https", "rumble.com", path, "", "")),
            platform="rumble",
        )

    if host in {"substack.com", "www.substack.com"}:
        path = _canonicalize_substack(parts)
        if path is None:
            return None
        return ChannelUrlCandidate(
            channel_url=urlunsplit(("https", "substack.com", path, "", "")),
            platform="substack",
        )
    if host.endswith(".substack.com"):
        subdomain = host[: -len(".substack.com")]
        if not _SUBSTACK_HANDLE_SLUG_PATTERN.match(subdomain):
            return None
        return ChannelUrlCandidate(
            channel_url=urlunsplit(("https", "substack.com", f"/@{subdomain}", "", "")),
            platform="substack",
        )

    return None


def extract_supported_channel_urls(text: str) -> list[ChannelUrlCandidate]:
    """Extract unique supported channel URLs from one text blob."""
    raw_urls = {_strip_trailing_punctuation(match.group(0)) for match in URL_PATTERN.finditer(text)}
    for match in BARE_SUPPORTED_URL_PATTERN.finditer(text):
        raw_urls.add(_normalize_scheme(match.group(0)))
    for match in SUBSTACK_SUBDOMAIN_PATTERN.finditer(text):
        raw_urls.add(f"https://{match.group(1)}.substack.com")

    for match in RUMBLE_PATH_MENTION_PATTERN.finditer(text):
        raw_urls.add(f"https://rumble.com/{match.group(1).lower()}/{match.group(2)}")
    for match in SUBSTACK_PATH_MENTION_PATTERN.finditer(text):
        raw_urls.add(f"https://substack.com/@{match.group(1)}")
    for match in SUBSTACK_HANDLE_PATTERN.finditer(text):
        slug = match.group(1)
        if _SUBSTACK_HANDLE_SLUG_PATTERN.match(slug):
            raw_urls.add(f"https://substack.com/@{slug}")

    candidates: dict[str, ChannelUrlCandidate] = {}
    for raw_url in raw_urls:
        candidate = canonicalize_channel_url(raw_url)
        if candidate is not None:
            candidates[candidate.channel_url] = candidate
    return list(candidates.values())
