from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.services import planningtree_workspace
from backend.services.node_detail_service import NodeDetailService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService
from backend.services.thread_lineage_service import _ROLLOUT_BOOTSTRAP_PROMPT
from backend.storage.file_utils import iso_now
from backend.tests.conftest import init_git_repo
from backend.main import create_app


class Phase5RehearsalCodexClient:
    def __init__(self) -> None:
        self.started_threads: list[str] = []
        self.forked_threads: list[dict[str, object]] = []
        self.prompts: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"phase5-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **kwargs: object) -> dict[str, str]:
        thread_id = f"phase5-fork-{len(self.forked_threads) + 1}"
        self.forked_threads.append({"thread_id": thread_id, "source_thread_id": source_thread_id, **kwargs})
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        thread_id = str(kwargs.get("thread_id") or "")
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": thread_id}

        self.prompts.append(prompt)
        on_raw_event = kwargs.get("on_raw_event")
        cwd = kwargs.get("cwd")
        output_schema = kwargs.get("output_schema")

        if output_schema is not None:
            summary = "Integrated package from rehearsal."
            if callable(on_raw_event):
                on_raw_event(
                    {
                        "method": "item/started",
                        "received_at": "2026-03-28T11:00:01Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": "rollup-msg-1",
                        "request_id": None,
                        "call_id": None,
                        "params": {"item": {"type": "agentMessage", "id": "rollup-msg-1"}},
                    }
                )
                on_raw_event(
                    {
                        "method": "item/agentMessage/delta",
                        "received_at": "2026-03-28T11:00:02Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": "rollup-msg-1",
                        "request_id": None,
                        "call_id": None,
                        "params": {"delta": f"## Rollup Summary\n\n{summary}"},
                    }
                )
                on_raw_event(
                    {
                        "method": "turn/completed",
                        "received_at": "2026-03-28T11:00:03Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": None,
                        "request_id": None,
                        "call_id": None,
                        "params": {"turn": {"status": "completed"}},
                    }
                )
            return {
                "stdout": json.dumps({"summary": summary}),
                "thread_id": thread_id,
                "turn_status": "completed",
            }

        if isinstance(cwd, str) and cwd:
            Path(cwd, "execution-output.txt").write_text("done\n", encoding="utf-8")
        if callable(on_raw_event):
            on_raw_event(
                {
                    "method": "item/started",
                    "received_at": "2026-03-28T10:00:01Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": "exec-msg-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {"item": {"type": "agentMessage", "id": "exec-msg-1"}},
                }
            )
            on_raw_event(
                {
                    "method": "item/agentMessage/delta",
                    "received_at": "2026-03-28T10:00:02Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": "exec-msg-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {"delta": "Implemented the task."},
                }
            )
            on_raw_event(
                {
                    "method": "item/tool/call",
                    "received_at": "2026-03-28T10:00:03Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": None,
                    "request_id": None,
                    "call_id": "call-1",
                    "params": {
                        "tool_name": "apply_patch",
                        "toolName": "apply_patch",
                        "arguments": {"path": "execution-output.txt"},
                    },
                }
            )
            on_raw_event(
                {
                    "method": "item/started",
                    "received_at": "2026-03-28T10:00:04Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": "file-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {
                        "item": {
                            "type": "fileChange",
                            "id": "file-1",
                            "callId": "call-1",
                            "toolName": "apply_patch",
                        }
                    },
                }
            )
            on_raw_event(
                {
                    "method": "item/fileChange/outputDelta",
                    "received_at": "2026-03-28T10:00:05Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": "file-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {
                        "delta": "preview",
                        "files": [{"path": "preview.txt", "changeType": "created", "summary": "preview"}],
                    },
                }
            )
            on_raw_event(
                {
                    "method": "item/completed",
                    "received_at": "2026-03-28T10:00:06Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": "file-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {
                        "item": {
                            "type": "fileChange",
                            "id": "file-1",
                            "changes": [{"path": "final.txt", "changeType": "updated", "summary": "final"}],
                        }
                    },
                }
            )
            on_raw_event(
                {
                    "method": "turn/completed",
                    "received_at": "2026-03-28T10:00:07Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": None,
                    "request_id": None,
                    "call_id": None,
                    "params": {"turn": {"status": "completed"}},
                }
            )
        return {"stdout": "Implemented the task.", "thread_id": thread_id, "turn_status": "completed"}


def _set_phase5_codex_client(app, codex_client: object) -> None:
    app.state.codex_client = codex_client
    app.state.chat_service._codex_client = codex_client
    app.state.thread_lineage_service._codex_client = codex_client
    app.state.thread_query_service_v2._codex_client = codex_client
    app.state.thread_runtime_service_v2._codex_client = codex_client
    app.state.finish_task_service._codex_client = codex_client
    app.state.review_service._codex_client = codex_client


