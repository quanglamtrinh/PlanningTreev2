from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import (
    ChatNotAllowed,
    ChatTurnAlreadyActive,
    InvalidRequest,
    NodeNotFound,
)
from backend.main import create_app
from backend.services import chat_service as chat_service_module
from backend.services.chat_service import ChatService
from backend.services import planningtree_workspace
from backend.services.project_service import ProjectService
from backend.services.review_service import ReviewService
from backend.services.thread_lineage_service import (
    ThreadLineageService,
    _ROLLOUT_BOOTSTRAP_PROMPT,
)
from backend.services.tree_service import TreeService
from backend.services.execution_gating import (
    AUDIT_FRAME_RECORD_MESSAGE_ID,
    AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
    append_immutable_audit_record,
)
from backend.storage.file_utils import iso_now
from backend.streaming.sse_broker import ChatEventBroker


class FakeChatCodexClient:
    def __init__(self, response_text: str = "Hello from AI", fail: bool = False) -> None:
        self.response_text = response_text
        self.fail = fail
        self.started_threads: list[str] = []
        self.resumed_threads: list[str] = []
        self.forked_threads: list[dict[str, object]] = []
        self.fail_resume = False
        self.turns_run: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"chat-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        self.resumed_threads.append(thread_id)
        if self.fail_resume:
            raise CodexTransportError("thread not found", "not_found")
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **kwargs: object) -> dict[str, str]:
        thread_id = f"chat-fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(
            {
                "thread_id": thread_id,
                "source_thread_id": source_thread_id,
                **kwargs,
            }
        )
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict:
        thread_id = kwargs.get("thread_id", "")
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": thread_id}
        self.turns_run.append(prompt)
        on_delta = kwargs.get("on_delta")
        on_tool_call = kwargs.get("on_tool_call")
        on_thread_status = kwargs.get("on_thread_status")
        if self.fail:
            raise CodexTransportError("AI failed", "rpc_error")
        if on_delta:
            on_delta("Hello ")
            on_delta("from AI")
        if on_tool_call:
            on_tool_call("read_file", {"path": "/test.py"})
        if on_thread_status:
            on_thread_status({"status": {"type": "running"}})
        return {"stdout": self.response_text, "thread_id": thread_id}


class SlowCheckpointCodexClient(FakeChatCodexClient):
    def __init__(
        self,
        *,
        response_text: str = "Hello from AI",
        fail_after_deltas: bool = False,
    ) -> None:
        super().__init__(response_text=response_text, fail=False)
        self.fail_after_deltas = fail_after_deltas

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict:
        thread_id = kwargs.get("thread_id", "")
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": thread_id}
        self.turns_run.append(prompt)
        on_delta = kwargs.get("on_delta")
        if on_delta:
            on_delta("Hello ")
            time.sleep(0.03)
            on_delta("from AI")
            time.sleep(0.1)
        if self.fail_after_deltas:
            raise CodexTransportError("AI failed after streaming", "rpc_error")
        return {"stdout": self.response_text, "thread_id": thread_id}


def _create_project(storage, workspace_root):
    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    project_id = snap["project"]["id"]
    root_id = snap["tree_state"]["root_node_id"]
    return project_id, root_id


def _make_service(storage, codex_client=None):
    codex = codex_client or FakeChatCodexClient()
    tree_service = TreeService()
    thread_lineage_service = ThreadLineageService(storage, codex, tree_service)
    return ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=ChatEventBroker(),
        chat_timeout=5,
        max_message_chars=10000,
    )


