from __future__ import annotations

import threading
import time
from pathlib import Path

from backend.services.split_service import SplitService
from backend.services.thread_lineage_service import ThreadLineageService


class FakeCodexClient:
    def start_thread(self, **_: object) -> dict[str, str]:
        return {"thread_id": "thread-1"}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": f"fork-{source_thread_id}"}

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


class FinishTaskCodexClient:
    def start_thread(self, **_: object) -> dict[str, str]:
        return {"thread_id": "exec-thread-1"}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def run_turn_streaming(self, *_: object, **__: object) -> dict[str, str]:
        return {"stdout": "Execution complete", "thread_id": "exec-thread-1"}


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
    _prepare_finishable_task(client, project_id, root_id)

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


def _prepare_finishable_task(client, project_id: str, root_id: str) -> None:
    frame_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame",
        json={"content": "# Task Title\nTask\n\n# Objective\nDo it\n"},
    )
    assert frame_resp.status_code == 200
    assert client.post(f"/v1/projects/{project_id}/nodes/{root_id}/confirm-frame").status_code == 200

    spec_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/spec",
        json={"content": "# Spec\nImplement it\n"},
    )
    assert spec_resp.status_code == 200
    assert client.post(f"/v1/projects/{project_id}/nodes/{root_id}/confirm-spec").status_code == 200

    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["status"] = "ready"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)


def test_frozen_frame_and_spec_saves_do_not_mutate_files(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    attached = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert attached.status_code == 200
    payload = attached.json()
    project_id = payload["project"]["id"]
    root_id = payload["tree_state"]["root_node_id"]

    initial_frame = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame",
        json={"content": "# Original Frame\n"},
    )
    assert initial_frame.status_code == 200
    initial_spec = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/spec",
        json={"content": "# Original Spec\n"},
    )
    assert initial_spec.status_code == 200

    client.app.state.storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "executing",
            "initial_sha": "sha256:abc",
            "head_sha": None,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None,
        },
    )

    frame_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame",
        json={"content": "# New Frame\n"},
    )
    assert frame_resp.status_code == 409
    assert frame_resp.json()["code"] == "shaping_frozen"
    refreshed_frame = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame")
    assert refreshed_frame.status_code == 200
    assert refreshed_frame.json()["content"] == "# Original Frame\n"

    spec_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/spec",
        json={"content": "# New Spec\n"},
    )
    assert spec_resp.status_code == 409
    assert spec_resp.json()["code"] == "shaping_frozen"
    refreshed_spec = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/documents/spec")
    assert refreshed_spec.status_code == 200
    assert refreshed_spec.json()["content"] == "# Original Spec\n"


def test_frame_save_is_atomic_against_concurrent_finish_task(client, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    attached = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert attached.status_code == 200
    payload = attached.json()
    project_id = payload["project"]["id"]
    root_id = payload["tree_state"]["root_node_id"]
    _prepare_finishable_task(client, project_id, root_id)
    finish_codex_client = FinishTaskCodexClient()
    client.app.state.finish_task_service._codex_client = finish_codex_client
    client.app.state.thread_lineage_service._codex_client = finish_codex_client

    original_bump = client.app.state.node_detail_service.bump_frame_revision
    entered_bump = threading.Event()
    release_bump = threading.Event()

    def blocking_bump(project_id_arg: str, node_id_arg: str) -> None:
        entered_bump.set()
        assert release_bump.wait(timeout=2.0), "finish-task race guard timed out"
        original_bump(project_id_arg, node_id_arg)

    client.app.state.node_detail_service.bump_frame_revision = blocking_bump

    put_result: dict[str, object] = {}
    finish_result: dict[str, object] = {}

    def do_put() -> None:
        put_result["response"] = client.put(
            f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame",
            json={"content": "# Task Title\nTask updated\n\n# Objective\nDo it now\n"},
        )

    def do_finish() -> None:
        finish_result["response"] = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/finish-task")

    put_thread = threading.Thread(target=do_put, daemon=True)
    finish_thread = threading.Thread(target=do_finish, daemon=True)

    put_thread.start()
    assert entered_bump.wait(timeout=2.0), "frame save never reached bump_frame_revision"

    finish_thread.start()
    time.sleep(0.1)
    assert finish_thread.is_alive(), "finish-task should block until frame save finishes"

    release_bump.set()
    put_thread.join(timeout=2.0)
    finish_thread.join(timeout=2.0)
    client.app.state.node_detail_service.bump_frame_revision = original_bump

    assert "response" in put_result
    assert "response" in finish_result
    assert put_result["response"].status_code == 200
    assert finish_result["response"].status_code == 400

    frame_resp = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame")
    assert frame_resp.status_code == 200
    assert frame_resp.json()["content"] == "# Task Title\nTask updated\n\n# Objective\nDo it now\n"

    detail_resp = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/detail-state")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["frame_revision"] >= 2
    assert detail["execution_started"] is False