def _setup_project(client: TestClient, workspace_root: Path) -> tuple[str, str]:
    response = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert response.status_code == 200
    payload = response.json()
    return payload["project"]["id"], payload["tree_state"]["root_node_id"]


def _confirm_spec(storage, project_id: str, node_id: str) -> None:
    detail_service = NodeDetailService(storage, TreeService())
    snapshot = storage.project_store.load_snapshot(project_id)
    project_path = Path(snapshot["project"]["project_path"])
    node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
    assert node_dir is not None
    frame_path = node_dir / "frame.md"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text("# Task Title\nTask\n\n# Objective\nDo it\n", encoding="utf-8")
    detail_service.confirm_frame(project_id, node_id)
    node_dir = planningtree_workspace.resolve_node_dir(project_path, storage.project_store.load_snapshot(project_id), node_id)
    assert node_dir is not None
    spec_path = node_dir / "spec.md"
    spec_path.write_text("# Spec\nImplement it\n", encoding="utf-8")
    detail_service.confirm_spec(project_id, node_id)
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, snapshot)


def _do_lazy_split(storage, project_id: str, node_id: str) -> tuple[str, str]:
    from backend.services.workspace_sha import compute_workspace_sha

    tree_service = TreeService()
    snapshot = storage.project_store.load_snapshot(project_id)
    node_by_id = tree_service.node_index(snapshot)
    parent = node_by_id[node_id]
    now = iso_now()
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)

    first_child_id = uuid4().hex
    snapshot["tree_state"]["node_index"][first_child_id] = {
        "node_id": first_child_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": "Subtask 1",
        "description": "Do subtask 1.",
        "status": "ready",
        "node_kind": "original",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.1",
        "created_at": now,
    }
    parent.setdefault("child_ids", []).append(first_child_id)

    review_node_id = uuid4().hex
    snapshot["tree_state"]["node_index"][review_node_id] = {
        "node_id": review_node_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": "Review",
        "description": f"Review node for {parent_hnum}",
        "status": "ready",
        "node_kind": "review",
        "depth": parent_depth + 1,
        "display_order": 1,
        "hierarchical_number": f"{parent_hnum}.R",
        "created_at": now,
    }
    parent["review_node_id"] = review_node_id
    if parent.get("status") in {"ready", "in_progress"}:
        parent["status"] = "draft"
    snapshot["tree_state"]["active_node_id"] = first_child_id
    snapshot["updated_at"] = now
    storage.project_store.save_snapshot(project_id, snapshot)

    workspace_root = Path(snapshot["project"]["project_path"])
    storage.review_state_store.write_state(
        project_id,
        review_node_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": compute_workspace_sha(workspace_root),
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": now,
                }
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )
    planningtree_workspace.sync_snapshot_tree(workspace_root, snapshot)
    return first_child_id, review_node_id


def _wait_for_thread_snapshot(
    client: TestClient,
    project_id: str,
    node_id: str,
    thread_role: str,
    predicate,
    *,
    timeout_sec: float = 3.0,
) -> dict:
    deadline = time.monotonic() + timeout_sec
    last_snapshot: dict | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        snapshot = payload["data"]["snapshot"]
        last_snapshot = snapshot
        if predicate(snapshot):
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for snapshot condition. Last snapshot: {last_snapshot!r}")


