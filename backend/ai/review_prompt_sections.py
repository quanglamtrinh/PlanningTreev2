from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.services import planningtree_workspace
from backend.services.node_detail_service import _load_frame_meta_from_node_dir

_FRAME_CHAR_LIMIT = 4000
_CHECKPOINT_CHAR_LIMIT = 800


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def resolve_node_dir(snapshot: dict[str, Any], node_id: str) -> Path | None:
    project = snapshot.get("project", {})
    workspace_root = str(project.get("project_path") or "").strip()
    if not workspace_root:
        return None
    return planningtree_workspace.resolve_node_dir(Path(workspace_root), snapshot, node_id)


def load_confirmed_frame_content(node_dir: Path | None) -> str:
    if node_dir is None:
        return ""
    frame_meta = _load_frame_meta_from_node_dir(node_dir)
    confirmed_revision = int(frame_meta.get("confirmed_revision", 0) or 0)
    if confirmed_revision < 1:
        return ""
    confirmed_content = str(frame_meta.get("confirmed_content") or "").strip()
    if confirmed_content:
        return confirmed_content
    frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
    if not frame_path.exists():
        return ""
    return frame_path.read_text(encoding="utf-8").strip()


def render_markdown_section(label: str, content: str, limit: int) -> str:
    return f"{label}:\n```markdown\n{truncate(content, limit)}\n```"


def render_parent_task_summary(title: str, description: str) -> str | None:
    cleaned_title = str(title or "").strip()
    cleaned_description = str(description or "").strip()
    if not cleaned_title and not cleaned_description:
        return None
    lines: list[str] = []
    if cleaned_title:
        lines.append(f"Parent task: {cleaned_title}")
    if cleaned_description:
        lines.append(f"Description: {cleaned_description}")
    return "\n".join(lines)


def render_parent_task_context(title: str, description: str) -> str | None:
    cleaned_title = str(title or "").strip()
    cleaned_description = str(description or "").strip()
    if not cleaned_title and not cleaned_description:
        return None
    lines = ["Parent task context:"]
    if cleaned_title:
        lines.append(f"- Title: {cleaned_title}")
    if cleaned_description:
        lines.append(f"- Description: {cleaned_description}")
    return "\n".join(lines)


def render_confirmed_parent_frame_section(node_dir: Path | None) -> str | None:
    frame_content = load_confirmed_frame_content(node_dir)
    if not frame_content:
        return None
    return render_markdown_section("Confirmed parent frame", frame_content, _FRAME_CHAR_LIMIT)


def render_split_package_section(
    manifest: list[dict[str, Any]] | None,
    *,
    include_none: bool = False,
) -> str | None:
    if not isinstance(manifest, list) or not manifest:
        return "Split package:\n- none" if include_none else None
    lines = ["Split package:"]
    for item in manifest:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        status = str(item.get("status") or "").strip() or "unknown"
        child_title = str(item.get("title") or "").strip() or "Untitled"
        objective = str(item.get("objective") or "").strip()
        checkpoint_label = str(item.get("checkpoint_label") or "").strip()
        summary = f"- [{index}] {child_title} ({status})"
        if objective:
            summary = f"{summary}: {objective}"
        if checkpoint_label:
            summary = f"{summary} [{checkpoint_label}]"
        lines.append(summary)
    return "\n".join(lines)


def render_accepted_checkpoint_section(
    review_state: dict[str, Any],
    node_index: dict[str, Any],
) -> str:
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
            checkpoint_lines.append(
                f"- {label}{title_suffix}: {truncate(summary, _CHECKPOINT_CHAR_LIMIT)}"
            )
    if checkpoint_lines:
        return "Accepted checkpoints:\n" + "\n".join(checkpoint_lines)
    return "Accepted checkpoints:\n- none"


def render_json_summary_contract() -> str:
    return (
        "Respond with valid JSON in exactly this shape:\n"
        '```json\n{"summary": "Concise integration rollup summary."}\n```'
    )
