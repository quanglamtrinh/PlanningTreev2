from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.thread_lineage_service import _ROLLOUT_BOOTSTRAP_PROMPT
from backend.tests.conftest import init_git_repo
from backend.tests.integration.test_phase5_execution_audit_rehearsal import (
    _confirm_spec,
    _do_lazy_split,
    _set_phase5_codex_client as _set_phase6_codex_client,
    _setup_project,
    _wait_for_thread_snapshot,
)


class Phase6ProductionCodexClient:
    def __init__(self) -> None:
        self.started_threads: list[str] = []
        self.forked_threads: list[dict[str, object]] = []
        self.prompts: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"phase6-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **kwargs: object) -> dict[str, str]:
        thread_id = f"phase6-fork-{len(self.forked_threads) + 1}"
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

        if isinstance(output_schema, dict) and "checkpoint_summary" in (output_schema.get("properties") or {}):
            summary = "Looks solid overall."
            checkpoint_summary = "Implementation looks coherent and ready to merge."
            if callable(on_raw_event):
                on_raw_event(
                    {
                        "method": "item/started",
                        "received_at": "2026-03-28T12:00:01Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": "auto-review-msg-1",
                        "request_id": None,
                        "call_id": None,
                        "params": {"item": {"type": "agentMessage", "id": "auto-review-msg-1"}},
                    }
                )
                on_raw_event(
                    {
                        "method": "item/agentMessage/delta",
                        "received_at": "2026-03-28T12:00:02Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": "auto-review-msg-1",
                        "request_id": None,
                        "call_id": None,
                        "params": {"delta": f"## Automated Local Review\n\n{summary}"},
                    }
                )
                on_raw_event(
                    {
                        "method": "turn/completed",
                        "received_at": "2026-03-28T12:00:03Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": None,
                        "request_id": None,
                        "call_id": None,
                        "params": {"turn": {"status": "completed"}},
                    }
                )
            return {
                "stdout": json.dumps(
                    {
                        "summary": summary,
                        "checkpoint_summary": checkpoint_summary,
                        "overall_severity": "info",
                        "overall_score": 94,
                        "findings": [],
                    }
                ),
                "thread_id": thread_id,
                "turn_status": "completed",
            }

        if output_schema is not None:
            summary = "Integrated package from production."
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


def _wait_for_condition(predicate, *, timeout_sec: float = 4.0):
    deadline = time.monotonic() + timeout_sec
    last_value = None
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        last_value = value
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for condition. Last value: {last_value!r}")


def _file_fingerprint(path: Path) -> tuple[bool, int | None, bytes | None]:
    if not path.exists():
        return (False, None, None)
    stat = path.stat()
    return (True, stat.st_mtime_ns, path.read_bytes())