def _wait_for_turn(service, project_id, node_id, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        session = service.get_session(project_id, node_id)
        if not session.get("active_turn_id"):
            return session
        time.sleep(0.02)
    raise AssertionError("Turn did not complete in time")


def _wait_for_turn_role(service, project_id, node_id, thread_role, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        session = service.get_session(project_id, node_id, thread_role=thread_role)
        if not session.get("active_turn_id"):
            return session
        time.sleep(0.02)
    raise AssertionError("Turn did not complete in time")


def _wait_for_condition(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("Condition was not met in time")


def _write_confirmed_frame_and_spec(storage, project_id: str, node_id: str) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    project_path = Path(snapshot["project"]["project_path"])
    node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
    assert node_dir is not None

    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "revision": 1,
                "confirmed_revision": 1,
                "confirmed_at": iso_now(),
                "confirmed_content": "# Frame\nReview the execution carefully.\n",
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "spec.meta.json").write_text(
        json.dumps(
            {
                "source_frame_revision": 1,
                "confirmed_at": iso_now(),
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "spec.md").write_text("# Spec\nShip the implementation safely.\n", encoding="utf-8")


def _add_child(
    storage,
    project_id: str,
    parent_id: str,
    *,
    node_id: str,
    title: str,
    description: str,
    status: str = "ready",
) -> None:
    snap = storage.project_store.load_snapshot(project_id)
    node_index = snap["tree_state"]["node_index"]
    parent = node_index[parent_id]
    child_ids = [*parent.get("child_ids", []), node_id]
    parent["child_ids"] = child_ids
    node_index[node_id] = {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,
        "description": description,
        "status": status,
        "node_kind": "original",
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": len(child_ids) - 1,
        "hierarchical_number": f"{parent.get('hierarchical_number', '1')}.{len(child_ids)}",
        "created_at": iso_now(),
    }
    storage.project_store.save_snapshot(project_id, snap)


def _add_review_node(storage, project_id: str, parent_id: str, review_id: str) -> None:
    snap = storage.project_store.load_snapshot(project_id)
    node_index = snap["tree_state"]["node_index"]
    parent = node_index[parent_id]
    node_index[review_id] = {
        "node_id": review_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Review",
        "description": "",
        "status": "ready",
        "node_kind": "review",
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": 99,
        "hierarchical_number": f"{parent.get('hierarchical_number', '1')}.R",
        "created_at": iso_now(),
    }
    parent["review_node_id"] = review_id
    storage.project_store.save_snapshot(project_id, snap)


def test_get_session_returns_empty_for_new_node(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)
    session = service.get_session(project_id, root_id)
    assert session["thread_id"] is not None
    assert session["fork_reason"] == "ask_bootstrap"
    assert session["forked_from_role"] == "audit"
    assert session["active_turn_id"] is None
    assert session["messages"] == []


def test_get_session_skips_ask_bootstrap_when_external_live_turn_exists(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient()
    service = _make_service(storage, client)

    session = storage.chat_state_store.read_session(project_id, root_id)
    session["thread_id"] = "ask-thread-ext-live"
    session["thread_role"] = "ask_planning"
    session["forked_from_thread_id"] = "audit-thread-root"
    session["forked_from_node_id"] = root_id
    session["forked_from_role"] = "audit"
    session["fork_reason"] = "ask_bootstrap"
    session["lineage_root_thread_id"] = "audit-thread-root"
    session["active_turn_id"] = None
    storage.chat_state_store.write_session(project_id, root_id, session, thread_role="ask_planning")

    service.register_external_live_turn(project_id, root_id, "ask_planning", "turn-ext-1")
    loaded = service.get_session(project_id, root_id, thread_role="ask_planning")

    assert loaded["thread_id"] == "ask-thread-ext-live"
    assert service.has_live_turn(project_id, root_id, "ask_planning") is True
    assert client.resumed_threads == []
    assert client.forked_threads == []


def test_get_session_guarded_ask_resume_is_debounced_when_idle(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient()
    service = _make_service(storage, client)

    session = storage.chat_state_store.read_session(project_id, root_id)
    session["thread_id"] = "ask-thread-debounced"
    session["thread_role"] = "ask_planning"
    session["forked_from_thread_id"] = "audit-thread-root"
    session["forked_from_node_id"] = root_id
    session["forked_from_role"] = "audit"
    session["fork_reason"] = "ask_bootstrap"
    session["lineage_root_thread_id"] = "audit-thread-root"
    session["active_turn_id"] = None
    storage.chat_state_store.write_session(project_id, root_id, session, thread_role="ask_planning")

    first = service.get_session(project_id, root_id, thread_role="ask_planning")
    second = service.get_session(project_id, root_id, thread_role="ask_planning")

    assert first["thread_id"] == "ask-thread-debounced"
    assert second["thread_id"] == "ask-thread-debounced"
    assert [thread_id for thread_id in client.resumed_threads if thread_id == "ask-thread-debounced"] == [
        "ask-thread-debounced"
    ]


def test_get_session_does_not_inject_or_normalize_legacy_audit_messages(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)

    audit_session = storage.chat_state_store.read_session(project_id, root_id, thread_role="audit")
    audit_session["messages"] = [
        {
            "message_id": AUDIT_FRAME_RECORD_MESSAGE_ID,
            "role": "assistant",
            "content": "Legacy frame snapshot",
            "status": "completed",
            "error": None,
            "turn_id": "legacy-turn",
            "created_at": iso_now(),
            "updated_at": iso_now(),
        }
    ]
    storage.chat_state_store.write_session(project_id, root_id, audit_session, thread_role="audit")

    session = service.get_session(project_id, root_id, thread_role="audit")

    assert [message["message_id"] for message in session["messages"]] == [AUDIT_FRAME_RECORD_MESSAGE_ID]
    assert session["messages"][0]["role"] == "assistant"
    assert session["messages"][0]["turn_id"] == "legacy-turn"


def test_review_audit_session_stays_empty_without_seed_replay(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    _add_review_node(storage, project_id, root_id, "review-phase7")
    service = _make_service(storage)

    session = service.get_session(project_id, "review-phase7", thread_role="audit")

    assert session["thread_role"] == "audit"
    assert session["messages"] == []


def test_get_session_raises_for_nonexistent_node(storage, workspace_root):
    project_id, _ = _create_project(storage, workspace_root)
    service = _make_service(storage)
    with pytest.raises(NodeNotFound):
        service.get_session(project_id, "nonexistent")


def test_ensure_chat_thread_rejects_unsupported_interactive_role(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)

    with pytest.raises(ValueError, match="Unsupported interactive thread role"):
        service._ensure_chat_thread(project_id, root_id, "execution", None, str(workspace_root))


def test_create_message_creates_user_and_assistant(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)
    result = service.create_message(project_id, root_id, "Hello")
    assert result["user_message"]["role"] == "user"
    assert result["user_message"]["content"] == "Hello"
    assert result["user_message"]["status"] == "completed"
    assert result["assistant_message"]["role"] == "assistant"
    assert result["assistant_message"]["status"] == "pending"
    assert result["active_turn_id"] is not None


def test_create_message_rejects_empty_content(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)
    with pytest.raises(InvalidRequest, match="content is required"):
        service.create_message(project_id, root_id, "   ")


def test_create_message_rejects_over_limit_content(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    codex_client = FakeChatCodexClient()
    tree_service = TreeService()
    service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker=ChatEventBroker(),
        chat_timeout=5,
        max_message_chars=10,
    )
    with pytest.raises(InvalidRequest, match="exceeds"):
        service.create_message(project_id, root_id, "x" * 20)


def test_create_message_rejects_nonexistent_node(storage, workspace_root):
    project_id, _ = _create_project(storage, workspace_root)
    service = _make_service(storage)
    with pytest.raises(NodeNotFound):
        service.create_message(project_id, "nonexistent", "Hello")


def test_background_turn_completes(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(response_text="AI response text")
    service = _make_service(storage, client)
    service.create_message(project_id, root_id, "Hello")
    session = _wait_for_turn(service, project_id, root_id)

    assert session["active_turn_id"] is None
    assert len(session["messages"]) == 2
    assert session["messages"][1]["status"] == "completed"
    assert session["messages"][1]["content"] == "AI response text"
    assert session["thread_id"] is not None


def test_background_turn_persists_parts(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(response_text="AI response text")
    service = _make_service(storage, client)
    service.create_message(project_id, root_id, "Hello")
    session = _wait_for_turn(service, project_id, root_id)

    parts = session["messages"][1].get("parts", [])
    # FakeChatCodexClient emits: delta("Hello "), delta("from AI"),
    # tool_call("read_file"), thread_status("running")
    # After finalize: text part closed, tool completed, trailing status removed
    part_types = [p["type"] for p in parts]
    assert "assistant_text" in part_types
    assert "tool_call" in part_types
    # Status blocks are removed by finalize (trailing)
    assert "status_block" not in part_types

    text_part = next(p for p in parts if p["type"] == "assistant_text")
    assert text_part["is_streaming"] is False
    assert text_part["content"] == "Hello from AI"

    tool_part = next(p for p in parts if p["type"] == "tool_call")
    assert tool_part["tool_name"] == "read_file"
    assert tool_part["status"] == "completed"

    items = session["messages"][1].get("items", [])
    assert any(item.get("item_type") == "assistant_text" for item in items)
    assert any(item.get("item_type") == "tool_call" for item in items)


def test_background_turn_fails_marks_error(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(fail=True)
    service = _make_service(storage, client)
    service.create_message(project_id, root_id, "Hello")
    session = _wait_for_turn(service, project_id, root_id)

    assert session["active_turn_id"] is None
    assert session["messages"][1]["status"] == "error"
    assert session["messages"][1]["error"] is not None


def test_audit_message_auto_starts_local_review_when_execution_completed(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)
    service._review_service = ReviewService(storage, TreeService())
    storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "completed",
            "initial_sha": "sha256:initial000",
            "head_sha": "sha256:head000",
            "started_at": iso_now(),
            "completed_at": iso_now(),
        },
    )

    service.create_message(project_id, root_id, "Please review this", thread_role="audit")

    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "review_pending"


def test_audit_message_does_not_restart_local_review_when_already_pending(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)

    class TrackingReviewService:
        def __init__(self) -> None:
            self.calls = 0

        def start_local_review(self, project_id: str, node_id: str) -> None:
            del project_id, node_id
            self.calls += 1

    tracker = TrackingReviewService()
    service._review_service = tracker
    storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "review_pending",
            "initial_sha": "sha256:initial000",
            "head_sha": "sha256:head000",
            "started_at": iso_now(),
            "completed_at": iso_now(),
        },
    )

    service.create_message(project_id, root_id, "Second review note", thread_role="audit")

    assert tracker.calls == 0


def test_audit_message_fails_cleanly_when_local_review_start_errors(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)

    class ExplodingReviewService:
        def start_local_review(self, project_id: str, node_id: str) -> None:
            del project_id, node_id
            raise RuntimeError("boom")

    service._review_service = ExplodingReviewService()
    storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "completed",
            "initial_sha": "sha256:initial000",
            "head_sha": "sha256:head000",
            "started_at": iso_now(),
            "completed_at": iso_now(),
        },
    )

    with pytest.raises(RuntimeError, match="boom"):
        service.create_message(project_id, root_id, "Please review this", thread_role="audit")

    session = storage.chat_state_store.read_session(project_id, root_id, thread_role="audit")
    assert session["messages"] == []
    assert session["active_turn_id"] is None


def test_audit_first_local_review_turn_uses_local_review_prompt_once(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(response_text="Audit review complete")
    service = _make_service(storage, client)
    service._review_service = ReviewService(storage, TreeService())
    _write_confirmed_frame_and_spec(storage, project_id, root_id)
    storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "completed",
            "initial_sha": "sha256:init",
            "head_sha": "sha256:head",
            "started_at": iso_now(),
            "completed_at": iso_now(),
        },
    )

    service.create_message(project_id, root_id, "Please review the execution", thread_role="audit")
    _wait_for_turn_role(service, project_id, root_id, "audit")

    first_prompt = client.turns_run[-1]
    assert "Confirmed frame" in first_prompt
    assert "Confirmed spec" in first_prompt
    assert "Head SHA: sha256:head" in first_prompt

    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "review_pending"
    assert exec_state["local_review_started_at"] is not None
    assert exec_state["local_review_prompt_consumed_at"] is not None

    service.create_message(project_id, root_id, "One more audit note", thread_role="audit")
    _wait_for_turn_role(service, project_id, root_id, "audit")

    second_prompt = client.turns_run[-1]
    assert "Confirmed frame" not in second_prompt
    assert "Confirmed spec" not in second_prompt
    assert "Head SHA: sha256:head" not in second_prompt


def test_failed_first_local_review_turn_keeps_boundary_open_for_retry(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(fail=True)
    service = _make_service(storage, client)
    service._review_service = ReviewService(storage, TreeService())
    _write_confirmed_frame_and_spec(storage, project_id, root_id)
    storage.execution_state_store.write_state(
        project_id,
        root_id,
        {
            "status": "completed",
            "initial_sha": "sha256:init",
            "head_sha": "sha256:head",
            "started_at": iso_now(),
            "completed_at": iso_now(),
        },
    )

    service.create_message(project_id, root_id, "Review attempt one", thread_role="audit")
    failed_session = _wait_for_turn_role(service, project_id, root_id, "audit")
    assert failed_session["messages"][1]["status"] == "error"
    assert "Confirmed frame" in client.turns_run[-1]

    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "review_pending"
    assert exec_state["local_review_started_at"] is not None
    assert exec_state["local_review_prompt_consumed_at"] is None

    client.fail = False
    client.response_text = "Retry succeeded"
    service.create_message(project_id, root_id, "Review attempt two", thread_role="audit")
    _wait_for_turn_role(service, project_id, root_id, "audit")

    assert "Confirmed frame" in client.turns_run[-1]
    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["local_review_prompt_consumed_at"] is not None


def test_audit_first_package_review_turn_uses_package_review_prompt_once(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(response_text="Package audit complete")
    service = _make_service(storage, client)
    _write_confirmed_frame_and_spec(storage, project_id, root_id)
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-package",
        title="Package child",
        description="Ship the child slice.",
        status="done",
    )
    _add_review_node(storage, project_id, root_id, "review-package")
    storage.review_state_store.write_state(
        project_id,
        "review-package",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": iso_now(),
                },
                {
                    "label": "K1",
                    "sha": "sha256:child",
                    "summary": "Package child completed successfully.",
                    "source_node_id": "child-package",
                    "accepted_at": iso_now(),
                },
            ],
            "rollup": {
                "status": "accepted",
                "summary": "Package is coherent and ready.",
                "sha": "sha256:rollup",
                "accepted_at": iso_now(),
            },
            "pending_siblings": [],
        },
    )
    append_immutable_audit_record(
        storage,
        project_id,
        root_id,
        message_id=AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
        content="## Rollup Package\n\n**Summary:** Package is coherent and ready.\n",
    )
    storage.review_state_store.open_package_review(project_id, "review-package")

    service.create_message(project_id, root_id, "Review the package", thread_role="audit")
    _wait_for_turn_role(service, project_id, root_id, "audit")

    first_prompt = client.turns_run[-1]
    assert "Confirmed parent frame" in first_prompt
    assert "Split package:" in first_prompt
    assert "Package is coherent and ready." in first_prompt

    review_state = storage.review_state_store.read_state(project_id, "review-package")
    assert review_state is not None
    assert review_state["rollup"]["package_review_started_at"] is not None
    assert review_state["rollup"]["package_review_prompt_consumed_at"] is not None

    service.create_message(project_id, root_id, "One more package note", thread_role="audit")
    _wait_for_turn_role(service, project_id, root_id, "audit")

    second_prompt = client.turns_run[-1]
    assert "Confirmed parent frame" not in second_prompt
    assert "Split package:" not in second_prompt
    assert "Package is coherent and ready." not in second_prompt


def test_failed_first_package_review_turn_keeps_boundary_open_for_retry(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(fail=True)
    service = _make_service(storage, client)
    _write_confirmed_frame_and_spec(storage, project_id, root_id)
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-package",
        title="Package child",
        description="Ship the child slice.",
        status="done",
    )
    _add_review_node(storage, project_id, root_id, "review-package")
    storage.review_state_store.write_state(
        project_id,
        "review-package",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": iso_now(),
                },
                {
                    "label": "K1",
                    "sha": "sha256:child",
                    "summary": "Package child completed successfully.",
                    "source_node_id": "child-package",
                    "accepted_at": iso_now(),
                },
            ],
            "rollup": {
                "status": "accepted",
                "summary": "Package is coherent and ready.",
                "sha": "sha256:rollup",
                "accepted_at": iso_now(),
            },
            "pending_siblings": [],
        },
    )
    append_immutable_audit_record(
        storage,
        project_id,
        root_id,
        message_id=AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
        content="## Rollup Package\n\n**Summary:** Package is coherent and ready.\n",
    )
    storage.review_state_store.open_package_review(project_id, "review-package")

    service.create_message(project_id, root_id, "Review package attempt one", thread_role="audit")
    failed_session = _wait_for_turn_role(service, project_id, root_id, "audit")
    failed_assistant = next(
        message
        for message in reversed(failed_session["messages"])
        if message.get("role") == "assistant"
    )
    assert failed_assistant["status"] == "error"
    assert "Split package:" in client.turns_run[-1]

    review_state = storage.review_state_store.read_state(project_id, "review-package")
    assert review_state is not None
    assert review_state["rollup"]["package_review_prompt_consumed_at"] is None

    client.fail = False
    client.response_text = "Retry package success"
    service.create_message(project_id, root_id, "Review package attempt two", thread_role="audit")
    _wait_for_turn_role(service, project_id, root_id, "audit")

    assert "Split package:" in client.turns_run[-1]
    review_state = storage.review_state_store.read_state(project_id, "review-package")
    assert review_state is not None
    assert review_state["rollup"]["package_review_prompt_consumed_at"] is not None


