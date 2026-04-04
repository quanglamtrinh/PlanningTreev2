from __future__ import annotations

from pathlib import Path

ALLOWED_WORKFLOW_ARTIFACT_FILE_NAMES: frozenset[str] = frozenset(
    {
        "frame.md",
        "clarify.json",
        "spec.md",
        "frame.meta.json",
        "spec.meta.json",
        "frame_gen.json",
        "clarify_gen.json",
        "spec_gen.json",
    }
)


def ensure_allowed_workflow_artifact_write(node_dir: Path, target_path: Path) -> Path:
    resolved_node_dir = Path(node_dir).expanduser().resolve()
    resolved_target = Path(target_path).expanduser().resolve()
    if resolved_target.parent != resolved_node_dir:
        raise ValueError(
            "Workflow artifact writes must target direct files under the node directory."
        )
    if resolved_target.name not in ALLOWED_WORKFLOW_ARTIFACT_FILE_NAMES:
        raise ValueError(
            f"Workflow artifact write is outside allowlist: {resolved_target.name!r}."
        )
    return resolved_target
