from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.ai.review_prompt_sections import (
    load_confirmed_frame_content,
    render_confirmed_parent_frame_section,
    render_markdown_section,
    render_parent_task_summary,
    render_split_package_section,
    resolve_node_dir,
    truncate,
)
from backend.ai.split_context_builder import (
    _build_parent_chain_prompts,
    _build_prior_node_summaries_compact,
)
from backend.services import planningtree_workspace
from backend.services.node_detail_service import _load_spec_meta_from_node_dir
from backend.services.review_sibling_manifest import derive_review_sibling_manifest
from backend.storage.storage import Storage

_PROJECT_CHAR_LIMIT = 200
_NODE_CHAR_LIMIT = 500
_ANCESTOR_CHAR_LIMIT = 300
_MAX_ANCESTORS = 6
_SIBLING_CHAR_LIMIT = 200
_MAX_SIBLINGS = 5
_FRAME_CHAR_LIMIT = 4000
_SPEC_CHAR_LIMIT = 4000
_CHECKPOINT_CHAR_LIMIT = 800


def _truncate(text: str, limit: int) -> str:
    return truncate(text, limit)


def build_chat_prompt(
    snapshot: dict[str, Any],
    node: dict[str, Any] | None,
    node_by_id: dict[str, dict[str, Any]],
    user_content: str,
) -> str:
    parts: list[str] = []

    project = snapshot.get("project", {})
    project_name = str(project.get("name", "")).strip()
    root_goal = str(project.get("root_goal", "")).strip()
    if project_name or root_goal:
        project_line = f"Project: {project_name}" if project_name else ""
        if root_goal:
            project_line = f"{project_line}\nRoot goal: {root_goal}" if project_line else f"Root goal: {root_goal}"
        parts.append(_truncate(project_line, _PROJECT_CHAR_LIMIT))

    if node is not None:
        title = str(node.get("title", "")).strip()
        description = str(node.get("description", "")).strip()
        node_text = ""
        if title:
            node_text = f"Current task: {title}"
        if description:
            node_text = f"{node_text}\nDescription: {description}" if node_text else f"Description: {description}"
        if node_text:
            parts.append(_truncate(node_text, _NODE_CHAR_LIMIT))

        ancestors = _build_parent_chain_prompts(node, node_by_id)
        if len(ancestors) > _MAX_ANCESTORS:
            ancestors = [ancestors[0], *ancestors[-(_MAX_ANCESTORS - 1):]]
        if ancestors:
            ancestor_lines = [
                _truncate(f"  - {a}", _ANCESTOR_CHAR_LIMIT) for a in ancestors
            ]
            parts.append("Ancestors:\n" + "\n".join(ancestor_lines))

        siblings = _build_prior_node_summaries_compact(node, node_by_id)
        siblings = siblings[-_MAX_SIBLINGS:]
        if siblings:
            sibling_lines = [
                _truncate(f"  - {s['title']}: {s['description']}", _SIBLING_CHAR_LIMIT)
                for s in siblings
            ]
            parts.append("Completed siblings:\n" + "\n".join(sibling_lines))

    hidden_context = "\n\n".join(parts)
    if hidden_context:
        return f"{hidden_context}\n\n---\n\nUser message:\n{user_content}"
    return user_content


def build_local_review_prompt(
    storage: Storage,
    project_id: str,
    node_id: str,
    user_content: str,
) -> str:
    with storage.project_lock(project_id):
        snapshot, node, _ = _load_snapshot_and_node_locked(storage, project_id, node_id)
        node_dir = resolve_node_dir(snapshot, node_id)
        execution_state = storage.workflow_domain_store.read_execution(project_id, node_id)

    sections: list[str] = []
    title = str(node.get("title") or "").strip()
    description = str(node.get("description") or "").strip()
    if title or description:
        lines = []
        if title:
            lines.append(f"Current task: {title}")
        if description:
            lines.append(f"Description: {description}")
        sections.append("\n".join(lines))

    frame_content = load_confirmed_frame_content(node_dir)
    if frame_content:
        sections.append(render_markdown_section("Confirmed frame", frame_content, _FRAME_CHAR_LIMIT))

    spec_content = _load_confirmed_spec_content(node_dir)
    if spec_content:
        sections.append(render_markdown_section("Confirmed spec", spec_content, _SPEC_CHAR_LIMIT))

    if isinstance(execution_state, dict):
        status = str(execution_state.get("status") or "").strip()
        head_sha = str(execution_state.get("head_sha") or "").strip()
        started_at = str(execution_state.get("started_at") or "").strip()
        completed_at = str(execution_state.get("completed_at") or "").strip()
        lines = ["Execution state:"]
        if status:
            lines.append(f"- Status: {status}")
        if head_sha:
            lines.append(f"- Head SHA: {head_sha}")
        if started_at:
            lines.append(f"- Started at: {started_at}")
        if completed_at:
            lines.append(f"- Completed at: {completed_at}")
        if len(lines) > 1:
            sections.append("\n".join(lines))

    return _compose_hidden_context_prompt(sections, user_content)


