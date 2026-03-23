from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import SplitNotAllowed
from backend.services import planningtree_workspace
from backend.services.node_detail_service import FRAME_META_FILE
from backend.services.project_service import ProjectService
from backend.services.split_service import SplitService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage


class FakeCodexClient:
    def __init__(self, payloads: list[dict] | None = None) -> None:
        self.payloads = list(payloads or [])
        self.started_threads: list[str] = []
        self.resumed_threads: list[str] = []
        self.turns_run: list[str] = []
        self.fail_resume = False

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        self.resumed_threads.append(thread_id)
        if self.fail_resume:
            raise CodexTransportError("thread not found", "not_found")
        return {"thread_id": thread_id}

    def run_turn_streaming(self, *_: object, **__: object) -> dict:
        if _:
            self.turns_run.append(str(_[0]))
        payload = self.payloads.pop(0)
        return {
            "stdout": "ok",
            "tool_calls": [
                {
                    "tool_name": "emit_render_data",
                    "arguments": {
                        "kind": "split_result",
                        "payload": payload,
                    },
                }
            ],
        }


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


def wait_for_terminal_status(service: SplitService, project_id: str, timeout_sec: float = 2.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        status = service.get_split_status(project_id)
        if status["status"] != "active":
            return status
        time.sleep(0.02)
    raise AssertionError("split job did not finish in time")


def test_split_service_creates_children_and_reuses_project_thread(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            },
            {
                "subtasks": [
                    {"id": "S1", "title": "Detail", "objective": "Detail the first child.", "why_now": "It is the next step."},
                    {"id": "S2", "title": "Polish", "objective": "Polish the child.", "why_now": "It follows detail."},
                ]
            },
        ]
    )
    service = SplitService(storage, TreeService(), fake_client, split_timeout=5)

    accepted = service.split_node(project_id, root_id, "workflow")
    assert accepted["status"] == "accepted"
    terminal = wait_for_terminal_status(service, project_id)
    assert terminal["status"] == "idle"

    persisted = storage.project_store.load_snapshot(project_id)
    root = persisted["tree_state"]["node_index"][root_id]
    first_child_id = persisted["tree_state"]["active_node_id"]
    project_dir = storage.project_store.project_dir(project_id)
    root_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace"
    first_child_dir = root_dir / "1.1 Prep"
    second_child_dir = root_dir / "1.2 Finish"
    assert len(root["child_ids"]) == 2
    assert storage.split_state_store.path(project_id).exists()
    assert first_child_dir.is_dir()
    assert second_child_dir.is_dir()
    assert (first_child_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (second_child_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == ""
    first_thread_id = storage.split_state_store.read_state(project_id)["thread_id"]

    accepted_second = service.split_node(project_id, first_child_id, "phase_breakdown")
    assert accepted_second["status"] == "accepted"
    second_terminal = wait_for_terminal_status(service, project_id)
    assert second_terminal["status"] == "idle"
    second_thread_id = storage.split_state_store.read_state(project_id)["thread_id"]

    assert first_thread_id == second_thread_id
    assert fake_client.resumed_threads == [first_thread_id]


def test_split_service_rejects_nodes_with_existing_children(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            }
        ]
    )
    service = SplitService(storage, TreeService(), fake_client, split_timeout=5)

    service.split_node(project_id, root_id, "workflow")
    terminal = wait_for_terminal_status(service, project_id)
    assert terminal["status"] == "idle"

    with pytest.raises(SplitNotAllowed):
        service.split_node(project_id, root_id, "workflow")


def test_split_service_recreates_thread_when_resume_fails(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            },
            {
                "subtasks": [
                    {"id": "S1", "title": "Detail", "objective": "Detail the first child.", "why_now": "It is the next step."},
                    {"id": "S2", "title": "Polish", "objective": "Polish the child.", "why_now": "It follows detail."},
                ]
            },
        ]
    )
    service = SplitService(storage, TreeService(), fake_client, split_timeout=5)

    service.split_node(project_id, root_id, "workflow")
    wait_for_terminal_status(service, project_id)
    first_thread_id = storage.split_state_store.read_state(project_id)["thread_id"]

    fake_client.fail_resume = True
    current_snapshot = storage.project_store.load_snapshot(project_id)
    first_child_id = current_snapshot["tree_state"]["active_node_id"]
    service.split_node(project_id, first_child_id, "workflow")
    wait_for_terminal_status(service, project_id)
    second_thread_id = storage.split_state_store.read_state(project_id)["thread_id"]

    assert first_thread_id != second_thread_id
    assert fake_client.started_threads == ["thread-1", "thread-2"]


def test_split_service_uses_frame_context_not_spec_context(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    persisted = storage.project_store.load_snapshot(project_id)
    workspace_path = Path(str(persisted["project"]["project_path"]))
    node_dir = planningtree_workspace.resolve_node_dir(workspace_path, persisted, root_id)
    assert node_dir is not None

    (node_dir / FRAME_META_FILE).write_text(
        json.dumps(
            {
                "revision": 1,
                "confirmed_revision": 1,
                "confirmed_at": "2026-03-22T00:00:00Z",
                "confirmed_content": (
                    "# Task Title\n"
                    "Marketing Site Entry\n\n"
                    "# Task-Shaping Fields\n"
                    "- frontend stack: React + Tailwind\n"
                ),
            }
        ),
        encoding="utf-8",
    )
    (node_dir / planningtree_workspace.SPEC_FILE_NAME).write_text(
        "# Overview\nUse Vue + Bootstrap.\n",
        encoding="utf-8",
    )

    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            }
        ]
    )
    service = SplitService(storage, TreeService(), fake_client, split_timeout=5)

    service.split_node(project_id, root_id, "workflow")
    wait_for_terminal_status(service, project_id)

    prompt = fake_client.turns_run[0]
    assert "Task frame:" in prompt
    assert "React + Tailwind" in prompt
    assert "Technical spec:" not in prompt
    assert "Vue + Bootstrap" not in prompt


def test_split_status_marks_stale_jobs_as_failed(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    service = SplitService(storage, TreeService(), FakeCodexClient(), split_timeout=5)

    storage.split_state_store.write_state(
        project_id,
        {
            "thread_id": "thread-1",
            "active_job": {
                "job_id": "split_stale",
                "node_id": root_id,
                "mode": "workflow",
                "started_at": "2026-03-20T00:00:00Z",
            },
            "last_error": None,
        },
    )

    status = service.get_split_status(project_id)

    assert status["status"] == "failed"
    assert "server restarted" in str(status["error"]).lower()
