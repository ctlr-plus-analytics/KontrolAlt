"""Helpers for provider response text and JSON extraction."""

from __future__ import annotations

import json


def extract_json_object(raw_text: str | None) -> dict[str, object] | None:
    """Extract the first JSON object from a model response."""
    if not raw_text or not raw_text.strip():
        return None
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    candidates = [text]
    first_brace = text.find("{")
    if first_brace > 0:
        candidates.append(text[first_brace:])

    for candidate in candidates:
        try:
            data, _end = decoder.raw_decode(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def extract_response_text(response: object) -> str | None:
    """Extract text from Google GenAI responses, including candidate parts."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    parts: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                parts.append(part_text)
    return "\n".join(parts) if parts else None