def test_first_child_ask_turn_uses_child_activation_prompt_once(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(response_text="Ask response")
    service = _make_service(storage, client)
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-a",
        title="Child A",
        description="Finish the first slice.",
        status="done",
    )
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-b",
        title="Child B",
        description="Finish the second slice.",
        status="ready",
    )
    _add_review_node(storage, project_id, root_id, "review-child")
    storage.review_state_store.write_state(
        project_id,
        "review-child",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": iso_now(),
                },
                {
                    "label": "K1",
                    "sha": "sha256:child-a",
                    "summary": "Child A delivered the first milestone.",
                    "source_node_id": "child-a",
                    "accepted_at": iso_now(),
                },
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    service.create_message(project_id, "child-b", "Start shaping this child", thread_role="ask_planning")
    _wait_for_turn_role(service, project_id, "child-b", "ask_planning")

    first_prompt = client.turns_run[-1]
    assert "Child activation context:" in first_prompt
    assert "- Assignment: Child B" in first_prompt
    assert "- Objective: Finish the second slice." in first_prompt
    assert "Prior accepted checkpoints:" in first_prompt
    assert "Child A delivered the first milestone." in first_prompt

    service.create_message(project_id, "child-b", "Another ask turn", thread_role="ask_planning")
    _wait_for_turn_role(service, project_id, "child-b", "ask_planning")

    second_prompt = client.turns_run[-1]
    assert "Child activation context:" not in second_prompt
    assert "Prior accepted checkpoints:" not in second_prompt


