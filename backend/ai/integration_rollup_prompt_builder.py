from __future__ import annotations

import json

from backend.storage.storage import Storage

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


def build_rollup_prompt_from_storage(
    storage: Storage,
    project_id: str,
    review_node_id: str,
) -> str:
    with storage.project_lock(project_id):
        snapshot = storage.project_store.load_snapshot(project_id)
        node_index = snapshot.get("tree_state", {}).get("node_index", {})
        if not isinstance(node_index, dict):
            node_index = {}
        review_node = node_index.get(review_node_id, {})
        parent_id = str(review_node.get("parent_id") or "").strip()
        parent = node_index.get(parent_id, {}) if parent_id else {}
        review_state = storage.review_state_store.read_state(project_id, review_node_id) or {}

    sections = ["Integration rollup context:"]

    parent_title = str(parent.get("title") or "").strip()
    parent_description = str(parent.get("description") or "").strip()
    if parent_title or parent_description:
        lines = ["Parent task context:"]
        if parent_title:
            lines.append(f"- Title: {parent_title}")
        if parent_description:
            lines.append(f"- Description: {parent_description}")
        sections.append("\n".join(lines))

    checkpoint_lines: list[str] = []
    checkpoints = review_state.get("checkpoints", [])
    if isinstance(checkpoints, list):
        for checkpoint in checkpoints:
            if not isinstance(checkpoint, dict):
                continue
            summary = str(checkpoint.get("summary") or "").strip()
            if not summary:
                continue
            label = str(checkpoint.get("label") or "").strip() or "Checkpoint"
            source_node_id = str(checkpoint.get("source_node_id") or "").strip()
            source_title = ""
            if source_node_id:
                source = node_index.get(source_node_id)
                if isinstance(source, dict):
                    source_title = str(source.get("title") or "").strip()
            title_suffix = f" ({source_title})" if source_title else ""
            checkpoint_lines.append(f"- {label}{title_suffix}: {summary}")
    if checkpoint_lines:
        sections.append("Accepted checkpoints:\n" + "\n".join(checkpoint_lines))
    else:
        sections.append("Accepted checkpoints:\n- none")

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
