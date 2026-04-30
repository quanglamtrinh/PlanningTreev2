from __future__ import annotations

import json

from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.state_machine import complete_execution, start_execution
from backend.services.project_service import ProjectService


def _project_id(storage, workspace_root) -> str:
    return ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]


def test_read_state_returns_default_without_writing(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    repository = WorkflowStateRepositoryV2(storage)

    state = repository.read_state(project_id, "node-1")

    assert state.project_id == project_id
    assert state.node_id == "node-1"
    assert state.phase == "ready_for_execution"
    assert not repository.canonical_path(project_id, "node-1").exists()


def test_write_state_uses_canonical_path_and_increments_version(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    repository = WorkflowStateRepositoryV2(storage)
    state = start_execution(repository.read_state(project_id, "node-1"), execution_run_id="exec-run-1")

    first = repository.write_state(project_id, "node-1", state)
    second = repository.write_state(project_id, "node-1", first)

    assert first.state_version == 1
    assert second.state_version == 2
    assert second.created_at == first.created_at
    assert second.updated_at != first.updated_at
    assert repository.canonical_path(project_id, "node-1").exists()

    raw = json.loads(repository.canonical_path(project_id, "node-1").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["state_version"] == 2
    assert raw["phase"] == "executing"
    assert "allowed_actions" not in raw
    assert "workflowPhase" not in raw
