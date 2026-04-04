from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.workflow_artifact_write_guard import (
    ALLOWED_WORKFLOW_ARTIFACT_FILE_NAMES,
    ensure_allowed_workflow_artifact_write,
)


def test_allows_known_artifact_file_names(tmp_path: Path) -> None:
    node_dir = tmp_path / "node-1"
    node_dir.mkdir(parents=True, exist_ok=True)

    for file_name in ALLOWED_WORKFLOW_ARTIFACT_FILE_NAMES:
        resolved = ensure_allowed_workflow_artifact_write(node_dir, node_dir / file_name)
        assert resolved == (node_dir / file_name).resolve()


def test_rejects_write_outside_node_dir(tmp_path: Path) -> None:
    node_dir = tmp_path / "node-1"
    node_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "frame.md"

    with pytest.raises(ValueError, match="must target direct files under the node directory"):
        ensure_allowed_workflow_artifact_write(node_dir, outside)


def test_rejects_non_allowlisted_file_name(tmp_path: Path) -> None:
    node_dir = tmp_path / "node-1"
    node_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="outside allowlist"):
        ensure_allowed_workflow_artifact_write(node_dir, node_dir / "notes.txt")
