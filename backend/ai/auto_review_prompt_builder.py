from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from backend.ai.review_prompt_sections import (
    load_confirmed_frame_content,
    render_markdown_section,
    resolve_node_dir,
    truncate,
)
from backend.services.node_detail_service import _load_spec_meta_from_node_dir
from backend.services import planningtree_workspace
from backend.storage.storage import Storage

_DIFF_CHAR_LIMIT = 12000
_SPEC_CHAR_LIMIT = 4000
_FRAME_CHAR_LIMIT = 4000

_BASE_INSTRUCTIONS = """You are performing an automated local code review for PlanningTree.
This is an automated, read-only analysis run in the task node's audit thread.

Rules:
1. Evaluate the implementation against the confirmed spec.
2. Evaluate code quality, correctness, completeness, and potential issues.
3. You may inspect the workspace or repository for implementation details.
4. Do not mutate files or propose write actions in this run.
5. Return ONLY valid JSON matching the required output schema.
6. Be concise and specific. Cite file paths and line references where possible.
"""

_AUTO_REVIEW_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "checkpoint_summary", "overall_severity", "overall_score", "findings"],
    "properties": {
        "summary": {
            "type": "string",
            "minLength": 1,
            "description": "Detailed review summary (2-4 sentences).",
        },
        "checkpoint_summary": {
            "type": "string",
            "minLength": 1,
            "description": "One-sentence compact summary for checkpoint record.",
        },
        "overall_severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low", "info"],
            "description": "Highest severity across all findings, or 'info' if no issues.",
        },
        "overall_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Quality score: 90-100 excellent, 70-89 good, 50-69 fair, below 50 poor.",
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "severity",
                    "description",
                    "file_path",
                    "evidence",
                    "suggested_followup",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                    },
                    "description": {"type": "string"},
                    "file_path": {
                        "type": "string",
                        "description": "Workspace-relative file path, or empty string if not applicable.",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "Brief evidence or line reference, or empty string if unavailable.",
                    },
                    "suggested_followup": {
                        "type": "string",
                        "description": "Suggested next step, or empty string if none.",
                    },
                },
            },
        },
    },
}

_OUTPUT_CONTRACT = (
    "Respond with valid JSON in exactly this shape:\n"
    "```json\n"
    '{"summary": "...", "checkpoint_summary": "...", '
    '"overall_severity": "info|low|medium|high|critical", '
    '"overall_score": 0-100, '
    '"findings": [{"title": "...", "severity": "...", "description": "...", '
    '"file_path": "...", "evidence": "...", "suggested_followup": "..."}]}\n'
    "```\n"
    "overall_severity must equal the highest severity across all findings, or 'info' if none.\n"
    "checkpoint_summary must be a single concise sentence suitable for a checkpoint record.\n"
    "Each finding object must include all keys shown above. Use empty strings for file_path, evidence, or "
    "suggested_followup when those details are not available.\n"
    "findings may be an empty array if there are no issues."
)


def build_auto_review_base_instructions() -> str:
    return _BASE_INSTRUCTIONS


def build_auto_review_output_schema() -> dict[str, object]:
    return copy.deepcopy(_AUTO_REVIEW_OUTPUT_SCHEMA)


def build_auto_review_prompt(
    storage: Storage,
    project_id: str,
    node_id: str,
    workspace_root: str | None,
    git_checkpoint_service: Any | None,
) -> str:
    with storage.project_lock(project_id):
        snapshot = storage.project_store.load_snapshot(project_id)
        node_by_id = snapshot.get("tree_state", {}).get("node_index", {})
        if not isinstance(node_by_id, dict):
            node_by_id = {}
        node = node_by_id.get(node_id)
        if not isinstance(node, dict):
            raise ValueError(f"Node {node_id!r} not found in project {project_id!r}.")
        node_dir = resolve_node_dir(snapshot, node_id)
        exec_state = storage.workflow_domain_store.read_execution(project_id, node_id)

    sections: list[str] = []

    title = str(node.get("title") or "").strip()
    description = str(node.get("description") or "").strip()
    if title or description:
        lines = []
        if title:
            lines.append(f"Task: {title}")
        if description:
            lines.append(f"Description: {description}")
        sections.append("\n".join(lines))

    frame_content = load_confirmed_frame_content(node_dir)
    if frame_content:
        sections.append(render_markdown_section("Confirmed frame", frame_content, _FRAME_CHAR_LIMIT))

    spec_content = _load_confirmed_spec_content(node_dir)
    if spec_content:
        sections.append(render_markdown_section("Confirmed spec", spec_content, _SPEC_CHAR_LIMIT))

    if isinstance(exec_state, dict):
        meta_lines = ["Execution metadata:"]
        initial_sha = str(exec_state.get("initial_sha") or "").strip()
        head_sha = str(exec_state.get("head_sha") or "").strip()
        commit_message = str(exec_state.get("commit_message") or "").strip()
        if initial_sha:
            meta_lines.append(f"- Initial SHA: {initial_sha}")
        if head_sha:
            meta_lines.append(f"- Head SHA: {head_sha}")
        if commit_message:
            meta_lines.append(f"- Commit: {commit_message}")
        if len(meta_lines) > 1:
            sections.append("\n".join(meta_lines))

        diff_section = _build_code_diff_section(workspace_root, exec_state, git_checkpoint_service)
        if diff_section:
            sections.append(diff_section)

    sections.append(_OUTPUT_CONTRACT)
    return "\n\n".join(s for s in sections if s.strip())