def test_failed_first_child_ask_turn_keeps_child_activation_open_for_retry_and_heals_child_audit(
    storage,
    workspace_root,
):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(response_text="Retry success")
    service = _make_service(storage, client)
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-a",
        title="Child A",
        description="Finish the first slice.",
        status="done",
    )
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-b",
        title="Child B",
        description="Finish the second slice.",
        status="ready",
    )
    _add_review_node(storage, project_id, root_id, "review-child")
    storage.review_state_store.write_state(
        project_id,
        "review-child",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": iso_now(),
                },
                {
                    "label": "K1",
                    "sha": "sha256:child-a",
                    "summary": "Child A delivered the first milestone.",
                    "source_node_id": "child-a",
                    "accepted_at": iso_now(),
                },
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    workspace_root_str = str(workspace_root)
    service._thread_lineage_service.ensure_root_audit_thread(project_id, root_id, workspace_root_str)
    service._thread_lineage_service.ensure_forked_thread(
        project_id,
        "review-child",
        "audit",
        source_node_id=root_id,
        source_role="audit",
        fork_reason="review_bootstrap",
        workspace_root=workspace_root_str,
    )
    missing_child_audit = storage.chat_state_store.read_session(
        project_id,
        "child-b",
        thread_role="audit",
    )
    assert missing_child_audit["thread_id"] is None

    client.fail = True
    service.create_message(project_id, "child-b", "Start shaping this child", thread_role="ask_planning")
    failed_session = _wait_for_turn_role(service, project_id, "child-b", "ask_planning")
    failed_assistant = next(
        message
        for message in reversed(failed_session["messages"])
        if message.get("role") == "assistant"
    )
    assert failed_assistant["status"] == "error"
    assert "Child activation context:" in client.turns_run[-1]

    child_audit_session = storage.chat_state_store.read_session(
        project_id,
        "child-b",
        thread_role="audit",
    )
    assert child_audit_session["thread_id"] is not None
    assert child_audit_session["fork_reason"] == "child_activation"
    assert child_audit_session["forked_from_node_id"] == "review-child"

    client.fail = False
    service.create_message(project_id, "child-b", "Retry shaping this child", thread_role="ask_planning")
    _wait_for_turn_role(service, project_id, "child-b", "ask_planning")

    retry_prompt = client.turns_run[-1]
    assert "Child activation context:" in retry_prompt
    assert "Prior accepted checkpoints:" in retry_prompt

    service.create_message(project_id, "child-b", "Third ask turn", thread_role="ask_planning")
    _wait_for_turn_role(service, project_id, "child-b", "ask_planning")

    third_prompt = client.turns_run[-1]
    assert "Child activation context:" not in third_prompt
    assert "Prior accepted checkpoints:" not in third_prompt


