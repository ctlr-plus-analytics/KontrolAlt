"""Proxy rotation logic."""

import logging
import random
from urllib.parse import urlsplit, urlunsplit

from core.config import scraper_settings

logger = logging.getLogger(__name__)


def _canonicalize_proxy_url(proxy: str) -> str:
    """Normalize proxy credentials into user:pass@host:port form.

    Supported inputs:
    - user:pass@host:port
    - host:port:user:pass
    - with or without scheme
    """
    proxy = proxy.strip()
    if not proxy:
        raise ValueError("empty proxy")

    if "://" in proxy:
        scheme, raw = proxy.split("://", 1)
    else:
        scheme, raw = "http", proxy

    if "@" in raw:
        auth, host_port = raw.rsplit("@", 1)
        if ":" not in auth or ":" not in host_port:
            raise ValueError(f"invalid proxy format: {proxy}")
        username, password = auth.split(":", 1)
        host, port = host_port.rsplit(":", 1)
    else:
        parts = raw.split(":")
        if len(parts) != 4:
            raise ValueError(f"invalid proxy format: {proxy}")
        host, port, username, password = parts

    if not port.isdigit():
        raise ValueError(f"invalid proxy port: {port}")
    return f"{scheme}://{username}:{password}@{host}:{port}"


def _supports_oxylabs_session_params(host: str) -> bool:
    """Return True for proxy hosts that accept username-appended session args."""
    normalized_host = host.lower()
    return "oxylabs" in normalized_host


def _supports_evomi_session_params(host: str) -> bool:
    """Return True for Evomi residential proxy hosts."""
    normalized_host = host.lower()
    return "evomi" in normalized_host


def _normalize_proxy(proxy: str) -> str:
    """Ensure a proxy string has an http:// scheme so urlsplit can parse it.

    Oxylabs and most residential proxy providers accept URLs in the format:
        http://user:pass@host:port
    Some providers, including Evomi, also document credentials as:
        host:port:user:pass
    If the scheme is missing, urlsplit cannot extract credentials and auth
    is silently dropped, causing the browser to exit via the datacenter IP.

    Args:
        proxy: Raw proxy string from PROXY_LIST env var.

    Returns:
        Proxy string guaranteed to have a scheme prefix.
    """
    try:
        return _canonicalize_proxy_url(proxy)
    except ValueError:
        # Keep backward compatibility for already-canonical inputs that include
        # uncommon auth chars we did not parse above.
        if "://" not in proxy:
            return f"http://{proxy.strip()}"
        return proxy.strip()


class ProxyRotator:
    """Manages a pool of proxy strings for rotation.

    Args:
        proxy_list_str: Comma-separated proxy URLs.
    """

    def __init__(self, proxy_list_str: str) -> None:
        raw = [p.strip() for p in proxy_list_str.split(",") if p.strip()]
        self.proxies: list[str] = []
        for proxy in raw:
            normalized = _normalize_proxy(proxy)
            try:
                parsed = urlsplit(normalized)
                _ = parsed.port
            except ValueError as exc:
                logger.warning("Skipping malformed proxy entry: %s", exc)
                continue
            self.proxies.append(normalized)
        logger.info("ProxyRotator: loaded %d proxy endpoint(s)", len(self.proxies))

    def get_random(self) -> str:
        """Return a random proxy string."""
        if not self.proxies:
            raise RuntimeError("PROXY_LIST must contain at least one proxy")
        return random.choice(self.proxies)

    def has_proxies(self) -> bool:
        """Return True if at least one proxy is available."""
        return len(self.proxies) > 0


# Module-level singleton instance
proxy_rotator = ProxyRotator(scraper_settings.proxy_list)


def get_random_proxy() -> str:
    """Return a random configured proxy string."""
    return proxy_rotator.get_random()


def build_session_proxy(
    *,
    base_proxy: str,
    session_id: str,
    session_minutes: int | None = None,
    active_since_minutes: int | None = None,
    platform_filter: str | None = None,
) -> str:
    """Return proxy URL with Oxylabs-compatible sticky session parameters.

    This keeps channel-flow requests on the same peer while allowing explicit
    session rollover on challenge/failure.
    """
    normalized_proxy = _normalize_proxy(base_proxy)
    parsed = urlsplit(normalized_proxy)
    username = parsed.username or ""
    password = parsed.password or ""
    host = parsed.hostname or ""
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        logger.warning("Malformed proxy URL after normalization, using base proxy: %s", exc)
        return normalized_proxy
    port = f":{parsed_port}" if parsed_port is not None else ""

    if not username:
        return normalized_proxy

    if _supports_evomi_session_params(host):
        # Evomi expects session/expert params on password suffix:
        # username:password_session-<id>_lifetime-<min>_activesince-<min>@host:port
        password_parts = [p for p in password.split("_") if p]
        filtered_password_parts: list[str] = []
        for part in password_parts:
            if part.startswith(
                ("session-", "hardsession-", "lifetime-", "activesince-")
            ):
                continue
            filtered_password_parts.append(part)
        filtered_password_parts.append(f"session-{session_id}")
        if session_minutes is not None:
            filtered_password_parts.append(f"lifetime-{session_minutes}")
        if active_since_minutes is not None and active_since_minutes > 0:
            filtered_password_parts.append(f"activesince-{active_since_minutes}")

        auth_password = "_".join(filtered_password_parts)
        auth = username
        if auth_password:
            auth = f"{auth}:{auth_password}"
        netloc = f"{auth}@{host}{port}"
        return urlunsplit(
            (parsed.scheme or "http", netloc, parsed.path, parsed.query, parsed.fragment)
        )

    if not _supports_oxylabs_session_params(host):
        return normalized_proxy

    parts = username.split("-")
    filtered_parts: list[str] = []
    skip_next = False
    for idx, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        if part in {"sessid", "sesstime", "os"}:
            skip_next = True
            continue
        filtered_parts.append(part)
    filtered_parts.extend(["sessid", session_id])
    if session_minutes is not None:
        filtered_parts.extend(["sesstime", str(session_minutes)])
    if platform_filter:
        filtered_parts.extend(["os", platform_filter.lower()])

    auth_user = "-".join(filtered_parts)
    auth = auth_user
    if password:
        auth = f"{auth}:{password}"
    netloc = f"{auth}@{host}{port}"
    return urlunsplit((parsed.scheme or "http", netloc, parsed.path, parsed.query, parsed.fragment))
