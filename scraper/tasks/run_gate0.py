"""Celery task: run Gate 0 compliance check for a channel."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from celery import Task
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client
from core.runtime_settings import Gate0CompetitorSetting, get_runtime_settings
from models import Gate0TaskResult
from tasks.task_queues import QUEUE_GATE0
from utils.ai_response import extract_json_object, extract_response_text

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

# Words that signal an explicit affiliation rather than a loose mention.
_EXPLICIT_AFFILIATION_WORDS = frozenset({
    "sponsor", "sponsored", "partner", "partnered", "affiliate",
    "affiliated", "referral", "referrer", "refers", "promotion",
    "promotional", "paid", "paid partnership", "ad", "advertisement",
    "ambassador", "collab", "collaboration", "endorsement",
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

# AI verification settings
_AI_MODEL = "gemini-2.5-flash"
_AI_MAX_OUTPUT_TOKENS = 700
_AI_EVIDENCE_DOC_LIMIT = 6
_AI_TEXT_WINDOW = 260
_AI_TRUSTED_SOURCE_KINDS = frozenset({
    "channel_local",
    "channel_page",
    "redirected_channel_link",
})
_AI_ALLOWED_DIRTY_KINDS = frozenset({
    "channel_local",
    "channel_page",
    "redirected_channel_link",
})


@dataclass
class EvidenceSignal:
    """A single confidence signal contributing to a Gate 0 determination."""

    signal_type: str
    matched_value: str
    weight: float
    source_url: str | None = None
    context: str | None = None
    source_kind: str = "channel_local"
    explicit: bool = False
    trusted: bool = False
    ai_note: str | None = None


@dataclass
class ScanResult:
    """Aggregated Gate 0 scan outcome with compound confidence and evidence trail."""

    flagged_brand: str | None = None
    source_url: str | None = None
    confidence: float = 0.0
    signals: list[EvidenceSignal] = dc_field(default_factory=list)
    result_status: str | None = None
    ai_decision: str | None = None
    ai_confidence: float | None = None
    ai_reason: str | None = None
    verification_source_url: str | None = None


@dataclass
class EvidenceDocument:
    """A fetched or extracted evidence source used for AI verification."""

    source_url: str
    source_kind: str
    title: str | None = None
    text: str | None = None
    trust: str = "low"
    matched_value: str | None = None
    matched_context: str | None = None
    signal_type: str | None = None


@dataclass
class AIVerdict:
    """Conservative AI verification result for borderline Gate 0 evidence."""

    decision: str
    confidence: float
    reason: str | None = None
    matched_brand: str | None = None
    source_url: str | None = None
    supporting_quotes: list[str] = dc_field(default_factory=list)
    conflicting_quotes: list[str] = dc_field(default_factory=list)
    raw_json: dict[str, object] | None = None


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


def _has_explicit_affiliation_context(text: str, term: str) -> bool:
    """Return True only for direct relationship language around the term."""
    window = _context_window(text, term).lower()
    return any(word in window for word in _EXPLICIT_AFFILIATION_WORDS)


def _quote_is_explicit_affiliation(quote: str) -> bool:
    lower = quote.lower()
    return any(word in lower for word in _EXPLICIT_AFFILIATION_WORDS)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _has_affiliate_pattern(url: str) -> bool:
    return bool(_AFFILIATE_PATTERN.search(url))


def _has_explicit_affiliation_path(url: str) -> bool:
    """True for URLs whose path/query strongly implies affiliation."""
    lower = url.lower()
    return any(marker in lower for marker in (
        "/partner", "/partners", "/affiliate", "/affiliates", "/sponsor",
        "/sponsored", "/referral", "/ref", "utm_source=", "utm_campaign=",
    ))


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


def _normalize_source_kind(source_kind: str | None) -> str:
    if not source_kind:
        return "channel_local"
    return source_kind


def _extract_visible_text(html_text: str) -> tuple[str | None, str]:
    """Return page title and visible text from HTML."""
    soup = BeautifulSoup(html_text, "lxml")
    for node in soup(["script", "style", "noscript", "svg", "canvas"]):
        node.decompose()

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip() or None

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def _extract_context_excerpt(text: str, term: str, width: int = _AI_TEXT_WINDOW) -> str:
    """Return a compact evidence window around the first term occurrence."""
    if not text or not term:
        return ""
    idx = text.lower().find(term.lower())
    if idx == -1:
        return text[: width * 2].strip()
    start = max(0, idx - width)
    end = min(len(text), idx + len(term) + width)
    return text[start:end].strip()


def _fetch_evidence_document(
    url: str,
    source_kind: str,
    matched_value: str | None = None,
    matched_context: str | None = None,
    signal_type: str | None = None,
) -> EvidenceDocument | None:
    """Fetch a page and normalize it into an evidence document for AI review."""
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, max_redirects=5) as http:
            response = http.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
    except Exception:
        return None

    final_url = str(response.url)
    content_type = (response.headers.get("content-type") or "").lower()
    title = None
    text = ""

    if "html" in content_type:
        try:
            title, text = _extract_visible_text(response.text)
        except Exception:
            text = response.text.strip()
    else:
        text = response.text.strip()

    if not text:
        return None

    if matched_value:
        excerpt = _extract_context_excerpt(text, matched_value)
    elif matched_context:
        excerpt = _extract_context_excerpt(text, matched_context)
    else:
        excerpt = text[: 2 * _AI_TEXT_WINDOW]

    excerpt = excerpt[: 2 * _AI_TEXT_WINDOW].strip()
    if not excerpt:
        excerpt = text[: 2 * _AI_TEXT_WINDOW].strip()

    trust = "high" if _normalize_source_kind(source_kind) in _AI_TRUSTED_SOURCE_KINDS else "medium"
    if _normalize_source_kind(source_kind) == "serper_result":
        trust = "low"

    return EvidenceDocument(
        source_url=final_url,
        source_kind=_normalize_source_kind(source_kind),
        title=title,
        text=excerpt or text[: 2 * _AI_TEXT_WINDOW],
        trust=trust,
        matched_value=matched_value,
        matched_context=matched_context,
        signal_type=signal_type,
    )


def _signal_payload(signal: EvidenceSignal) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": signal.signal_type,
        "value": signal.matched_value,
        "weight": round(signal.weight, 4),
        "source_url": signal.source_url,
        "context": signal.context,
        "source_kind": signal.source_kind,
        "explicit": signal.explicit,
        "trusted": signal.trusted,
    }
    if signal.ai_note:
        payload["ai_note"] = signal.ai_note
    return {key: value for key, value in payload.items() if value is not None}


def _looks_explicit(signal: EvidenceSignal) -> bool:
    """Return True when a signal is explicit enough to justify dirty status."""
    if signal.signal_type in {"domain_in_contact", "redirect_to_domain"}:
        return signal.explicit and signal.source_kind in _AI_ALLOWED_DIRTY_KINDS
    if signal.signal_type in {"brand_in_description", "domain_in_description"}:
        return signal.explicit and signal.source_kind in _AI_ALLOWED_DIRTY_KINDS
    if signal.signal_type == "title_promo":
        return signal.explicit and signal.source_kind in _AI_ALLOWED_DIRTY_KINDS
    return False


def _has_dirty_direct_evidence(signals: list[EvidenceSignal]) -> bool:
    return any(_looks_explicit(signal) for signal in signals)


def _has_any_positive_signal(signals: list[EvidenceSignal]) -> bool:
    return any(signal.weight > 0.0 for signal in signals)


def _is_valid_ai_quote(quote: str, documents: list[EvidenceDocument]) -> bool:
    normalized = quote.strip().lower()
    if not normalized:
        return False
    return any(normalized in (doc.text or "").lower() for doc in documents)


def _parse_ai_assessment(raw_text: str | None, documents: list[EvidenceDocument]) -> AIVerdict:
    data = extract_json_object(raw_text)
    if data is None or not isinstance(data, dict):
        return AIVerdict(
            decision="needs_review",
            confidence=0.0,
            reason="AI response did not include valid JSON.",
            raw_json=None,
        )

    decision = str(data.get("decision") or "needs_review").strip().lower()
    if decision not in {"clean", "needs_review", "dirty"}:
        decision = "needs_review"

    try:
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    matched_brand = data.get("matched_brand")
    if not isinstance(matched_brand, str) or not matched_brand.strip():
        matched_brand = None
    else:
        matched_brand = matched_brand.strip()

    source_url = data.get("matched_source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        source_url = None
    else:
        source_url = source_url.strip()

    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = None
    else:
        reason = reason.strip()

    quotes: list[str] = []
    raw_quotes = data.get("supporting_quotes")
    if isinstance(raw_quotes, list):
        for quote in raw_quotes:
            if isinstance(quote, str) and _is_valid_ai_quote(quote, documents):
                quotes.append(quote.strip())
            elif isinstance(quote, dict):
                raw_quote = quote.get("quote")
                if isinstance(raw_quote, str) and _is_valid_ai_quote(raw_quote, documents):
                    quotes.append(raw_quote.strip())

    conflicts: list[str] = []
    raw_conflicts = data.get("conflicting_quotes")
    if isinstance(raw_conflicts, list):
        for quote in raw_conflicts:
            if isinstance(quote, str) and quote.strip():
                conflicts.append(quote.strip())

    if decision == "dirty" and not quotes:
        decision = "needs_review"
        reason = "AI requested dirty but did not provide a verifiable supporting quote."

    if decision == "dirty" and quotes and not any(_quote_is_explicit_affiliation(quote) for quote in quotes):
        decision = "needs_review"
        reason = "AI requested dirty but the supporting quotes were not explicit enough."

    if decision == "dirty" and confidence < 0.95:
        decision = "needs_review"
        reason = "AI confidence was below the dirty threshold."

    if decision == "dirty" and source_url is None and documents:
        source_url = documents[0].source_url

    return AIVerdict(
        decision=decision,
        confidence=confidence,
        reason=reason,
        matched_brand=matched_brand,
        source_url=source_url,
        supporting_quotes=quotes,
        conflicting_quotes=conflicts,
        raw_json=data,
    )


def _build_ai_prompt(
    channel: dict[str, object],
    competitors: tuple[Gate0CompetitorSetting, ...],
    evidence_documents: list[EvidenceDocument],
) -> str:
    """Build a conservative verification prompt for the AI verifier."""
    channel_name = str(channel.get("name") or "")
    channel_url = str(channel.get("channel_url") or "")
    description = str(channel.get("description") or "")
    recent_titles = channel.get("video_titles") or []
    if isinstance(recent_titles, str):
        recent_titles = [recent_titles]
    titles = [str(title) for title in recent_titles[:10] if title]

    competitors_block = [
        {
            "brand": competitor.brand,
            "domains": list(competitor.domains),
        }
        for competitor in competitors
    ]

    evidence_block: list[dict[str, object]] = []
    for idx, document in enumerate(evidence_documents, start=1):
        evidence_block.append(
            {
                "id": idx,
                "source_url": document.source_url,
                "source_kind": document.source_kind,
                "trust": document.trust,
                "title": document.title,
                "matched_value": document.matched_value,
                "matched_context": document.matched_context,
                "signal_type": document.signal_type,
                "text": document.text[:1200] if document.text else None,
            }
        )

    prompt = {
        "task": "Verify whether the channel has an explicit affiliation with any competitor brand.",
        "rules": [
            "Only mark dirty when the evidence explicitly shows sponsor, sponsored, partner, affiliate, referral, paid placement, ambassador, or equivalent relationship.",
            "Do not infer dirty from a bare brand mention, a bare domain mention, or a generic third-party search result.",
            "If evidence is indirect or ambiguous, return needs_review.",
            "If there is no explicit affiliation evidence, return clean.",
            "Use only the provided evidence documents. Do not invent facts or quotes.",
            "Every supporting quote must be copied verbatim from one of the evidence documents.",
            "Prefer precision over recall. False dirty must be avoided.",
        ],
        "channel": {
            "name": channel_name,
            "url": channel_url,
            "description": description,
            "recent_titles": titles,
        },
        "competitors": competitors_block,
        "evidence_documents": evidence_block,
        "required_output": {
            "decision": "clean | needs_review | dirty",
            "confidence": 0.0,
            "matched_brand": "string or null",
            "matched_source_url": "string or null",
            "supporting_quotes": ["verbatim quote strings"],
            "conflicting_quotes": ["optional conflicting quote strings"],
            "reason": "short explanation",
        },
    }
    return json.dumps(prompt, ensure_ascii=False)


def _run_gate0_ai_verification(
    channel: dict[str, object],
    competitors: tuple[Gate0CompetitorSetting, ...],
    evidence_documents: list[EvidenceDocument],
) -> AIVerdict | None:
    api_key = scraper_settings.google_api_key
    if not api_key or not evidence_documents:
        return None

    try:
        from google import genai
        from google.genai import types
    except Exception:
        logger.warning("google-genai is unavailable; skipping Gate 0 AI verification")
        return None

    client = genai.Client(api_key=api_key)
    prompt = _build_ai_prompt(channel, competitors, evidence_documents)

    try:
        response = client.models.generate_content(
            model=_AI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a conservative evidence verifier for a compliance screen. "
                    "Return JSON only. Never mark dirty unless the evidence explicitly shows "
                    "a direct affiliation. Prefer needs_review over dirty whenever uncertain."
                ),
                response_mime_type="application/json",
                max_output_tokens=_AI_MAX_OUTPUT_TOKENS,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
    except Exception as exc:
        logger.warning("Gate 0 AI verification failed: %s", exc, exc_info=True)
        return None

    raw_text = extract_response_text(response)
    verdict = _parse_ai_assessment(raw_text, evidence_documents)

    if verdict.decision == "dirty":
        allowed_kinds = _AI_ALLOWED_DIRTY_KINDS
        if not any(doc.source_kind in allowed_kinds for doc in evidence_documents):
            verdict = AIVerdict(
                decision="needs_review",
                confidence=min(verdict.confidence, 0.94),
                reason="AI identified a suspicious relationship, but the evidence source was not trusted enough for dirty.",
                matched_brand=verdict.matched_brand,
                source_url=verdict.source_url,
                supporting_quotes=verdict.supporting_quotes,
                conflicting_quotes=verdict.conflicting_quotes,
                raw_json=verdict.raw_json,
            )

    return verdict


def _build_evidence_documents(
    channel: dict[str, object],
    local_result: ScanResult,
    serper_brand: str | None,
    serper_url: str | None,
) -> list[EvidenceDocument]:
    """Build the compact evidence packet sent to the AI verifier."""
    documents: list[EvidenceDocument] = []
    seen: set[str] = set()
    channel_url = str(channel.get("channel_url") or "")

    def add_document(document: EvidenceDocument | None) -> None:
        if document is None:
            return
        key = document.source_url.rstrip("/").lower()
        if key in seen:
            return
        seen.add(key)
        documents.append(document)

    for signal in local_result.signals:
        source_url = signal.source_url or channel_url or "channel-local"
        if source_url.startswith(("http://", "https://")):
            add_document(
                _fetch_evidence_document(
                    source_url,
                    signal.source_kind,
                    matched_value=signal.matched_value,
                    matched_context=signal.context,
                    signal_type=signal.signal_type,
                )
            )
        else:
            text = signal.context or signal.matched_value
            if not text:
                continue
            add_document(EvidenceDocument(
                source_url=source_url,
                source_kind=signal.source_kind,
                title=str(signal.source_url or "Channel local evidence"),
                text=text,
                trust="high" if signal.trusted else "medium",
                matched_value=signal.matched_value,
                matched_context=signal.context,
                signal_type=signal.signal_type,
            ))

    if serper_url and serper_url.startswith(("http://", "https://")):
        add_document(
            _fetch_evidence_document(
                serper_url,
                "serper_result",
                matched_value=serper_brand,
                matched_context=serper_brand,
                signal_type="serper_hit",
            )
        )

    if not documents and serper_brand and serper_url:
        add_document(EvidenceDocument(
            source_url=serper_url,
            source_kind="serper_result",
            title="Serper hit",
            text=f"{serper_brand} {serper_url}",
            trust="low",
            matched_value=serper_brand,
            matched_context=serper_brand,
            signal_type="serper_hit",
        ))

    return documents[:_AI_EVIDENCE_DOC_LIMIT]


def _normalize_gate0_status(
    local_result: ScanResult,
    ai_verdict: AIVerdict | None,
    evidence_documents: list[EvidenceDocument],
) -> tuple[str, float, str | None]:
    """Return (result_status, confidence, source_url) using conservative rules."""
    has_dirty_signal = _has_dirty_direct_evidence(local_result.signals)
    has_positive_signal = _has_any_positive_signal(local_result.signals)

    if ai_verdict and ai_verdict.decision == "dirty":
        has_dirty_signal = has_dirty_signal or any(
            doc.source_kind in _AI_ALLOWED_DIRTY_KINDS for doc in evidence_documents
        )

    if has_dirty_signal:
        status = "dirty"
    elif has_positive_signal or (ai_verdict is not None and ai_verdict.decision in {"needs_review", "dirty"}):
        status = "needs_review"
    else:
        status = "clean"

    confidence = local_result.confidence
    if ai_verdict is not None:
        confidence = max(confidence, ai_verdict.confidence)

    if status == "clean":
        confidence = min(confidence, 0.79)
    elif status == "needs_review":
        confidence = min(max(confidence, 0.80), 0.94)
    else:
        confidence = max(confidence, 0.95)

    source_url = local_result.source_url
    if ai_verdict and ai_verdict.source_url:
        source_url = ai_verdict.source_url
    elif not source_url and evidence_documents:
        source_url = evidence_documents[0].source_url

    return status, confidence, source_url


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
                explicit = _has_affiliate_pattern(url) or _has_explicit_affiliation_path(url)
                return [EvidenceSignal(
                    "domain_in_contact",
                    domain,
                    weight,
                    url,
                    None,
                    "channel_local",
                    explicit,
                    True,
                )]

        if _contains_brand(url_lower, competitor.brand):
            explicit = _has_explicit_affiliation_path(url)
            return [EvidenceSignal(
                "brand_in_contact",
                competitor.brand,
                0.70,
                url,
                None,
                "channel_local",
                explicit,
                True,
            )]

    # No immediate match — follow redirect if it's a known link shortener.
    if _should_follow_redirect(url):
        resolved = _follow_url_redirect(url)
        if resolved:
            resolved_lower = resolved.lower()
            for competitor in competitors:
                for domain in competitor.domains:
                    if _contains_domain(resolved_lower, domain):
                        explicit = _has_explicit_affiliation_path(resolved)
                        return [EvidenceSignal(
                            "redirect_to_domain",
                            domain,
                            _W_REDIRECT_TO_DOMAIN,
                            resolved,
                            None,
                            "redirected_channel_link",
                            explicit,
                            True,
                        )]

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
                is_explicit = _has_explicit_affiliation_context(text, domain)
                weight = _W_DOMAIN_DESCRIPTION_PROMO if has_promo else _W_DOMAIN_IN_DESCRIPTION
                source = _source_url_for_domain(text, fallback_url, domain)
                ctx = _context_window(text, domain)
                signals.append(EvidenceSignal(
                    f"domain_in_{field_type}",
                    domain,
                    weight,
                    source,
                    ctx,
                    "channel_text",
                    is_explicit,
                    True,
                ))
                break

        if not domain_matched and _contains_brand(text_lower, competitor.brand):
            if not _has_negative_context(text, competitor.brand):
                has_promo = _has_promo_context(text, competitor.brand)
                is_explicit = _has_explicit_affiliation_context(text, competitor.brand)
                weight = _W_BRAND_DESCRIPTION_PROMO if has_promo else _W_BRAND_IN_DESCRIPTION
                ctx = _context_window(text, competitor.brand)
                source_label = {
                    "description": "Channel description",
                    "name": "Channel name",
                }.get(field_type, f"Channel {field_type}")
                signals.append(EvidenceSignal(
                    f"brand_in_{field_type}",
                    competitor.brand,
                    weight,
                    source_label,
                    ctx,
                    "channel_text",
                    is_explicit,
                    True,
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
            explicit = any(_has_explicit_affiliation_context(title, competitor.brand) or _has_explicit_affiliation_context(title, domain)
                           for title in promo_hits for domain in competitor.domains)
            signals.append(EvidenceSignal(
                "title_promo",
                competitor.brand,
                weight,
                "Channel video titles",
                "; ".join(promo_hits[:3]),
                "channel_video_titles",
                explicit,
                True,
            ))

        if neutral_hits:
            n = len(neutral_hits)
            weight = _W_MULTI_TITLE_NEUTRAL if n >= 3 else _W_ONE_TITLE_NEUTRAL
            signals.append(EvidenceSignal(
                "title_neutral",
                competitor.brand,
                weight,
                "Channel video titles",
                "; ".join(neutral_hits[:3]),
                "channel_video_titles",
                False,
                True,
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

    for item in organic_results[:10]:
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
            json={"q": search_query, "num": 10},
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
    result_status = result.result_status or _classify_confidence(result.confidence)
    now = datetime.now(timezone.utc).isoformat()

    # Only store brand/url on non-clean outcomes.
    flagged_brand = result.flagged_brand if result_status != "clean" else None
    source_url = result.source_url if result_status != "clean" else None

    evidence_payload = [
        _signal_payload(s)
        for s in result.signals
    ] or None

    if result.ai_decision:
        evidence_payload = (evidence_payload or []) + [
            {
                "type": "ai_verification",
                "value": result.ai_decision,
                "weight": round(result.ai_confidence or 0.0, 4),
                "source_url": result.verification_source_url,
                "context": result.ai_reason,
                "ai_decision": result.ai_decision,
            }
        ]

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

    local_result = _scan_channel_local(channel, competitors)
    search_queries = _build_search_queries(channel_name, channel_handle, competitors)
    primary_query = search_queries[0] if search_queries else f'"{channel_name}" "{competitors[0].brand}"'

    serper_brand: str | None = None
    serper_url: str | None = None
    search_query = primary_query
    serper_confidence = 0.0
    combined_result = local_result

    # If the local scan already found explicit direct affiliation evidence, keep the
    # path cheap: no search and no AI round-trip are needed.
    if not _has_dirty_direct_evidence(local_result.signals):
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
                EvidenceSignal(
                    "serper_hit",
                    serper_brand or "",
                    serper_confidence,
                    serper_url,
                    None,
                    "serper_result",
                    False,
                    False,
                )
            )
            local_url = local_result.source_url
            is_channel_self = bool(
                local_url and channel_url_str and
                local_url.rstrip("/") == channel_url_str.rstrip("/")
            )
            combined_url = (serper_url or local_url) if is_channel_self else (local_url or serper_url)
            combined_result = ScanResult(
                local_result.flagged_brand or serper_brand,
                combined_url,
                combined_confidence,
                combined_signals,
            )
        else:
            combined_result = local_result

    evidence_documents: list[EvidenceDocument] = []
    ai_verdict: AIVerdict | None = None

    if _has_dirty_direct_evidence(combined_result.signals):
        result_status = "dirty"
        normalized_confidence = max(combined_result.confidence, 0.95)
        normalized_source_url = combined_result.source_url or serper_url or channel_url_str
    else:
        evidence_documents = _build_evidence_documents(
            channel,
            combined_result,
            serper_brand,
            serper_url,
        )
        ai_verdict = _run_gate0_ai_verification(channel, competitors, evidence_documents)

        result_status, normalized_confidence, normalized_source_url = _normalize_gate0_status(
            combined_result,
            ai_verdict,
            evidence_documents,
        )

        # Final safety net: if no direct evidence exists, never persist dirty.
        if result_status == "dirty":
            result_status = "needs_review"
            normalized_confidence = min(normalized_confidence, 0.94)

    final_result = ScanResult(
        combined_result.flagged_brand,
        normalized_source_url,
        normalized_confidence,
        combined_result.signals,
        result_status=result_status,
        ai_decision=ai_verdict.decision if ai_verdict else None,
        ai_confidence=ai_verdict.confidence if ai_verdict else None,
        ai_reason=ai_verdict.reason if ai_verdict else None,
        verification_source_url=ai_verdict.source_url if ai_verdict else None,
    )

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

@celery_app.task(name="scraper.tasks.run_gate0_all", queue="gate0")
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
    queue="gate0",
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
