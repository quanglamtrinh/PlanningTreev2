from __future__ import annotations

import time
from pathlib import Path

from backend.services import planningtree_workspace
from backend.services.split_service import SplitService
from backend.services.thread_lineage_service import ThreadLineageService


class FakeCodexClient:
    def __init__(self) -> None:
        self.started_threads: list[str] = []
        self.forked_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(source_thread_id)
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
                                {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                                {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                            ]
                        },
                    },
                }
            ],
        }


def wait_for_terminal_status(client, project_id: str, timeout_sec: float = 2.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        response = client.get(f"/v3/projects/{project_id}/split-status")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] != "active":
            return payload
        time.sleep(0.02)
    raise AssertionError("split api job did not finish in time")


def make_node_split_ready(client, project_id: str, node_id: str, title: str) -> None:
    frame_response = client.put(
        f"/v3/projects/{project_id}/nodes/{node_id}/documents/frame",
        json={
            "content": (
                f"# Task Title\n{title}\n\n"
                "# Task-Shaping Fields\n"
                "- target platform: web\n"
            )
        },
    )
    assert frame_response.status_code == 200
    confirm_response = client.post(f"/v3/projects/{project_id}/nodes/{node_id}/confirm-frame")
    assert confirm_response.status_code == 200
    assert confirm_response.json()["active_step"] == "spec"


def test_split_api_accepts_jobs_and_updates_snapshot(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    project_dir = workspace_root / ".planningtree"

    created = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]
    make_node_split_ready(client, project_id, root_id, title=workspace_root.name)

    codex_client = FakeCodexClient()
    client.app.state.split_service = SplitService(
        storage=client.app.state.storage,
        tree_service=client.app.state.tree_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(
            client.app.state.storage,
            codex_client,
            client.app.state.tree_service,
        ),
        split_timeout=5,
    )

    response = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": "workflow"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"

    terminal = wait_for_terminal_status(client, project_id)
    assert terminal["status"] == "idle"

    snapshot = client.get(f"/v3/projects/{project_id}/snapshot")
    assert snapshot.status_code == 200
    payload = snapshot.json()
    root = next(node for node in payload["tree_state"]["node_registry"] if node["node_id"] == root_id)
    root_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace"
    first_child_dir = root_dir / "1.1 Prep"
    assert len(root["child_ids"]) == 1
    assert first_child_dir.is_dir()
    assert (first_child_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    review_node_id = root["review_node_id"]
    review_node = next(node for node in payload["tree_state"]["node_registry"] if node["node_id"] == review_node_id)
    assert review_node["node_kind"] == "review"


def test_split_api_rejects_nodes_that_are_not_workflow_ready(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    created = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]

    codex_client = FakeCodexClient()
    client.app.state.split_service = SplitService(
        storage=client.app.state.storage,
        tree_service=client.app.state.tree_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(
            client.app.state.storage,
            codex_client,
            client.app.state.tree_service,
        ),
        split_timeout=5,
    )

    response = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": "workflow"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "split_not_allowed"


def test_snapshot_includes_node_workflow_summary(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    created = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]
    make_node_split_ready(client, project_id, root_id, title=workspace_root.name)

    snapshot = client.get(f"/v3/projects/{project_id}/snapshot")
    assert snapshot.status_code == 200
    payload = snapshot.json()
    root = next(node for node in payload["tree_state"]["node_registry"] if node["node_id"] == root_id)

    assert root["workflow"]["frame_confirmed"] is True
    assert root["workflow"]["active_step"] == "spec"
    assert root["workflow"]["spec_confirmed"] is False
    assert root["workflow"]["execution_started"] is False
    assert root["workflow"]["execution_completed"] is False
    assert root["workflow"]["shaping_frozen"] is False


def test_legacy_planning_routes_remain_absent_after_split_rebuild(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    created = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]

    history_response = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/planning/history")
    events_response = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/planning/events")

    assert history_response.status_code == 404
    assert events_response.status_code == 404