def test_reset_child_ask_session_reopens_child_activation_prompt(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(response_text="Ask response")
    service = _make_service(storage, client)
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-a",
        title="Child A",
        description="Finish the first slice.",
        status="done",
    )
    _add_child(
        storage,
        project_id,
        root_id,
        node_id="child-b",
        title="Child B",
        description="Finish the second slice.",
        status="ready",
    )
    _add_review_node(storage, project_id, root_id, "review-child")
    storage.review_state_store.write_state(
        project_id,
        "review-child",
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": iso_now(),
                },
                {
                    "label": "K1",
                    "sha": "sha256:child-a",
                    "summary": "Child A delivered the first milestone.",
                    "source_node_id": "child-a",
                    "accepted_at": iso_now(),
                },
            ],
            "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
            "pending_siblings": [],
        },
    )

    service.create_message(project_id, "child-b", "Start shaping this child", thread_role="ask_planning")
    _wait_for_turn_role(service, project_id, "child-b", "ask_planning")
    assert "Child activation context:" in client.turns_run[-1]

    reset_session = service.reset_session(project_id, "child-b", thread_role="ask_planning")
    assert reset_session["messages"] == []

    service.create_message(project_id, "child-b", "Restart shaping this child", thread_role="ask_planning")
    _wait_for_turn_role(service, project_id, "child-b", "ask_planning")
    assert "Child activation context:" in client.turns_run[-1]


