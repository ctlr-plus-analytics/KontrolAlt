"""Celery task: run Gate 0 compliance check for a channel."""

import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from celery import Task
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client
from core.runtime_settings import Gate0CompetitorSetting, get_runtime_settings
from models import Gate0TaskResult
from tasks.task_queues import QUEUE_GATE0

logger = logging.getLogger(__name__)

_SERPER_SEARCH_URL = "https://google.serper.dev/search"
_SERPER_QUOTA_STATUS_CODES = {402, 429}
_URLISH_PATTERN = re.compile(
    r"https?://[^\s<>\"{}|\\^`\[\]]+|(?<!@)\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>\"{}|\\^`\[\]]*)?",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = ".,;:!?)\"]}'"

# Affiliate URL indicator: query/path segments that denote referral tracking.
_AFFILIATE_PATTERN = re.compile(
    r"[?&/](?:ref|aff|affiliate|aid|partner|source|utm_source|utm_campaign)[=/]",
    re.IGNORECASE,
)

# Link-shortener / link-aggregator hosts whose URLs should be redirect-followed.
_LINK_SHORTENER_HOSTS = frozenset({
    "bit.ly", "t.co", "tinyurl.com", "ow.ly", "buff.ly",
    "linktr.ee", "beacons.ai", "linkin.bio", "allmylinks.com",
    "lnk.to", "smarturl.it",
})

# Words that raise confidence when found near a competitor mention.
_PROMO_WORDS = frozenset({
    "sponsor", "sponsored", "partner", "affiliate", "promo",
    "code", "free", "offer", "exclusive", "discount", "kit",
    "click", "refer", "referral", "get started", "link",
})

# Words that lower confidence when found near a competitor mention.
_NEGATIVE_WORDS = frozenset({
    "scam", "fraud", "avoid", "warning", "lawsuit", "sec",
    "complaint", "versus", "vs", "compared", "switched", "left",
    "problems", "beware", "fake", "exposed", "review", "reviews",
})

# Context window (characters each side of a match) for promo/negative detection.
_CONTEXT_WINDOW = 120

# --- Signal weights ---

# High confidence — auto-dirty zone (≥ 0.95)
_W_DOMAIN_IN_CONTACT = 0.97   # competitor domain in contact_info or secondary_urls
_W_REDIRECT_TO_DOMAIN = 0.96  # link-shortener URL that resolves to a competitor domain
_W_AFFILIATE_URL = 0.95       # URL with affiliate pattern pointing to a competitor

# Medium confidence — needs-review zone (0.80–0.94)
_W_DOMAIN_DESCRIPTION_PROMO = 0.90   # domain in description + promo language nearby
_W_DOMAIN_IN_DESCRIPTION = 0.60      # domain in description, neutral context (no promo language)
_W_BRAND_DESCRIPTION_PROMO = 0.82    # brand in description + promo language
_W_MULTI_TITLE_PROMO = 0.88          # 3+ video titles: brand + promo language
_W_TWO_TITLE_PROMO = 0.75            # 2 video titles: brand + promo language
_W_ONE_TITLE_PROMO = 0.70            # 1 video title: brand + promo language

# Low confidence — below threshold (< 0.80)
_W_BRAND_IN_DESCRIPTION = 0.50       # brand only in description, neutral context
_W_MULTI_TITLE_NEUTRAL = 0.60        # 3+ video titles mentioning brand, neutral
_W_ONE_TITLE_NEUTRAL = 0.35          # 1–2 video titles mentioning brand, neutral

# Serper weights — kept for compound-math reference in tests
_W_SERPER_SINGLE = 0.45

# Serper match-quality weights returned by _scan_serper_results
_W_SERPER_DOMAIN_LINK = 0.80  # channel appears on competitor's own website (site: hit)
_W_SERPER_DOMAIN_TEXT = 0.55  # competitor domain cited in a third-party article
_W_SERPER_BRAND_PROMO = 0.50  # brand + promo language, no domain (weakest qualifying hit)

# Decision thresholds
_THRESHOLD_DIRTY = 0.95
_THRESHOLD_REVIEW = 0.80


@dataclass
class EvidenceSignal:
    """A single confidence signal contributing to a Gate 0 determination."""

    signal_type: str
    matched_value: str
    weight: float
    source_url: str | None = None
    context: str | None = None


@dataclass
class ScanResult:
    """Aggregated Gate 0 scan outcome with compound confidence and evidence trail."""

    flagged_brand: str | None = None
    source_url: str | None = None
    confidence: float = 0.0
    signals: list[EvidenceSignal] = dc_field(default_factory=list)


# ---------------------------------------------------------------------------
# Confidence math
# ---------------------------------------------------------------------------

def _compound_confidence(weights: list[float]) -> float:
    """Combine independent signal weights: 1 − Π(1 − wᵢ)."""
    if not weights:
        return 0.0
    complement = 1.0
    for w in weights:
        complement *= 1.0 - max(0.0, min(1.0, w))
    return 1.0 - complement


def _classify_confidence(confidence: float) -> str:
    if confidence >= _THRESHOLD_DIRTY:
        return "dirty"
    if confidence >= _THRESHOLD_REVIEW:
        return "needs_review"
    return "clean"


# ---------------------------------------------------------------------------
# Context detection
# ---------------------------------------------------------------------------

def _context_window(text: str, term: str) -> str:
    """Return the substring of text surrounding the first occurrence of term."""
    idx = text.lower().find(term.lower())
    if idx == -1:
        return ""
    start = max(0, idx - _CONTEXT_WINDOW)
    end = min(len(text), idx + len(term) + _CONTEXT_WINDOW)
    return text[start:end]


def _has_promo_context(text: str, term: str) -> bool:
    window = _context_window(text, term).lower()
    return any(word in window for word in _PROMO_WORDS)


def _has_negative_context(text: str, term: str) -> bool:
    window = _context_window(text, term).lower()
    return any(word in window for word in _NEGATIVE_WORDS)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _has_affiliate_pattern(url: str) -> bool:
    return bool(_AFFILIATE_PATTERN.search(url))


def _should_follow_redirect(url: str) -> bool:
    """True if url is from a known link shortener worth resolving."""
    try:
        host = urlparse(url).hostname or ""
        return host in _LINK_SHORTENER_HOSTS or any(
            host.endswith(f".{s}") for s in _LINK_SHORTENER_HOSTS
        )
    except Exception:
        return False


def _follow_url_redirect(url: str) -> str | None:
    """Follow HTTP redirects and return the final URL, or None on failure."""
    try:
        with httpx.Client(timeout=5.0, follow_redirects=True, max_redirects=5) as http:
            resp = http.head(url, headers={"User-Agent": "Mozilla/5.0"})
            return str(resp.url)
    except Exception:
        return None


def _normalize_evidence_url(raw_url: str) -> str:
    cleaned = raw_url.strip().strip(_TRAILING_PUNCTUATION)
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


def _source_url_for_domain(text: str, fallback_url: str | None, domain: str) -> str:
    """Return the most specific URL in text that contains the competitor domain."""
    if fallback_url and _contains_domain(fallback_url.lower(), domain):
        return fallback_url
    for candidate in _URLISH_PATTERN.findall(text):
        normalized = _normalize_evidence_url(candidate)
        if _contains_domain(normalized.lower(), domain):
            return normalized
    return f"https://{domain}"


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------

def _contains_domain(text_lower: str, domain: str) -> bool:
    """Match a hostname/subdomain without matching unrelated longer strings."""
    pattern = rf"(?<![a-z0-9-]){re.escape(domain.lower())}(?![a-z0-9-])"
    return re.search(pattern, text_lower) is not None


def _contains_brand(text_lower: str, brand: str) -> bool:
    """Match brand phrases on word boundaries."""
    pattern = rf"(?<![a-z0-9]){re.escape(brand.lower())}(?![a-z0-9])"
    return re.search(pattern, text_lower) is not None


# ---------------------------------------------------------------------------
# Field-level scanners (return EvidenceSignal lists)
# ---------------------------------------------------------------------------

def _scan_url_for_competitor(
    url: str,
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> list[EvidenceSignal]:
    """Scan a single URL from contact_info or secondary_urls for competitor signals."""
    url_lower = url.lower()

    for competitor in competitors:
        for domain in competitor.domains:
            if _contains_domain(url_lower, domain):
                weight = _W_AFFILIATE_URL if _has_affiliate_pattern(url) else _W_DOMAIN_IN_CONTACT
                return [EvidenceSignal("domain_in_contact", domain, weight, url)]

        if _contains_brand(url_lower, competitor.brand):
            return [EvidenceSignal("brand_in_contact", competitor.brand, 0.70, url)]

    # No immediate match — follow redirect if it's a known link shortener.
    if _should_follow_redirect(url):
        resolved = _follow_url_redirect(url)
        if resolved:
            resolved_lower = resolved.lower()
            for competitor in competitors:
                for domain in competitor.domains:
                    if _contains_domain(resolved_lower, domain):
                        return [EvidenceSignal("redirect_to_domain", domain, _W_REDIRECT_TO_DOMAIN, resolved)]

    return []


def _scan_text_field(
    text: str,
    field_type: str,
    fallback_url: str,
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> list[EvidenceSignal]:
    """Scan a text blob (description, name) for competitor signals."""
    signals: list[EvidenceSignal] = []
    text_lower = text.lower()

    for competitor in competitors:
        domain_matched = False
        for domain in competitor.domains:
            if _contains_domain(text_lower, domain):
                domain_matched = True
                if _has_negative_context(text, domain):
                    break  # suppress; also skip brand check for this competitor
                has_promo = _has_promo_context(text, domain)
                weight = _W_DOMAIN_DESCRIPTION_PROMO if has_promo else _W_DOMAIN_IN_DESCRIPTION
                source = _source_url_for_domain(text, fallback_url, domain)
                ctx = _context_window(text, domain)
                signals.append(EvidenceSignal(f"domain_in_{field_type}", domain, weight, source, ctx))
                break

        if not domain_matched and _contains_brand(text_lower, competitor.brand):
            if not _has_negative_context(text, competitor.brand):
                has_promo = _has_promo_context(text, competitor.brand)
                weight = _W_BRAND_DESCRIPTION_PROMO if has_promo else _W_BRAND_IN_DESCRIPTION
                ctx = _context_window(text, competitor.brand)
                source_label = {
                    "description": "Channel description",
                    "name": "Channel name",
                }.get(field_type, f"Channel {field_type}")
                signals.append(EvidenceSignal(
                    f"brand_in_{field_type}", competitor.brand, weight, source_label, ctx,
                ))

    return signals


def _scan_video_titles(
    titles: list[str],
    competitors: tuple[Gate0CompetitorSetting, ...],
    fallback_url: str,
) -> list[EvidenceSignal]:
    """Score video title mentions per competitor, weighted by count and promo context."""
    signals: list[EvidenceSignal] = []

    for competitor in competitors:
        promo_hits: list[str] = []
        neutral_hits: list[str] = []

        for title in titles:
            title_lower = title.lower()
            matched_domain = False
            for domain in competitor.domains:
                if _contains_domain(title_lower, domain):
                    matched_domain = True
                    if not _has_negative_context(title, domain):
                        target = promo_hits if _has_promo_context(title, domain) else neutral_hits
                        target.append(title)
                    break
            if not matched_domain and _contains_brand(title_lower, competitor.brand):
                if not _has_negative_context(title, competitor.brand):
                    target = promo_hits if _has_promo_context(title, competitor.brand) else neutral_hits
                    target.append(title)

        if promo_hits:
            n = len(promo_hits)
            weight = _W_MULTI_TITLE_PROMO if n >= 3 else (_W_TWO_TITLE_PROMO if n == 2 else _W_ONE_TITLE_PROMO)
            signals.append(EvidenceSignal(
                "title_promo", competitor.brand, weight, "Channel video titles", "; ".join(promo_hits[:3]),
            ))

        if neutral_hits:
            n = len(neutral_hits)
            weight = _W_MULTI_TITLE_NEUTRAL if n >= 3 else _W_ONE_TITLE_NEUTRAL
            signals.append(EvidenceSignal(
                "title_neutral", competitor.brand, weight, "Channel video titles", "; ".join(neutral_hits[:3]),
            ))

    return signals


# ---------------------------------------------------------------------------
# Channel-level local scan
# ---------------------------------------------------------------------------

def _scan_channel_local(
    channel: dict[str, object],
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> ScanResult:
    """Scan all stored channel fields and return a ScanResult with accumulated signals."""
    channel_url = str(channel.get("channel_url") or "")

    contact_info = channel.get("contact_info") or []
    secondary_urls = channel.get("secondary_urls") or []
    if isinstance(contact_info, str):
        contact_info = [contact_info]
    if isinstance(secondary_urls, str):
        secondary_urls = [secondary_urls]

    video_titles = channel.get("video_titles") or []
    if isinstance(video_titles, str):
        video_titles = [video_titles]
    video_titles = [str(t) for t in video_titles if t]

    description = str(channel.get("description") or "")
    name = str(channel.get("name") or "")

    all_signals: list[EvidenceSignal] = []

    for url in list(contact_info) + list(secondary_urls):
        all_signals.extend(_scan_url_for_competitor(str(url), competitors))

    if description:
        all_signals.extend(_scan_text_field(description, "description", channel_url, competitors))

    if name:
        all_signals.extend(_scan_text_field(name, "name", channel_url, competitors))

    if video_titles:
        all_signals.extend(_scan_video_titles(video_titles, competitors, channel_url))

    if not all_signals:
        return ScanResult()

    confidence = _compound_confidence([s.weight for s in all_signals])
    best = max(all_signals, key=lambda s: s.weight)
    return ScanResult(best.matched_value, best.source_url, confidence, all_signals)


# ---------------------------------------------------------------------------
# Serper search
# ---------------------------------------------------------------------------

def _scan_serper_results(
    organic_results: object,
    competitors: tuple[Gate0CompetitorSetting, ...],
    channel_identifiers: frozenset[str] = frozenset(),
    is_site_query: bool = False,
) -> tuple[str | None, str | None, float]:
    """Scan top Serper organic results for competitor signals.

    Returns (matched_value, source_url, weight) for the first qualifying hit,
    or (None, None, 0.0). Three signal tiers by quality:
      - Domain in result link (channel on competitor's own site): _W_SERPER_DOMAIN_LINK
        (only counted for site: queries — competitor homepage appears for any brand search)
      - Domain in article title/snippet (third-party coverage): _W_SERPER_DOMAIN_TEXT
      - Brand + promo language, no domain: _W_SERPER_BRAND_PROMO

    Fix A — channel name gate: results that don't reference the channel being checked
    are skipped entirely. Augusta's homepage appears for any 'Augusta' brand search but
    its title/snippet won't mention the specific channel.
    Fix B — site: query guard: domain-in-link is only meaningful when we explicitly
    asked Google to find the channel on the competitor's site.
    Fix C — negative context: domain-in-link is suppressed by negative language.
    """
    if not isinstance(organic_results, list):
        return None, None, 0.0

    for item in organic_results[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        link = str(item.get("link") or "")
        link_lower = link.lower()
        text = f"{title} {snippet}"
        text_lower = text.lower()

        # Fix A: skip results that don't reference the channel being checked.
        # A result is only evidence if it co-mentions the channel and a competitor.
        if channel_identifiers and not any(ident in text_lower for ident in channel_identifiers):
            continue

        for competitor in competitors:
            # Fix B: domain-in-link only for site: queries.
            # For brand-name queries the competitor's own homepage appears in results
            # as a natural SEO artefact — it is not evidence of channel affiliation.
            if is_site_query:
                for domain in competitor.domains:
                    if _contains_domain(link_lower, domain):
                        # Fix C: suppress if result title/snippet carries negative language.
                        # The domain itself may only appear in the link URL, not the text,
                        # so we also check the brand name as a proxy.
                        neg = (
                            _has_negative_context(text, domain)
                            or _has_negative_context(text, competitor.brand)
                        )
                        if not neg:
                            return domain, link, _W_SERPER_DOMAIN_LINK

            # Domain cited inside article text (title or snippet).
            for domain in competitor.domains:
                if _contains_domain(text_lower, domain):
                    if not _has_negative_context(text, domain):
                        source = _source_url_for_domain(text, link, domain)
                        return domain, source, _W_SERPER_DOMAIN_TEXT

            # Brand + explicit promo language; bare co-mentions suppressed.
            if _contains_brand(text_lower, competitor.brand):
                if (
                    _has_promo_context(text, competitor.brand)
                    and not _has_negative_context(text, competitor.brand)
                ):
                    return competitor.brand, link or None, _W_SERPER_BRAND_PROMO

    return None, None, 0.0


def _run_serper_search(
    search_query: str,
    competitors: tuple[Gate0CompetitorSetting, ...],
    channel_identifiers: frozenset[str] = frozenset(),
    is_site_query: bool = False,
) -> tuple[str | None, str | None, float]:
    """Run a single Serper query and return any competitor hit with its quality weight."""
    with httpx.Client(timeout=15.0) as http:
        response = http.post(
            _SERPER_SEARCH_URL,
            headers={
                "X-API-KEY": scraper_settings.serp_api_key,
                "Content-Type": "application/json",
            },
            json={"q": search_query, "num": 3},
        )
        if response.status_code in _SERPER_QUOTA_STATUS_CODES:
            raise RuntimeError("Serper quota exceeded for today")
        response.raise_for_status()
        data = response.json()
        organic = data.get("organic", []) if isinstance(data, dict) else []
        return _scan_serper_results(organic, competitors, channel_identifiers, is_site_query)


def _build_search_queries(
    channel_name: str,
    channel_handle: str | None,
    competitors: tuple[Gate0CompetitorSetting, ...],
) -> list[str]:
    """Return ordered Serper queries for Gate 0, most affiliation-targeted first.

    Query order (early exit on hit):
      1. Per-competitor affiliation queries (sponsor/affiliate/partner language)
      2. Site-specific queries (channel appears on competitor domain)
      3. Broad per-competitor name queries
    """
    handle_differs = bool(
        channel_handle and channel_handle.lower() != channel_name.lower()
    )
    queries: list[str] = []

    # 1. Affiliation-targeted (highest signal-to-noise)
    for competitor in competitors:
        queries.append(
            f'"{channel_name}" "{competitor.brand}" "sponsor" OR "affiliate" OR "partner"'
        )
        if handle_differs:
            queries.append(
                f'"{channel_handle}" "{competitor.brand}" "sponsor" OR "affiliate" OR "partner"'
            )

    # 2. Site-targeted
    for competitor in competitors:
        for domain in competitor.domains[:1]:
            queries.append(f'site:{domain} "{channel_name}"')
            if handle_differs:
                queries.append(f'site:{domain} "{channel_handle}"')

    # 3. Broad per-competitor
    for competitor in competitors:
        queries.append(f'"{channel_name}" "{competitor.brand}"')
        if handle_differs:
            queries.append(f'"{channel_handle}" "{competitor.brand}"')

    # 4. Gold IRA catch-all (last resort — no competitor name, least specific)
    queries.append(f'"{channel_name}" "gold IRA"')
    if handle_differs:
        queries.append(f'"{channel_handle}" "gold IRA"')

    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def _run_serper_search_multi(
    queries: list[str],
    competitors: tuple[Gate0CompetitorSetting, ...],
    channel_identifiers: frozenset[str] = frozenset(),
) -> tuple[str | None, str | None, str, float]:
    """Run Serper queries in order, compounding confidence across independent hits.

    Each unique source URL is counted once — the same article appearing across multiple
    queries is skipped so it cannot inflate the compound confidence score.
    Returns (flagged_brand, source_url, winning_query, serper_confidence).
    Stops early once combined confidence reaches _THRESHOLD_DIRTY.
    """
    first_query = queries[0] if queries else ""
    hit_weights: list[float] = []
    winning_brand: str | None = None
    winning_url: str | None = None
    winning_query = first_query
    seen_urls: set[str] = set()

    for query in queries:
        is_site_query = query.startswith("site:")
        brand, url, weight = _run_serper_search(
            query, competitors,
            channel_identifiers=channel_identifiers,
            is_site_query=is_site_query,
        )
        if brand is not None:
            url_key = (url or "").rstrip("/").lower()
            if url_key and url_key in seen_urls:
                continue  # same source already counted, not independent evidence
            if url_key:
                seen_urls.add(url_key)
            if winning_brand is None:
                winning_brand = brand
                winning_url = url
                winning_query = query
            hit_weights.append(weight)
            if _compound_confidence(hit_weights) >= _THRESHOLD_DIRTY:
                break

    if not hit_weights:
        return None, None, first_query, 0.0

    return winning_brand, winning_url, winning_query, _compound_confidence(hit_weights)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _persist_gate0_result(
    channel: dict[str, object],
    search_query: str,
    result: ScanResult,
) -> dict[str, object]:
    """Insert a Gate 0 result and update the channel's cached status fields."""
    client = get_supabase_client()
    channel_id = str(channel["id"])
    result_status = _classify_confidence(result.confidence)
    now = datetime.now(timezone.utc).isoformat()

    # Only store brand/url on non-clean outcomes.
    flagged_brand = result.flagged_brand if result_status != "clean" else None
    source_url = result.source_url if result_status != "clean" else None

    evidence_payload = [
        {
            "type": s.signal_type,
            "value": s.matched_value,
            "weight": round(s.weight, 4),
            "source_url": s.source_url,
            "context": s.context,
        }
        for s in result.signals
    ] or None

    gate0_record: dict[str, object] = {
        "channel_id": channel_id,
        "checked_at": now,
        "search_query": search_query,
        "result_status": result_status,
        "flagged_brand": flagged_brand,
        "source_url": source_url,
        "confidence": round(result.confidence, 4),
        "evidence_signals": evidence_payload,
    }
    insert_res = client.table("gate0_results").insert(gate0_record).execute()
    gate0_id = None
    if insert_res.data:
        gate0_id = insert_res.data[0].get("id")

    client.table("channels").update(
        {
            "gate0_status": result_status,
            "gate0_checked_at": now,
            "gate0_result_id": gate0_id,
            "gate0_search_query": search_query,
            "gate0_result_status": result_status,
            "gate0_flagged_brand": flagged_brand,
            "gate0_source_url": source_url,
            "updated_at": now,
        }
    ).eq("id", channel_id).execute()

    logger.info(
        "Gate 0 complete for %s: %s (brand=%s, confidence=%.3f)",
        channel_id,
        result_status,
        flagged_brand,
        result.confidence,
    )
    return gate0_record


def _mark_gate0_unchecked(channel_id: str, reason: str) -> None:
    """Clear a stuck pending status so the channel can be retried later."""
    now = datetime.now(timezone.utc).isoformat()
    get_supabase_client().table("channels").update(
        {"gate0_status": "unchecked", "updated_at": now}
    ).eq("id", channel_id).execute()
    logger.warning("Gate 0 marked unchecked for %s: %s", channel_id, reason)


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------

def _load_competitors() -> tuple[Gate0CompetitorSetting, ...]:
    """Read Gate 0 competitors from system_settings. Returns empty tuple on failure."""
    try:
        client = get_supabase_client()
        result = (
            client.table("system_settings")
            .select("gate0_competitors")
            .eq("singleton_key", "global")
            .single()
            .execute()
        )
        raw = (result.data or {}).get("gate0_competitors")
        if isinstance(raw, list):
            return tuple(
                Gate0CompetitorSetting(
                    str(item["brand"]),
                    tuple(str(d) for d in (item.get("domains") or [])),
                )
                for item in raw
                if isinstance(item, dict) and item.get("brand")
            )
    except Exception:
        logger.warning("Failed to load gate0 competitors from DB", exc_info=True)
    return ()


def _parse_datetime(value: object) -> datetime | None:
    """Parse a Supabase timestamp into an aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _should_run_gate0_check(
    channel: dict[str, object],
    manual: bool = False,
    clean_recheck_days: int = 7,
) -> tuple[bool, str | None]:
    """Return whether a Gate 0 task should consume search quota."""
    if manual:
        return True, None

    status = channel.get("gate0_status")

    # dirty and needs_review are both frozen for automatic rechecks.
    # needs_review requires human adjudication before it can transition.
    if status in ("dirty", "needs_review"):
        return False, f"{status} channels are not rechecked automatically"

    if status == "clean":
        checked_at = _parse_datetime(channel.get("gate0_checked_at"))
        if checked_at is not None:
            age = datetime.now(timezone.utc) - checked_at
            if age < timedelta(days=clean_recheck_days):
                return (
                    False,
                    f"clean channel checked within the last {clean_recheck_days} days",
                )

    return True, None


def _extract_channel_handle(channel_url: str) -> str | None:
    """Extract a short searchable handle from a channel URL."""
    m = re.search(r"rumble\.com/(?:c|user)/([^/?#]+)", channel_url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"substack\.com/@([^/?#]+)", channel_url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b([a-z0-9-]+)\.substack\.com", channel_url, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _run_gate0_sync(
    channel_id: str,
    manual: bool = False,
) -> dict[str, object]:
    """Synchronous Gate 0 check implementation."""
    runtime = get_runtime_settings()
    if not runtime.settings_loaded:
        _mark_gate0_unchecked(channel_id, "runtime settings unavailable")
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason="runtime_settings_unavailable",
        ).model_dump(mode="json")

    if not runtime.gate0_enabled:
        _mark_gate0_unchecked(channel_id, "gate0 disabled")
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason="gate0_disabled",
        ).model_dump(mode="json")

    client = get_supabase_client()
    ch_result = (
        client.table("channels")
        .select("*")
        .eq("id", channel_id)
        .maybe_single()
        .execute()
    )
    if ch_result.data is None:
        raise ValueError(f"Channel {channel_id} not found")

    channel = ch_result.data
    should_run, skip_reason = _should_run_gate0_check(
        channel,
        manual=manual,
        clean_recheck_days=runtime.gate0_clean_recheck_days,
    )
    if not should_run:
        logger.info("Gate 0 skipped for %s: %s", channel_id, skip_reason)
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason=skip_reason,
        ).model_dump(mode="json")

    channel_name = str(channel.get("name") or "")
    channel_url_str = str(channel.get("channel_url") or "")
    channel_handle = _extract_channel_handle(channel_url_str)
    channel_identifiers: frozenset[str] = frozenset(filter(None, [
        channel_name.lower() if channel_name else None,
        channel_handle.lower() if channel_handle else None,
    ]))
    competitors = _load_competitors()
    if not competitors:
        _mark_gate0_unchecked(channel_id, "no gate0 competitors configured")
        return Gate0TaskResult(
            channel_id=channel_id,
            skipped=True,
            reason="no_gate0_competitors_configured",
        ).model_dump(mode="json")

    # Layer 1: local scan (zero API cost)
    local_result = _scan_channel_local(channel, competitors)

    search_queries = _build_search_queries(channel_name, channel_handle, competitors)
    primary_query = search_queries[0] if search_queries else f'"{channel_name}" "{competitors[0].brand}"'

    # Layer 2: Serper (API cost) — skip if local scan already reaches dirty threshold
    if local_result.confidence >= _THRESHOLD_DIRTY:
        final_result = local_result
        search_query = primary_query
    else:
        serper_brand, serper_url, search_query, serper_confidence = _run_serper_search_multi(
            search_queries,
            competitors,
            channel_identifiers,
        )
        if serper_confidence > 0.0:
            combined_weights = [s.weight for s in local_result.signals] + [serper_confidence]
            combined_confidence = _compound_confidence(combined_weights)
            combined_signals = local_result.signals.copy()
            combined_signals.append(
                EvidenceSignal("serper_hit", serper_brand or "", serper_confidence, serper_url)
            )
            # Prefer Serper URL (external evidence page) over the channel's own URL
            # that comes from a local brand/title match. If local source is a specific
            # competitor URL (from a domain match in contact_info), keep it — but those
            # cases reach dirty threshold and skip Serper entirely.
            local_url = local_result.source_url
            is_channel_self = bool(
                local_url and channel_url_str and
                local_url.rstrip("/") == channel_url_str.rstrip("/")
            )
            combined_url = (serper_url or local_url) if is_channel_self else (local_url or serper_url)
            final_result = ScanResult(
                local_result.flagged_brand or serper_brand,
                combined_url,
                combined_confidence,
                combined_signals,
            )
        else:
            final_result = local_result
            if not search_query:
                search_query = primary_query

    gate0_record = _persist_gate0_result(channel, search_query, final_result)
    return Gate0TaskResult(
        channel_id=channel_id,
        checked_at=str(gate0_record["checked_at"]),
        search_query=search_query,
        result_status=str(gate0_record["result_status"]),
        flagged_brand=gate0_record.get("flagged_brand"),  # type: ignore[arg-type]
        source_url=gate0_record.get("source_url"),  # type: ignore[arg-type]
        confidence=gate0_record.get("confidence"),  # type: ignore[arg-type]
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="scraper.tasks.run_gate0_all")
def run_gate0_all(
    recheck_clean: bool = False,
    dashboard_eligible_only: bool = False,
    force_all: bool = False,
) -> dict[str, object]:
    """Fetch all eligible channels and dispatch individual run_gate0 tasks.

    Args:
        recheck_clean:           When True, also re-queue clean channels.
        dashboard_eligible_only: When True, restrict to dashboard_eligible=True channels.
        force_all:               When True, process every active+scraped channel regardless
                                 of current gate0_status (dirty/clean/needs_review included),
                                 overwriting all previous Gate 0 results.
    """
    client = get_supabase_client()
    try:
        base_query = (
            client.table("channels")
            .select("id,gate0_status")
            .eq("is_active", True)
            .eq("has_been_scraped", True)
        )
        if not force_all and not recheck_clean:
            base_query = base_query.in_("gate0_status", ["unchecked", "pending"])
        if dashboard_eligible_only:
            base_query = base_query.eq("dashboard_eligible", True)

        # Paginate to bypass the PostgREST default 1000-row cap.
        channels: list[dict] = []
        batch_size = 1000
        offset = 0
        while True:
            batch = base_query.range(offset, offset + batch_size - 1).execute().data or []
            channels.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size
    except APIError as exc:
        logger.error("run_gate0_all: failed to fetch channels: %s", exc)
        return {"error": str(exc), "queued": 0}

    # force_all dispatches with manual=True so _should_run_gate0_check cannot block any channel.
    manual = force_all
    queued = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for ch in channels:
        channel_id = str(ch.get("id") or "")
        if not channel_id:
            continue
        try:
            client.table("channels").update(
                {"gate0_status": "pending", "updated_at": now_iso}
            ).eq("id", channel_id).execute()
            celery_app.send_task(
                "scraper.tasks.run_gate0",
                args=[channel_id, manual],
                queue=QUEUE_GATE0,
            )
            queued += 1
        except Exception as exc:
            logger.warning("run_gate0_all: failed to queue %s: %s", channel_id, exc)

    logger.info(
        "run_gate0_all: queued=%d total_fetched=%d recheck_clean=%s "
        "dashboard_eligible_only=%s force_all=%s",
        queued, len(channels), recheck_clean, dashboard_eligible_only, force_all,
    )
    return {"queued": queued, "total_fetched": len(channels)}


@celery_app.task(
    bind=True,
    max_retries=2,
    name="scraper.tasks.run_gate0",
)
def run_gate0(
    self: Task, channel_id: str, manual: bool = False
) -> dict[str, object]:
    """Run a Gate 0 compliance check for a channel."""
    logger.info("Running Gate 0 for channel %s", channel_id)
    try:
        return _run_gate0_sync(channel_id, manual=manual)
    except (APIError, httpx.HTTPError, RuntimeError, ValueError) as exc:
        logger.error("Gate 0 failed for %s: %s", channel_id, exc, exc_info=True)
        is_quota_error = isinstance(exc, RuntimeError) and "quota" in str(exc).lower()
        if is_quota_error or self.request.retries >= self.max_retries:
            try:
                _mark_gate0_unchecked(channel_id, str(exc))
            except APIError:
                logger.error(
                    "Failed to clear Gate 0 pending status for %s",
                    channel_id,
                    exc_info=True,
                )
            return Gate0TaskResult(
                channel_id=channel_id,
                skipped=True,
                reason=f"gate0_failed: {exc}",
            ).model_dump(mode="json")
        raise self.retry(exc=exc, countdown=30)
