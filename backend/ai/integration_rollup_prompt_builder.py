from __future__ import annotations

import json

_BASE_INSTRUCTIONS = """You are performing automated integration rollup analysis for PlanningTree.
This is a read-only analysis run over a review node's integration thread.

Rules:
1. Treat the seeded integration context as the primary source of truth.
2. You may inspect the workspace or repository for implementation details if needed.
3. Do not mutate files or propose write actions in this run.
4. Return ONLY valid JSON with exactly one key: "summary".
5. The summary must be non-empty and should concisely capture integration quality, gaps, and overall package readiness.
"""


def build_integration_rollup_base_instructions() -> str:
    return _BASE_INSTRUCTIONS


def build_integration_rollup_prompt(system_messages: list[dict[str, object]]) -> str:
    sections = ["Integration rollup context:"]
    for message in system_messages:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "").strip()
        if content:
            sections.append(content)

    sections.append(
        "Respond with valid JSON in exactly this shape:\n"
        '```json\n{"summary": "Concise integration rollup summary."}\n```'
    )
    return "\n\n".join(sections)


def extract_integration_rollup_summary(text: str) -> str | None:
    payload = _extract_json_object(text)
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    if not isinstance(summary, str):
        return None
    cleaned = summary.strip()
    return cleaned or None


def render_integration_rollup_message(summary: str, sha: str) -> str:
    return (
        "## Integration Rollup\n\n"
        f"**Summary:** {summary}\n\n"
        f"**Final SHA:** {sha}\n"
    )


def _extract_json_object(text: str) -> dict[str, object] | None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return None

    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
