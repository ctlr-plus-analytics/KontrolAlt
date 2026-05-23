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
    r"\b(?:www\.|old\.)?(?:rumble\.com|bitchute\.com)/[^\s<>\]\"')]+",
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
BITCHUTE_HANDLE_PATTERN = re.compile(
    r"\bbitchute\s*(?:channel)?\s*[:/@-]+\s*@?([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\b",
    re.IGNORECASE,
)
BITCHUTE_PATH_MENTION_PATTERN = re.compile(
    r"\bbitchute\s+(?:com\s+)?(?:/)?channel\s*/?\s*([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\b",
    re.IGNORECASE,
)
RUMBLE_CONTEXT_HANDLE_PATTERN = re.compile(
    r"\brumble\b(?:\s+(?:channel|profile|page|handle))?\s+"
    r"(?:at|as|under|handle|profile|channel|page)\s+@?"
    r"([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\b",
    re.IGNORECASE,
)
BITCHUTE_CONTEXT_HANDLE_PATTERN = re.compile(
    r"\bbitchute\b(?:\s+(?:channel|profile|page|handle))?\s+"
    r"(?:at|as|under|handle|profile|channel|page)\s+@?"
    r"([a-zA-Z0-9][a-zA-Z0-9_-]{1,127})\b",
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
_BITCHUTE_SYSTEM_PATHS = {
    "all",
    "category",
    "embed",
    "hashtag",
    "login",
    "members",
    "playlist",
    "profile",
    "search",
    "video",
}
_SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,127}$")


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
        return "/" + "/".join((first, parts[1]))

    if first in _RUMBLE_SYSTEM_PATHS:
        return None

    if len(parts) >= 1 and _is_valid_rumble_root_slug(parts[0]):
        return f"/{parts[0]}"

    return None


def _canonicalize_bitchute(parts: list[str]) -> str | None:
    if not parts:
        return None

    first = parts[0].lower()
    if first in _BITCHUTE_SYSTEM_PATHS:
        return None
    if first != "channel" or len(parts) < 2 or not _is_valid_slug(parts[1]):
        return None
    return "/" + "/".join(("channel", parts[1]))


def canonicalize_channel_url(raw_url: str) -> ChannelUrlCandidate | None:
    """Return a canonical supported Rumble/BitChute channel URL, if present."""
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

    if host == "bitchute.com" or host.endswith(".bitchute.com"):
        path = _canonicalize_bitchute(parts)
        if path is None:
            return None
        return ChannelUrlCandidate(
            channel_url=urlunsplit(("https", "bitchute.com", path, "", "")),
            platform="bitchute",
        )

    return None


def extract_supported_channel_urls(text: str) -> list[ChannelUrlCandidate]:
    """Extract unique supported channel URLs from one text blob."""
    raw_urls = {_strip_trailing_punctuation(match.group(0)) for match in URL_PATTERN.finditer(text)}
    for match in BARE_SUPPORTED_URL_PATTERN.finditer(text):
        raw_urls.add(_normalize_scheme(match.group(0)))

    for match in RUMBLE_PATH_MENTION_PATTERN.finditer(text):
        raw_urls.add(f"https://rumble.com/{match.group(1).lower()}/{match.group(2)}")
    for match in RUMBLE_HANDLE_PATTERN.finditer(text):
        slug = match.group(1)
        if _is_valid_rumble_root_slug(slug):
            raw_urls.add(f"https://rumble.com/{slug}")
    for match in RUMBLE_CONTEXT_HANDLE_PATTERN.finditer(text):
        slug = match.group(1)
        if _is_valid_rumble_root_slug(slug):
            raw_urls.add(f"https://rumble.com/{slug}")
    for match in BITCHUTE_PATH_MENTION_PATTERN.finditer(text):
        raw_urls.add(f"https://bitchute.com/channel/{match.group(1)}")
    for match in BITCHUTE_HANDLE_PATTERN.finditer(text):
        slug = match.group(1)
        if slug.lower() not in _BITCHUTE_SYSTEM_PATHS:
            raw_urls.add(f"https://bitchute.com/channel/{slug}")
    for match in BITCHUTE_CONTEXT_HANDLE_PATTERN.finditer(text):
        slug = match.group(1)
        if slug.lower() not in _BITCHUTE_SYSTEM_PATHS:
            raw_urls.add(f"https://bitchute.com/channel/{slug}")

    candidates: dict[str, ChannelUrlCandidate] = {}
    for raw_url in raw_urls:
        candidate = canonicalize_channel_url(raw_url)
        if candidate is not None:
            candidates[candidate.channel_url] = candidate
    return list(candidates.values())
