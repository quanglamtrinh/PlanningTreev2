from __future__ import annotations

import copy
import json

from backend.ai.review_prompt_sections import (
    render_accepted_checkpoint_section,
    render_confirmed_parent_frame_section,
    render_json_summary_contract,
    render_parent_task_context,
    render_split_package_section,
    resolve_node_dir,
)
from backend.services.review_sibling_manifest import derive_review_sibling_manifest
from backend.storage.storage import Storage

_BASE_INSTRUCTIONS = """You are performing automated integration rollup analysis for PlanningTree.
This is an automated, read-only analysis run over a review node's audit thread.

Rules:
1. Treat the storage-backed rollup context as the primary source of truth.
2. You may inspect the workspace or repository for implementation details if needed.
3. Do not mutate files or propose write actions in this run.
4. Evaluate package coherence against the parent frame and the split package.
5. Return ONLY valid JSON with exactly one key: "summary".
6. The summary must be non-empty and should concisely capture integration quality, gaps, and overall package readiness.
"""

_ROLLUP_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary"],
    "properties": {
        "summary": {
            "type": "string",
            "minLength": 1,
        }
    },
}


def build_review_rollup_base_instructions() -> str:
    return _BASE_INSTRUCTIONS


def build_review_rollup_output_schema() -> dict[str, object]:
    return copy.deepcopy(_ROLLUP_OUTPUT_SCHEMA)


def build_review_rollup_prompt(system_messages: list[dict[str, object]]) -> str:
    sections = ["Integration rollup context:"]
    for message in system_messages:
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "").strip()
        if content:
            sections.append(content)

    sections.append(render_json_summary_contract())
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
        review_state = storage.workflow_domain_store.read_review(project_id, review_node_id) or {}
        manifest = (
            derive_review_sibling_manifest(snapshot, parent, review_node, review_state)
            if isinstance(parent, dict) and isinstance(review_node, dict)
            else []
        )
        parent_node_dir = resolve_node_dir(snapshot, parent_id) if parent_id else None

    sections = ["Integration rollup context:"]

    parent_context = render_parent_task_context(
        str(parent.get("title") or ""),
        str(parent.get("description") or ""),
    )
    if parent_context:
        sections.append(parent_context)

    parent_frame = render_confirmed_parent_frame_section(parent_node_dir)
    if parent_frame:
        sections.append(parent_frame)

    sections.append(render_split_package_section(manifest, include_none=True))
    sections.append(render_accepted_checkpoint_section(review_state, node_index))
    sections.append(render_json_summary_contract())
    return "\n\n".join(sections)


def extract_review_rollup_summary(text: str) -> str | None:
    payload = _extract_json_object(text)
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    if not isinstance(summary, str):
        return None
    cleaned = summary.strip()
    return cleaned or None


def render_review_rollup_message(summary: str, sha: str) -> str:
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