def test_background_turn_checkpoints_partial_content(storage, workspace_root, monkeypatch):
    monkeypatch.setattr(chat_service_module, "_DRAFT_FLUSH_INTERVAL_SEC", 0.01)
    project_id, root_id = _create_project(storage, workspace_root)
    client = SlowCheckpointCodexClient()
    service = _make_service(storage, client)
    service.create_message(project_id, root_id, "Hello")

    streaming_session = _wait_for_condition(
        lambda: (
            current
            if (current := service.get_session(project_id, root_id))["messages"]
            and current["messages"][1]["status"] == "streaming"
            else None
        ),
        timeout=2.0,
    )

    assert streaming_session["messages"][1]["content"].startswith("Hello")
    assert streaming_session["active_turn_id"] is not None

    completed_session = _wait_for_turn(service, project_id, root_id)
    assert completed_session["messages"][1]["status"] == "completed"


def test_background_turn_failure_preserves_partial_content(storage, workspace_root, monkeypatch):
    monkeypatch.setattr(chat_service_module, "_DRAFT_FLUSH_INTERVAL_SEC", 0.01)
    project_id, root_id = _create_project(storage, workspace_root)
    client = SlowCheckpointCodexClient(fail_after_deltas=True)
    service = _make_service(storage, client)
    service.create_message(project_id, root_id, "Hello")
    session = _wait_for_turn(service, project_id, root_id)

    assert session["messages"][1]["status"] == "error"
    assert session["messages"][1]["content"] == "Hello from AI"


