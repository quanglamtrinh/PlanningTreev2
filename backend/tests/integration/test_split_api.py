from __future__ import annotations

import time
from pathlib import Path

from backend.services.split_service import SplitService


class FakeCodexClient:
    def __init__(self) -> None:
        self.started_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

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
        response = client.get(f"/v1/projects/{project_id}/split-status")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] != "active":
            return payload
        time.sleep(0.02)
    raise AssertionError("split api job did not finish in time")


def test_split_api_accepts_jobs_and_updates_snapshot(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    client.patch("/v1/settings/workspace", json={"base_workspace_root": str(workspace_root)})
    created = client.post("/v1/projects", json={"name": "Alpha", "root_goal": "Ship split"})
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]

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
    assert response.json()["status"] == "accepted"

    terminal = wait_for_terminal_status(client, project_id)
    assert terminal["status"] == "idle"

    snapshot = client.get(f"/v1/projects/{project_id}/snapshot")
    assert snapshot.status_code == 200
    payload = snapshot.json()
    root = next(node for node in payload["tree_state"]["node_registry"] if node["node_id"] == root_id)
    assert len(root["child_ids"]) == 2


def test_legacy_planning_routes_remain_absent_after_split_rebuild(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    client.patch("/v1/settings/workspace", json={"base_workspace_root": str(workspace_root)})
    created = client.post("/v1/projects", json={"name": "Alpha", "root_goal": "Ship split"})
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]
    root_id = created.json()["tree_state"]["root_node_id"]

    history_response = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/planning/history")
    events_response = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/planning/events")

    assert history_response.status_code == 404
    assert events_response.status_code == 404
