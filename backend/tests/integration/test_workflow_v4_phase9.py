from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.services.node_document_service import NodeDocumentService


def _project_with_frame(client: TestClient, workspace_root: Path, content: str = "# Task Title\nFrame v1") -> tuple[str, str]:
    snapshot = client.app.state.project_service.attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    node_id = snapshot["tree_state"]["root_node_id"]
    NodeDocumentService(client.app.state.storage).put_document(project_id, node_id, "frame", content)
    client.app.state.node_detail_service.bump_frame_revision(project_id, node_id)
    return project_id, node_id


def test_v4_artifact_state_and_frame_confirm_use_artifact_orchestrator(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_frame(client, workspace_root)

    confirm = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/artifacts/frame/confirm",
        json={"idempotencyKey": "frame-confirm:phase9"},
    )

    assert confirm.status_code == 200, confirm.json()
    payload = confirm.json()
    assert payload["confirmed"] is True
    assert payload["artifact"]["kind"] == "frame"
    assert payload["artifact"]["frameVersion"] == 1
    assert payload["detailState"]["frame_confirmed"] is True
    assert payload["workflowState"]["context"]["frameVersion"] == 1

    state = client.get(f"/v4/projects/{project_id}/nodes/{node_id}/artifacts/state")
    assert state.status_code == 200, state.json()
    assert state.json()["versions"]["confirmedFrameVersion"] == 1


def test_v4_artifact_frame_confirm_idempotent_replay_does_not_reconfirm(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_frame(client, workspace_root)

    first = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/artifacts/frame/confirm",
        json={"idempotencyKey": "frame-confirm:phase9-replay"},
    )
    replay = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/artifacts/frame/confirm",
        json={"idempotencyKey": "frame-confirm:phase9-replay"},
    )

    assert first.status_code == 200, first.json()
    assert replay.status_code == 200, replay.json()
    assert replay.json() == first.json()


def test_v4_artifact_routes_reject_idempotency_key_conflicts(
    client: TestClient,
    workspace_root: Path,
) -> None:
    project_id, node_id = _project_with_frame(client, workspace_root)

    first = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/artifacts/split/start",
        json={"idempotencyKey": "split-start:phase9-conflict", "mode": "workflow"},
    )
    conflict = client.post(
        f"/v4/projects/{project_id}/nodes/{node_id}/artifacts/split/start",
        json={"idempotencyKey": "split-start:phase9-conflict", "mode": "phase_breakdown"},
    )

    assert first.status_code in {202, 409}
    if first.status_code == 202:
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "ERR_WORKFLOW_IDEMPOTENCY_CONFLICT"