def extract_auto_review_result(text: str) -> dict[str, Any] | None:
    payload = _extract_json_object(text)
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    checkpoint_summary = payload.get("checkpoint_summary")
    overall_severity = payload.get("overall_severity")
    overall_score = payload.get("overall_score")
    findings = payload.get("findings")

    if not isinstance(summary, str) or not summary.strip():
        return None
    if not isinstance(checkpoint_summary, str) or not checkpoint_summary.strip():
        return None
    valid_severities = {"critical", "high", "medium", "low", "info"}
    if overall_severity not in valid_severities:
        return None
    if not isinstance(overall_score, int) or not (0 <= overall_score <= 100):
        return None
    if not isinstance(findings, list):
        return None

    cleaned_findings: list[dict[str, Any]] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        f_title = str(f.get("title") or "").strip()
        f_severity = f.get("severity")
        f_description = str(f.get("description") or "").strip()
        if not f_title or f_severity not in valid_severities or not f_description:
            continue
        entry: dict[str, Any] = {
            "title": f_title,
            "severity": f_severity,
            "description": f_description,
        }
        for opt in ("file_path", "evidence", "suggested_followup"):
            val = str(f.get(opt) or "").strip()
            if val:
                entry[opt] = val
        cleaned_findings.append(entry)

    return {
        "summary": summary.strip(),
        "checkpoint_summary": checkpoint_summary.strip(),
        "overall_severity": overall_severity,
        "overall_score": overall_score,
        "findings": cleaned_findings,
    }


def _build_code_diff_section(
    workspace_root: str | None,
    exec_state: dict[str, Any],
    git_checkpoint_service: Any | None,
) -> str:
    initial_sha = str(exec_state.get("initial_sha") or "").strip()
    head_sha = str(exec_state.get("head_sha") or "").strip()
    changed_files: list[dict[str, Any]] = exec_state.get("changed_files") or []
    commit_message = str(exec_state.get("commit_message") or "").strip()

    if not initial_sha and not head_sha and not changed_files and not commit_message:
        return ""

    if initial_sha == head_sha or (not changed_files and not commit_message):
        return "Code changes:\nNo files were changed during this execution."

    if (
        git_checkpoint_service is not None
        and git_checkpoint_service.is_git_commit_sha(initial_sha)
        and git_checkpoint_service.is_git_commit_sha(head_sha)
        and workspace_root
    ):
        try:
            diff_output = git_checkpoint_service.get_diff(Path(workspace_root), initial_sha, head_sha)
            if diff_output and diff_output.strip():
                short_from = initial_sha[:8]
                short_to = head_sha[:8]
                return (
                    f"Code diff ({short_from}..{short_to}):\n"
                    f"```diff\n{truncate(diff_output, _DIFF_CHAR_LIMIT)}\n```"
                )
        except Exception:
            pass

    if changed_files:
        lines = ["Changed files:"]
        for f in changed_files:
            if isinstance(f, dict):
                lines.append(f"- {f.get('status', '?')} {f.get('path', '?')}")
        lines.append("\nInspect these files in the workspace to review the implementation.")
        return "\n".join(lines)

    return "Code changes:\nUnable to determine specific changes. Inspect the workspace against the spec."


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