def test_phase5_rehearsal_finish_task_and_rollup_routes_use_v2_threads(monkeypatch, tmp_path: Path) -> None:
    rehearsal_root = tmp_path / "rehearsal-root"
    rehearsal_root.mkdir()
    workspace_root = rehearsal_root / "workspace"
    workspace_root.mkdir()
    init_git_repo(workspace_root)

    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", "1")
    monkeypatch.setenv("PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT", str(rehearsal_root))

    app = create_app(data_root=tmp_path / "appdata")
    codex_client = Phase5RehearsalCodexClient()
    _set_phase5_codex_client(app, codex_client)

    published: list[dict[str, object]] = []
    original_publish = app.state.chat_event_broker.publish

    def capture_publish(project_id_arg, node_id_arg, event, thread_role=""):
        published.append(
            {
                "project_id": project_id_arg,
                "node_id": node_id_arg,
                "thread_role": thread_role,
                "event": dict(event),
            }
        )
        return original_publish(project_id_arg, node_id_arg, event, thread_role=thread_role)

    app.state.chat_event_broker.publish = capture_publish
    workflow_events: list[tuple[str, dict[str, object]]] = []
    original_workflow_updated = app.state.workflow_event_publisher_v2.publish_workflow_updated
    original_detail_invalidate = app.state.workflow_event_publisher_v2.publish_detail_invalidate

    def capture_workflow_updated(**kwargs):
        envelope = original_workflow_updated(**kwargs)
        workflow_events.append(("updated", envelope))
        return envelope

    def capture_detail_invalidate(**kwargs):
        envelope = original_detail_invalidate(**kwargs)
        workflow_events.append(("invalidate", envelope))
        return envelope

    app.state.workflow_event_publisher_v2.publish_workflow_updated = capture_workflow_updated
    app.state.workflow_event_publisher_v2.publish_detail_invalidate = capture_detail_invalidate

    with TestClient(app) as client:
        project_id, root_id = _setup_project(client, workspace_root)
        child_id, review_node_id = _do_lazy_split(app.state.storage, project_id, root_id)
        _confirm_spec(app.state.storage, project_id, child_id)

        finish_response = client.post(f"/v1/projects/{project_id}/nodes/{child_id}/finish-task")
        assert finish_response.status_code == 200

        execution_snapshot = _wait_for_thread_snapshot(
            client,
            project_id,
            child_id,
            "execution",
            lambda snapshot: (
                snapshot.get("processingState") == "idle"
                and snapshot.get("activeTurnId") is None
                and any(item.get("kind") == "tool" for item in snapshot.get("items", []))
            ),
        )
        execution_tools = [item for item in execution_snapshot["items"] if item.get("kind") == "tool"]
        assert len(execution_tools) == 1
        assert execution_tools[0]["id"] == "file-1"
        assert execution_tools[0]["outputFiles"] == [
            {"path": "final.txt", "changeType": "updated", "summary": "final"}
        ]
        assert all(item.get("id") != "tool-call:call-1" for item in execution_snapshot["items"])

        execution_session = app.state.storage.chat_state_store.read_session(project_id, child_id, thread_role="execution")
        assert execution_session["messages"] == []

        accept_response = client.post(
            f"/v1/projects/{project_id}/nodes/{child_id}/accept-local-review",
            json={"summary": "Looks good."},
        )
        assert accept_response.status_code == 200

        audit_snapshot = _wait_for_thread_snapshot(
            client,
            project_id,
            review_node_id,
            "audit",
            lambda snapshot: (
                snapshot.get("processingState") == "idle"
                and snapshot.get("activeTurnId") is None
                and any(
                    item.get("kind") == "message" and item.get("role") == "assistant"
                    for item in snapshot.get("items", [])
                )
            ),
        )
        audit_session = app.state.storage.chat_state_store.read_session(project_id, review_node_id, thread_role="audit")
        assert audit_session["messages"] == []

        assistant_messages = [
            item
            for item in audit_snapshot["items"]
            if item.get("kind") == "message" and item.get("role") == "assistant"
        ]
        assert len(assistant_messages) == 1
        assert "Integrated package from rehearsal." in assistant_messages[0]["text"]

        review_state = app.state.storage.review_state_store.read_state(project_id, review_node_id)
        assert review_state is not None
        assert review_state["rollup"]["draft"]["summary"] == "Integrated package from rehearsal."

        legacy_types = {
            "message_created",
            "assistant_delta",
            "assistant_tool_call",
            "assistant_completed",
            "execution_completed",
        }
        assert not any(
            item["thread_role"] in {"execution", "audit"}
            and isinstance(item["event"], dict)
            and item["event"].get("type") in legacy_types
            for item in published
        )
        invalidate_reasons = [
            envelope["payload"]["reason"]
            for kind, envelope in workflow_events
            if kind == "invalidate"
        ]
        assert "execution_started" in invalidate_reasons
        assert "execution_completed" in invalidate_reasons
        assert "review_rollup_started" in invalidate_reasons
        assert "review_rollup_completed" in invalidate_reasons


def test_phase5_rehearsal_route_rejects_workspace_outside_configured_root(monkeypatch, tmp_path: Path) -> None:
    rehearsal_root = tmp_path / "rehearsal-root"
    rehearsal_root.mkdir()
    outside_workspace = tmp_path / "outside-workspace"
    outside_workspace.mkdir()
    init_git_repo(outside_workspace)

    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", "1")
    monkeypatch.setenv("PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT", str(rehearsal_root))

    app = create_app(data_root=tmp_path / "appdata")
    codex_client = Phase5RehearsalCodexClient()
    _set_phase5_codex_client(app, codex_client)

    with TestClient(app) as client:
        project_id, root_id = _setup_project(client, outside_workspace)
        _confirm_spec(app.state.storage, project_id, root_id)
        response = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/finish-task")
        assert response.status_code == 412
        payload = response.json()
        assert payload["code"] == "execution_audit_v2_rehearsal_workspace_unsafe"
