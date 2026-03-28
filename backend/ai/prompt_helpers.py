"""Shared helpers used by multiple prompt builders."""

from __future__ import annotations

import re
from typing import Any


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_frame_content(frame_content: str, char_limit: int = 6000) -> str:
    """Format a frame document for inclusion in a generation prompt."""
    content = frame_content.strip()
    if not content:
        return "Frame document: (empty)"
    if len(content) > char_limit:
        content = content[: char_limit - 3] + "..."
    return f"Confirmed frame document:\n\n{content}"


_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n(.*?)\n\s*```\s*$",
    re.DOTALL,
)


def strip_json_fence(text: str) -> str:
    """Strip markdown code fences (```json ... ```) wrapping JSON content.

    Returns the inner content if a fence is found, otherwise the original text.
    """
    m = _FENCE_RE.match(text.strip())
    if m:
        return m.group(1).strip()
    return text.strip()
