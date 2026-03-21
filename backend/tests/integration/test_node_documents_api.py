from __future__ import annotations

import time
from pathlib import Path

from backend.services.split_service import SplitService


class FakeCodexClient:
    def start_thread(self, **_: object) -> dict[str, str]:
        return {"thread_id": "thread-1"}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def run_turn_streaming(self, *_: object, **__: object) -> dict:
        return {
            "stdout": "ok",
            "tool_calls": [
                {
                    "tool_name": "emit_render_data",
                    "arguments": {
                        "kind": "split_result",
                        "payload": {
                            "subtasks": [
                                {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts."},
                                {"id": "S2", "title": "Finish", "objective": "Finish the flow.", "why_now": "It follows."},
                            ]
                        },
                    },
                }
            ],
        }


def wait_for_terminal_status(client, project_id: str, timeout_sec: float = 2.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        response = client.get(f"/v1/projects/{project_id}/split-status")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] != "active":
            return payload
        time.sleep(0.02)
    raise AssertionError("split api job did not finish in time")


def test_root_documents_can_be_read_and_written(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    attached = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert attached.status_code == 200
    payload = attached.json()
    project_id = payload["project"]["id"]
    root_id = payload["tree_state"]["root_node_id"]

    frame = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame")
    spec = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/documents/spec")
    assert frame.status_code == 200
    assert spec.status_code == 200
    assert frame.json()["content"] == ""
    assert spec.json()["content"] == ""

    updated = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame",
        json={"content": "# Root frame"},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "# Root frame"

    refreshed = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame")
    assert refreshed.status_code == 200
    assert refreshed.json()["content"] == "# Root frame"


def test_child_document_endpoints_work_immediately_after_create_child(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    attached = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    project_id = attached.json()["project"]["id"]
    root_id = attached.json()["tree_state"]["root_node_id"]

    created = client.post(f"/v1/projects/{project_id}/nodes", json={"parent_id": root_id})
    assert created.status_code == 200
    child_id = created.json()["tree_state"]["active_node_id"]

    response = client.get(f"/v1/projects/{project_id}/nodes/{child_id}/documents/spec")
    assert response.status_code == 200
    assert response.json()["content"] == ""


def test_split_created_child_document_endpoints_work(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    attached = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    project_id = attached.json()["project"]["id"]
    root_id = attached.json()["tree_state"]["root_node_id"]

    client.app.state.split_service = SplitService(
        storage=client.app.state.storage,
        tree_service=client.app.state.tree_service,
        codex_client=FakeCodexClient(),
        split_timeout=5,
    )

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": "workflow"},
    )
    assert response.status_code == 202

    terminal = wait_for_terminal_status(client, project_id)
    assert terminal["status"] == "idle"

    snapshot = client.get(f"/v1/projects/{project_id}/snapshot")
    assert snapshot.status_code == 200
    root = next(
        node for node in snapshot.json()["tree_state"]["node_registry"] if node["node_id"] == root_id
    )
    child_id = root["child_ids"][0]

    child_frame = client.get(f"/v1/projects/{project_id}/nodes/{child_id}/documents/frame")
    assert child_frame.status_code == 200
    assert child_frame.json()["content"] == ""