def test_phase6_production_finish_task_cuts_execution_auto_review_and_rollup_to_v2(monkeypatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    init_git_repo(workspace_root)

    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)
    monkeypatch.delenv("PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "1")

    app = create_app(data_root=tmp_path / "appdata")
    codex_client = Phase6ProductionCodexClient()
    _set_phase6_codex_client(app, codex_client)

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

        execution_chat_path = app.state.storage.chat_state_store.path(project_id, child_id, thread_role="execution")
        child_audit_chat_path = app.state.storage.chat_state_store.path(project_id, child_id, thread_role="audit")
        review_audit_chat_path = app.state.storage.chat_state_store.path(project_id, review_node_id, thread_role="audit")
        execution_snapshot_path = app.state.storage.thread_snapshot_store_v2.path(project_id, child_id, "execution")
        child_audit_snapshot_path = app.state.storage.thread_snapshot_store_v2.path(project_id, child_id, "audit")
        review_audit_snapshot_path = app.state.storage.thread_snapshot_store_v2.path(project_id, review_node_id, "audit")
        execution_registry_path = app.state.storage.thread_registry_store.path(project_id, child_id, "execution")
        child_audit_registry_path = app.state.storage.thread_registry_store.path(project_id, child_id, "audit")
        review_audit_registry_path = app.state.storage.thread_registry_store.path(project_id, review_node_id, "audit")

        legacy_before = {
            "execution": _file_fingerprint(execution_chat_path),
            "child_audit": _file_fingerprint(child_audit_chat_path),
            "review_audit": _file_fingerprint(review_audit_chat_path),
        }
        legacy_write_calls: list[tuple[str, str]] = []
        original_write_session = app.state.storage.chat_state_store.write_session

        def capture_write_session(project_id_arg, node_id_arg, session, thread_role="ask_planning"):
            if (
                project_id_arg == project_id
                and node_id_arg in {child_id, review_node_id}
                and thread_role in {"execution", "audit"}
            ):
                legacy_write_calls.append((node_id_arg, str(thread_role)))
            return original_write_session(project_id_arg, node_id_arg, session, thread_role=thread_role)

        app.state.storage.chat_state_store.write_session = capture_write_session

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
        exec_state = _wait_for_condition(
            lambda: (
                state := app.state.storage.execution_state_store.read_state(project_id, child_id)
            )
            and state.get("status") == "review_accepted"
            and isinstance(state.get("auto_review"), dict)
            and state["auto_review"].get("status") == "completed"
            and state
        )
        child_audit_snapshot = _wait_for_thread_snapshot(
            client,
            project_id,
            child_id,
            "audit",
            lambda snapshot: (
                snapshot.get("processingState") == "idle"
                and snapshot.get("activeTurnId") is None
                and any(
                    item.get("kind") == "message" and item.get("role") == "assistant"
                    for item in snapshot.get("items", [])
                )
            ),
            timeout_sec=6.0,
        )
        review_audit_snapshot = _wait_for_thread_snapshot(
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
        review_state = _wait_for_condition(
            lambda: (
                state := app.state.storage.review_state_store.read_state(project_id, review_node_id)
            )
            and isinstance(state.get("rollup"), dict)
            and isinstance(state["rollup"].get("draft"), dict)
            and str(state["rollup"]["draft"].get("summary") or "").strip()
            and state
        )

        assert exec_state["auto_review"]["summary"] == "Looks solid overall."

        execution_session = app.state.storage.chat_state_store.read_session(project_id, child_id, thread_role="execution")
        child_audit_session = app.state.storage.chat_state_store.read_session(project_id, child_id, thread_role="audit")
        review_audit_session = app.state.storage.chat_state_store.read_session(project_id, review_node_id, thread_role="audit")
        assert execution_session["messages"] == []
        assert child_audit_session["messages"] == []
        assert review_audit_session["messages"] == []
        assert legacy_write_calls == []

        assert execution_registry_path.exists()
        assert child_audit_registry_path.exists()
        assert review_audit_registry_path.exists()
        assert execution_snapshot_path.exists()
        assert child_audit_snapshot_path.exists()
        assert review_audit_snapshot_path.exists()
        assert legacy_before["execution"] == _file_fingerprint(execution_chat_path)
        assert legacy_before["child_audit"] == _file_fingerprint(child_audit_chat_path)
        assert legacy_before["review_audit"] == _file_fingerprint(review_audit_chat_path)

        tool_items = [item for item in execution_snapshot["items"] if item.get("kind") == "tool"]
        assert len(tool_items) == 1
        assert tool_items[0]["id"] == "file-1"
        assert tool_items[0]["outputFiles"] == [{"path": "final.txt", "changeType": "updated", "summary": "final"}]
        assert all(item.get("id") != "tool-call:call-1" for item in execution_snapshot["items"])

        child_audit_messages = [
            item
            for item in child_audit_snapshot["items"]
            if item.get("kind") == "message" and item.get("role") == "assistant"
        ]
        assert len(child_audit_messages) == 1
        assert "Looks solid overall." in child_audit_messages[0]["text"]

        review_audit_messages = [
            item
            for item in review_audit_snapshot["items"]
            if item.get("kind") == "message" and item.get("role") == "assistant"
        ]
        assert len(review_audit_messages) == 1
        assert "Integrated package from production." in review_audit_messages[0]["text"]

        assert review_state["rollup"]["draft"]["summary"] == "Integrated package from production."

        legacy_types = {
            "message_created",
            "assistant_delta",
            "assistant_tool_call",
            "assistant_completed",
            "assistant_error",
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
        assert "auto_review_started" in invalidate_reasons
        assert "auto_review_completed" in invalidate_reasons
        assert "review_rollup_started" in invalidate_reasons
        _wait_for_condition(
            lambda: "review_rollup_completed"
            in [
                envelope["payload"]["reason"]
                for kind, envelope in workflow_events
                if kind == "invalidate"
            ]
        )
        invalidate_reasons = [
            envelope["payload"]["reason"]
            for kind, envelope in workflow_events
            if kind == "invalidate"
        ]
        assert "review_rollup_completed" in invalidate_reasons