def build_package_review_prompt(
    storage: Storage,
    project_id: str,
    node_id: str,
    user_content: str,
) -> str:
    with storage.project_lock(project_id):
        snapshot, node, node_by_id = _load_snapshot_and_node_locked(storage, project_id, node_id)
        review_node_id = str(node.get("review_node_id") or "").strip()
        review_node = node_by_id.get(review_node_id) if review_node_id else None
        review_state = (
            storage.workflow_domain_store.read_review(project_id, review_node_id)
            if review_node_id
            else None
        )
        manifest = (
            derive_review_sibling_manifest(snapshot, node, review_node, review_state or {})
            if isinstance(review_node, dict)
            else []
        )
        node_dir = resolve_node_dir(snapshot, node_id)

    sections: list[str] = []
    parent_summary = render_parent_task_summary(
        str(node.get("title") or ""),
        str(node.get("description") or ""),
    )
    if parent_summary:
        sections.append(parent_summary)

    parent_frame = render_confirmed_parent_frame_section(node_dir)
    if parent_frame:
        sections.append(parent_frame)

    split_package = render_split_package_section(manifest)
    if split_package:
        sections.append(split_package)

    if isinstance(review_state, dict):
        rollup = review_state.get("rollup", {})
        if isinstance(rollup, dict):
            draft = rollup.get("draft", {})
            status = str(rollup.get("status") or "").strip()
            summary = str(rollup.get("summary") or "").strip()
            sha = str(rollup.get("sha") or "").strip()
            if not summary and isinstance(draft, dict):
                summary = str(draft.get("summary") or "").strip()
                sha = sha or str(draft.get("sha") or "").strip()
            lines = ["Rollup result:"]
            if status:
                lines.append(f"- Status: {status}")
            if summary:
                lines.append(f"- Summary: {_truncate(summary, 1200)}")
            if sha:
                lines.append(f"- SHA: {sha}")
            if len(lines) > 1:
                sections.append("\n".join(lines))

    return _compose_hidden_context_prompt(sections, user_content)


def build_child_activation_prompt(
    storage: Storage,
    project_id: str,
    node_id: str,
    review_node_id: str,
    user_content: str,
) -> str:
    with storage.project_lock(project_id):
        snapshot, node, node_by_id = _load_snapshot_and_node_locked(storage, project_id, node_id)
        review_node = node_by_id.get(review_node_id)
        review_state = storage.workflow_domain_store.read_review(project_id, review_node_id)
        parent_id = str(node.get("parent_id") or "").strip()
        parent = node_by_id.get(parent_id) if parent_id else None
        manifest = (
            derive_review_sibling_manifest(snapshot, parent, review_node, review_state or {})
            if isinstance(parent, dict) and isinstance(review_node, dict)
            else []
        )

    sections: list[str] = []
    title = str(node.get("title") or "").strip()
    description = str(node.get("description") or "").strip()
    if title or description:
        lines = []
        if title:
            lines.append(f"Activated child task: {title}")
        if description:
            lines.append(f"Current description: {description}")
        sections.append("\n".join(lines))

    current_index = _child_manifest_index(node)
    current_entry = None
    for item in manifest:
        if str(item.get("materialized_node_id") or "").strip() == node_id:
            current_entry = item
            break
        try:
            if int(item.get("index") or 0) == current_index:
                current_entry = item
        except (TypeError, ValueError):
            continue
    if isinstance(current_entry, dict):
        lines = ["Child activation context:"]
        child_title = str(current_entry.get("title") or "").strip()
        objective = str(current_entry.get("objective") or "").strip()
        if child_title:
            lines.append(f"- Assignment: {child_title}")
        if objective:
            lines.append(f"- Objective: {objective}")
        sections.append("\n".join(lines))

    prior_checkpoint_lines: list[str] = []
    if isinstance(review_state, dict):
        checkpoints = review_state.get("checkpoints", [])
        if isinstance(checkpoints, list):
            for checkpoint in checkpoints:
                if not isinstance(checkpoint, dict):
                    continue
                summary = str(checkpoint.get("summary") or "").strip()
                if not summary:
                    continue
                source_node_id = str(checkpoint.get("source_node_id") or "").strip()
                source_node = node_by_id.get(source_node_id) if source_node_id else None
                source_index = _child_manifest_index(source_node) if isinstance(source_node, dict) else None
                if source_index is None or source_index >= current_index:
                    continue
                label = str(checkpoint.get("label") or "").strip() or "Checkpoint"
                source_title = str(source_node.get("title") or "").strip() if isinstance(source_node, dict) else ""
                title_suffix = f" ({source_title})" if source_title else ""
                prior_checkpoint_lines.append(
                    f"- {label}{title_suffix}: {_truncate(summary, _CHECKPOINT_CHAR_LIMIT)}"
                )
    if prior_checkpoint_lines:
        sections.append("Prior accepted checkpoints:\n" + "\n".join(prior_checkpoint_lines))

    return _compose_hidden_context_prompt(sections, user_content)


def _load_snapshot_and_node_locked(
    storage: Storage,
    project_id: str,
    node_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    snapshot = storage.project_store.load_snapshot(project_id)
    node_by_id = snapshot.get("tree_state", {}).get("node_index", {})
    if not isinstance(node_by_id, dict):
        node_by_id = {}
    node = node_by_id.get(node_id)
    if not isinstance(node, dict):
        raise ValueError(f"Node {node_id!r} was not found in project {project_id!r}.")
    return snapshot, node, node_by_id


def _load_confirmed_spec_content(node_dir: Path | None) -> str:
    if node_dir is None:
        return ""
    spec_meta = _load_spec_meta_from_node_dir(node_dir)
    if not str(spec_meta.get("confirmed_at") or "").strip():
        return ""
    spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
    if not spec_path.exists():
        return ""
    return spec_path.read_text(encoding="utf-8").strip()


def _compose_hidden_context_prompt(sections: list[str], user_content: str) -> str:
    hidden_context = "\n\n".join(section for section in sections if section.strip())
    if hidden_context:
        return f"{hidden_context}\n\n---\n\nUser message:\n{user_content}"
    return user_content


def _child_manifest_index(node: dict[str, Any] | None) -> int | None:
    if not isinstance(node, dict):
        return None
    try:
        return int(node.get("display_order", 0) or 0) + 1
    except (TypeError, ValueError):
        return None