def test_create_message_rejects_when_active_turn(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)

    class SlowCodexClient(FakeChatCodexClient):
        def run_turn_streaming(self, prompt, **kwargs):
            import time
            time.sleep(1)
            return super().run_turn_streaming(prompt, **kwargs)

    service = _make_service(storage, SlowCodexClient())
    service.create_message(project_id, root_id, "First")
    with pytest.raises(ChatTurnAlreadyActive):
        service.create_message(project_id, root_id, "Second")


def test_reset_session_clears_messages(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)
    service.create_message(project_id, root_id, "Hello")
    _wait_for_turn(service, project_id, root_id)

    session = service.reset_session(project_id, root_id)
    assert session["messages"] == []
    assert session["thread_id"] is None


def test_reset_session_rejects_when_active_turn(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)

    class SlowCodexClient(FakeChatCodexClient):
        def run_turn_streaming(self, prompt, **kwargs):
            import time
            time.sleep(1)
            return super().run_turn_streaming(prompt, **kwargs)

    service = _make_service(storage, SlowCodexClient())
    service.create_message(project_id, root_id, "First")
    with pytest.raises(ChatTurnAlreadyActive):
        service.reset_session(project_id, root_id)


def test_stale_turn_recovery(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    service = _make_service(storage)

    # Simulate a stale turn in persisted state
    session = storage.chat_state_store.read_session(project_id, root_id)
    session["active_turn_id"] = "stale-turn"
    session["messages"].append({
        "message_id": "msg-stale",
        "role": "assistant",
        "content": "",
        "status": "pending",
        "error": None,
        "turn_id": "stale-turn",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    storage.chat_state_store.write_session(project_id, root_id, session)

    # get_session should recover
    recovered = service.get_session(project_id, root_id)
    assert recovered["active_turn_id"] is None
    assert recovered["messages"][0]["status"] == "error"
    assert "interrupted" in recovered["messages"][0]["error"].lower()


def test_has_live_turns_for_project(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)

    class SlowCodexClient(FakeChatCodexClient):
        def run_turn_streaming(self, prompt, **kwargs):
            import time
            time.sleep(1)
            return super().run_turn_streaming(prompt, **kwargs)

    service = _make_service(storage, SlowCodexClient())
    assert not service.has_live_turns_for_project(project_id)
    service.create_message(project_id, root_id, "Hello")
    assert service.has_live_turns_for_project(project_id)


def test_thread_id_created_and_preserved_on_failure(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient(fail=True)
    service = _make_service(storage, client)
    service.create_message(project_id, root_id, "Hello")
    session = _wait_for_turn(service, project_id, root_id)
    # thread_id should be set (was persisted before turn ran)
    assert session["thread_id"] is not None


def test_thread_recreated_when_resume_fails(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)
    client = FakeChatCodexClient()
    service = _make_service(storage, client)

    # First message creates a thread
    service.create_message(project_id, root_id, "First")
    session = _wait_for_turn(service, project_id, root_id)
    first_thread = session["thread_id"]
    assert first_thread is not None

    # Now make resume fail
    client.fail_resume = True
    service.create_message(project_id, root_id, "Second")
    session = _wait_for_turn(service, project_id, root_id)
    second_thread = session["thread_id"]
    # Missing-thread recovery reboots root audit and then re-forks ask.
    assert second_thread != first_thread
    assert len(client.started_threads) >= 2
    assert len(client.forked_threads) >= 2


def test_project_reset_rejected_when_live_turn(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)

    class SlowCodexClient(FakeChatCodexClient):
        def run_turn_streaming(self, prompt, **kwargs):
            import time
            time.sleep(1)
            return super().run_turn_streaming(prompt, **kwargs)

    codex_client = SlowCodexClient()
    tree_service = TreeService()
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker=ChatEventBroker(),
        chat_timeout=5,
    )
    project_service = ProjectService(storage, chat_service=chat_service)

    chat_service.create_message(project_id, root_id, "Hello")

    with pytest.raises(ChatNotAllowed, match="reset"):
        project_service.reset_to_root(project_id)


def test_project_delete_rejected_when_live_turn(storage, workspace_root):
    project_id, root_id = _create_project(storage, workspace_root)

    class SlowCodexClient(FakeChatCodexClient):
        def run_turn_streaming(self, prompt, **kwargs):
            import time
            time.sleep(1)
            return super().run_turn_streaming(prompt, **kwargs)

    codex_client = SlowCodexClient()
    tree_service = TreeService()
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker=ChatEventBroker(),
        chat_timeout=5,
    )
    project_service = ProjectService(storage, chat_service=chat_service)

    chat_service.create_message(project_id, root_id, "Hello")

    with pytest.raises(ChatNotAllowed, match="remove"):
        project_service.delete_project(project_id)


def test_app_shutdown_stops_codex_client(data_root):
    app = create_app(data_root=data_root)
    stop_calls: list[bool] = []

    def fake_stop() -> None:
        stop_calls.append(True)

    app.state.codex_client.stop = fake_stop

    with TestClient(app):
        pass

    assert stop_calls == [True]
