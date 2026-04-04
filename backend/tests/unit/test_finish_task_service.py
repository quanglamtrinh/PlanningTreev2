"""Tests for FinishTaskService execution lifecycle and state transitions."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from backend.conversation.services.request_ledger_service import RequestLedgerService
from backend.conversation.services.thread_query_service import ThreadQueryService
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.services.thread_runtime_service import ThreadRuntimeService
from backend.conversation.services.workflow_event_publisher import WorkflowEventPublisher
from backend.ai.execution_prompt_builder import build_execution_base_instructions
from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import ExecutionAuditRehearsalWorkspaceUnsafe, FinishTaskNotAllowed
from backend.services.chat_service import ChatService
from backend.services.finish_task_service import FinishTaskService
from backend.services.node_detail_service import NodeDetailService
from backend.services.project_service import ProjectService
from backend.services.review_service import ReviewService
from backend.services.thread_lineage_service import (
    ThreadLineageService,
    _ROLLOUT_BOOTSTRAP_PROMPT,
)
from backend.services.tree_service import TreeService
from backend.streaming.sse_broker import ChatEventBroker, GlobalEventBroker


class FakeExecutionCodexClient:
    def __init__(
        self,
        *,
        response_text: str = "Implemented the task.",
        fail: bool = False,
        barrier: threading.Event | None = None,
        create_file_name: str = "execution-output.txt",
    ) -> None:
        self.response_text = response_text
        self.fail = fail
        self.barrier = barrier
        self.create_file_name = create_file_name
        self.started_threads: list[str] = []
        self.resumed_threads: list[str] = []
        self.forked_threads: list[dict[str, object]] = []
        self.prompts: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"exec-start-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        self.resumed_threads.append(thread_id)
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **kwargs: object) -> dict[str, str]:
        thread_id = f"exec-fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(
            {
                "thread_id": thread_id,
                "source_thread_id": source_thread_id,
                **kwargs,
            }
        )
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        thread_id = str(kwargs.get("thread_id") or "")
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": thread_id}
        self.prompts.append(prompt)
        cwd = kwargs.get("cwd")
        on_delta = kwargs.get("on_delta")
        on_plan_delta = kwargs.get("on_plan_delta")
        on_tool_call = kwargs.get("on_tool_call")
        on_thread_status = kwargs.get("on_thread_status")
        on_item_event = kwargs.get("on_item_event")

        if self.barrier is not None:
            self.barrier.wait(timeout=5)

        if on_thread_status:
            on_thread_status({"status": {"type": "running"}})
        if on_plan_delta:
            on_plan_delta("Inspect existing files", {"id": "plan-1"})
        if on_tool_call:
            on_tool_call("write_file", {"path": self.create_file_name})
        if on_item_event:
            on_item_event(
                "started",
                {
                    "type": "commandExecution",
                    "id": "cmd-1",
                    "command": f"Write {self.create_file_name}",
                    "cwd": cwd if isinstance(cwd, str) else None,
                    "source": "agent",
                    "status": "inProgress",
                },
            )
        if on_delta:
            on_delta("Working ")
            time.sleep(0.02)
            on_delta("done")

        if self.fail:
            raise CodexTransportError("Execution failed", "rpc_error")

        if isinstance(cwd, str) and cwd:
            Path(cwd, self.create_file_name).write_text("updated by execution\n", encoding="utf-8")
        if on_item_event:
            on_item_event(
                "completed",
                {
                    "type": "commandExecution",
                    "id": "cmd-1",
                    "command": f"Write {self.create_file_name}",
                    "cwd": cwd if isinstance(cwd, str) else None,
                    "source": "agent",
                    "status": "completed",
                    "aggregatedOutput": f"updated {self.create_file_name}",
                    "exitCode": 0,
                },
            )

        return {"stdout": self.response_text, "thread_id": thread_id}


class FakeExecutionV2CodexClient(FakeExecutionCodexClient):
    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        thread_id = str(kwargs.get("thread_id") or "")
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": thread_id}
        self.prompts.append(prompt)
        on_raw_event = kwargs.get("on_raw_event")
        cwd = kwargs.get("cwd")
        output_schema = kwargs.get("output_schema")

        if self.fail:
            raise CodexTransportError("Execution failed", "rpc_error")

        if output_schema is not None:
            rendered_message = "## Automated Local Review\n\nLooks solid overall."
            if callable(on_raw_event):
                on_raw_event(
                    {
                        "method": "item/started",
                        "received_at": "2026-03-28T10:05:01Z",
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
                        "received_at": "2026-03-28T10:05:02Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": "auto-review-msg-1",
                        "request_id": None,
                        "call_id": None,
                        "params": {"delta": rendered_message},
                    }
                )
                on_raw_event(
                    {
                        "method": "turn/completed",
                        "received_at": "2026-03-28T10:05:03Z",
                        "thread_id": thread_id,
                        "turn_id": None,
                        "item_id": None,
                        "request_id": None,
                        "call_id": None,
                        "params": {"turn": {"status": "completed"}},
                    }
                )
            return {
                "stdout": (
                    '{"summary":"Looks solid overall.","checkpoint_summary":"Looks solid overall.",'
                    '"overall_severity":"info","overall_score":92,'
                    '"findings":[{"title":"No blocking issues","severity":"info",'
                    '"description":"Implementation matches the spec.","file_path":"","evidence":"",'
                    '"suggested_followup":""}]}'
                ),
                "thread_id": thread_id,
                "turn_status": "completed",
            }

        if callable(on_raw_event):
            on_raw_event(
                {
                    "method": "item/started",
                    "received_at": "2026-03-28T10:00:01Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": "msg-1",
                    "request_id": None,
                    "call_id": None,
                    "params": {"item": {"type": "agentMessage", "id": "msg-1"}},
                }
            )
            on_raw_event(
                {
                    "method": "item/agentMessage/delta",
                    "received_at": "2026-03-28T10:00:02Z",
                    "thread_id": thread_id,
                    "turn_id": None,
                    "item_id": "msg-1",
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
                        "arguments": {"path": self.create_file_name},
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
        if isinstance(cwd, str) and cwd:
            Path(cwd, self.create_file_name).write_text("updated by execution\n", encoding="utf-8")
        if callable(on_raw_event):
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
        return {"stdout": self.response_text, "thread_id": thread_id, "turn_status": "completed"}


def _wait_for_condition(predicate, timeout: float = 2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("Condition did not become true in time")


def test_thread_runtime_service_prefers_patch_body_for_tool_call_arguments_text() -> None:
    patch_body = "*** Begin Patch\n*** Update File: src/app.ts\n@@\n+const ok = true\n*** End Patch"
    arguments = {"input": patch_body, "path": "src/app.ts"}
    assert ThreadRuntimeService._tool_call_arguments_text(arguments) == patch_body


def _build_v2_runtime(
    *,
    storage,
    tree_service,
    chat_service,
    codex_client,
) -> tuple[ThreadRuntimeService, WorkflowEventPublisher]:
    request_ledger_service = RequestLedgerService()
    thread_registry_service = ThreadRegistryService(storage.thread_registry_store)
    chat_service._thread_lineage_service.set_thread_registry_service(thread_registry_service)
    conversation_event_broker = ChatEventBroker()
    workflow_event_broker = GlobalEventBroker()
    query_service = ThreadQueryService(
        storage=storage,
        chat_service=chat_service,
        thread_lineage_service=chat_service._thread_lineage_service,
        codex_client=codex_client,
        snapshot_store=storage.thread_snapshot_store_v2,
        registry_service=thread_registry_service,
        request_ledger_service=request_ledger_service,
        thread_event_broker=conversation_event_broker,
    )
    runtime = ThreadRuntimeService(
        storage=storage,
        tree_service=tree_service,
        chat_service=chat_service,
        codex_client=codex_client,
        query_service=query_service,
        request_ledger_service=request_ledger_service,
        chat_timeout=5,
        max_message_chars=10000,
    )
    workflow_publisher = WorkflowEventPublisher(workflow_event_broker)
    return runtime, workflow_publisher


@pytest.fixture
def project_id(storage, workspace_root):
    snap = ProjectService(storage).attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


@pytest.fixture
def root_node_id(storage, project_id):
    snap = storage.project_store.load_snapshot(project_id)
    return snap["tree_state"]["root_node_id"]


@pytest.fixture
def detail_service(storage, tree_service):
    return NodeDetailService(storage, tree_service)


@pytest.fixture
def chat_event_broker():
    return ChatEventBroker()


@pytest.fixture
def codex_client():
    return FakeExecutionCodexClient()


@pytest.fixture
def finish_service(storage, tree_service, detail_service, codex_client, chat_event_broker):
    return FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=detail_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
    )


def _confirm_spec(storage, project_id: str, node_id: str) -> None:
    from backend.services import planningtree_workspace

    detail_svc = NodeDetailService(storage, TreeService())
    storage.thread_registry_store.write_entry(
        project_id,
        node_id,
        "audit",
        {
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "audit",
            "threadId": f"audit-thread-{node_id}",
        },
    )

    def _get_node_dir():
        snap = storage.project_store.load_snapshot(project_id)
        project = snap.get("project", {})
        project_path = Path(project.get("project_path", ""))
        return planningtree_workspace.resolve_node_dir(project_path, snap, node_id)

    node_dir = _get_node_dir()
    frame_path = node_dir / "frame.md"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text("# Task Title\nTest Task\n\n# Objective\nDo something\n", encoding="utf-8")
    detail_svc.confirm_frame(project_id, node_id)

    node_dir = _get_node_dir()
    spec_path = node_dir / "spec.md"
    spec_path.write_text("# Spec\nImplement the thing\n", encoding="utf-8")
    detail_svc.confirm_spec(project_id, node_id)

    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][node_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, snap)


def test_finish_task_fails_spec_not_confirmed(finish_service, project_id, root_node_id):
    with pytest.raises(FinishTaskNotAllowed, match="Spec must be confirmed"):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_fails_not_leaf(finish_service, storage, project_id, root_node_id):
    _confirm_spec(storage, project_id, root_node_id)
    snap = storage.project_store.load_snapshot(project_id)
    node_index = snap["tree_state"]["node_index"]
    node_index["child-001"] = {
        "node_id": "child-001",
        "parent_id": root_node_id,
        "child_ids": [],
        "title": "Child",
        "description": "",
        "status": "ready",
        "node_kind": "original",
        "depth": 1,
        "display_order": 0,
        "hierarchical_number": "1.1",
        "created_at": "2026-01-01T00:00:00Z",
    }
    node_index[root_node_id]["child_ids"] = ["child-001"]
    storage.project_store.save_snapshot(project_id, snap)

    with pytest.raises(FinishTaskNotAllowed, match="leaf"):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_fails_wrong_status(finish_service, storage, project_id, root_node_id):
    _confirm_spec(storage, project_id, root_node_id)
    snap = storage.project_store.load_snapshot(project_id)
    snap["tree_state"]["node_index"][root_node_id]["status"] = "locked"
    storage.project_store.save_snapshot(project_id, snap)

    with pytest.raises(FinishTaskNotAllowed, match="status"):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_fails_already_executing(finish_service, storage, project_id, root_node_id):
    _confirm_spec(storage, project_id, root_node_id)
    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "executing",
            "initial_sha": "sha256:abc",
            "head_sha": None,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None,
        },
    )

    with pytest.raises(FinishTaskNotAllowed, match="already in progress"):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_creates_execution_state_session_and_thread(
    storage,
    tree_service,
    detail_service,
    chat_event_broker,
    project_id,
    root_node_id,
) -> None:
    _confirm_spec(storage, project_id, root_node_id)
    barrier = threading.Event()
    codex_client = FakeExecutionCodexClient(barrier=barrier)
    finish_service = FinishTaskService(
        storage,
        tree_service,
        detail_service,
        codex_client,
        ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker,
        chat_timeout=5,
    )

    result = finish_service.finish_task(project_id, root_node_id)

    exec_state = storage.execution_state_store.read_state(project_id, root_node_id)
    assert exec_state is not None
    assert exec_state["status"] == "executing"
    assert exec_state["initial_sha"].startswith("sha256:")
    assert exec_state["head_sha"] is None
    assert result["execution_started"] is True
    assert result["execution_status"] == "executing"
    assert result["shaping_frozen"] is True

    session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="execution")
    assert session["thread_id"] == "exec-fork-thread-1"
    assert session["fork_reason"] == "execution_bootstrap"
    assert session["forked_from_role"] == "audit"
    assert session["forked_from_thread_id"] is not None
    assert session["lineage_root_thread_id"] is not None
    assert session["active_turn_id"] is not None
    assert len(session["messages"]) == 1
    assert session["messages"][0]["role"] == "assistant"
    assert session["messages"][0]["status"] == "pending"
    assert storage.chat_state_store.path(project_id, root_node_id, thread_role="execution").exists()
    assert len(codex_client.started_threads) == 1
    assert len(codex_client.forked_threads) == 1
    assert codex_client.forked_threads[0]["base_instructions"] == build_execution_base_instructions()
    assert codex_client.forked_threads[0]["dynamic_tools"] == []
    assert codex_client.forked_threads[0]["writable_roots"] == [str(storage.workspace_store.get_folder_path(project_id))]

    barrier.set()


def test_finish_task_background_completion_publishes_sse_and_head_sha(
    finish_service,
    storage,
    chat_event_broker,
    project_id,
    root_node_id,
):
    _confirm_spec(storage, project_id, root_node_id)
    published: list[dict[str, object]] = []
    original_publish = chat_event_broker.publish

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

    chat_event_broker.publish = capture_publish  # type: ignore[method-assign]

    finish_service.finish_task(project_id, root_node_id)

    _wait_for_condition(
        lambda: (
            state := storage.execution_state_store.read_state(project_id, root_node_id)
        )
        and state["status"] == "completed"
        and state["head_sha"] is not None
        and storage.chat_state_store.read_session(project_id, root_node_id, thread_role="execution")[
            "active_turn_id"
        ] is None
    )

    session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="execution")
    assert session["active_turn_id"] is None
    assert session["messages"][0]["status"] == "completed"
    assert session["messages"][0]["content"] == "Implemented the task."
    part_types = [part["type"] for part in session["messages"][0].get("parts", [])]
    assert "plan_item" in part_types
    assert "tool_call" in part_types
    assert "status_block" in part_types
    items = session["messages"][0].get("items", [])
    assert any(item.get("item_type") == "plan_item" for item in items)
    assert any(item.get("item_type") == "tool_call" for item in items)
    assert any(item.get("item_type") == "commandExecution" for item in items)
    command_tool = next(
        part
        for part in session["messages"][0]["parts"]
        if part["type"] == "tool_call" and part.get("call_id") == "cmd-1"
    )
    assert command_tool["status"] == "completed"
    assert command_tool["output"] == "updated execution-output.txt"
    assert command_tool["exit_code"] == 0
    assert Path(storage.workspace_store.get_folder_path(project_id), "execution-output.txt").exists()

    assert any(
        item["thread_role"] == "execution"
        and isinstance(item["event"], dict)
        and item["event"].get("type") == "execution_completed"
        for item in published
    )
    assert any(
        item["thread_role"] == "execution"
        and isinstance(item["event"], dict)
        and item["event"].get("type") == "assistant_plan_delta"
        for item in published
    )
    assert any(
        item["thread_role"] == "execution"
        and isinstance(item["event"], dict)
        and item["event"].get("type") == "assistant_tool_result"
        for item in published
    )


def test_execution_session_stays_live_while_background_turn_is_running(
    storage,
    tree_service,
    detail_service,
    chat_event_broker,
    project_id,
    root_node_id,
):
    _confirm_spec(storage, project_id, root_node_id)
    barrier = threading.Event()
    codex_client = FakeExecutionCodexClient(barrier=barrier)
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        max_message_chars=10000,
    )
    finish_service = FinishTaskService(
        storage,
        tree_service,
        detail_service,
        codex_client,
        ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
    )

    finish_service.finish_task(project_id, root_node_id)

    recovered = chat_service.get_session(project_id, root_node_id, thread_role="execution")
    assert recovered["active_turn_id"] is not None
    assert recovered["messages"][0]["status"] == "pending"
    assert recovered["messages"][0]["error"] is None

    barrier.set()
    _wait_for_condition(
        lambda: (
            session := storage.chat_state_store.read_session(
                project_id,
                root_node_id,
                thread_role="execution",
            )
        )
        and session["active_turn_id"] is None
    )


def test_finish_task_background_failure_marks_error_and_completes_without_head_sha(
    storage,
    tree_service,
    detail_service,
    chat_event_broker,
    project_id,
    root_node_id,
):
    _confirm_spec(storage, project_id, root_node_id)
    codex_client = FakeExecutionCodexClient(fail=True)
    finish_service = FinishTaskService(
        storage,
        tree_service,
        detail_service,
        codex_client,
        ThreadLineageService(storage, codex_client, tree_service),
        chat_event_broker,
        chat_timeout=5,
    )

    finish_service.finish_task(project_id, root_node_id)

    _wait_for_condition(
        lambda: (
            state := storage.execution_state_store.read_state(project_id, root_node_id)
        )
        and state["status"] == "failed"
        and state["completed_at"] is not None
    )

    exec_state = storage.execution_state_store.read_state(project_id, root_node_id)
    assert exec_state["head_sha"] is None
    assert exec_state["error_message"] is not None

    session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="execution")
    assert session["messages"][0]["status"] == "error"
    assert session["messages"][0]["error"] is not None


def test_complete_execution_updates_state(finish_service, storage, project_id, root_node_id):
    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "executing",
            "initial_sha": "sha256:start",
            "head_sha": None,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None,
        },
    )

    result = finish_service.complete_execution(project_id, root_node_id, head_sha="sha256:final")

    exec_state = storage.execution_state_store.read_state(project_id, root_node_id)
    assert exec_state["status"] == "completed"
    assert exec_state["head_sha"] == "sha256:final"
    assert result["execution_completed"] is True
    assert result["audit_writable"] is True


def test_complete_execution_fails_not_executing(finish_service, storage, project_id, root_node_id):
    with pytest.raises(FinishTaskNotAllowed, match="No execution state"):
        finish_service.complete_execution(project_id, root_node_id)

    storage.execution_state_store.write_state(
        project_id,
        root_node_id,
        {
            "status": "completed",
            "initial_sha": "sha256:start",
            "head_sha": "sha256:done",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T01:00:00Z",
        },
    )
    with pytest.raises(FinishTaskNotAllowed, match="expected 'executing'"):
        finish_service.complete_execution(project_id, root_node_id, head_sha="sha256:new")


def test_workspace_sha_is_deterministic_and_ignores_planningtree(
    workspace_root: Path,
) -> None:
    from backend.services.workspace_sha import compute_workspace_sha

    (workspace_root / "src.txt").write_text("hello\n", encoding="utf-8")
    (workspace_root / ".planningtree").mkdir(exist_ok=True)
    (workspace_root / ".planningtree" / "ignored.txt").write_text("ignore-me\n", encoding="utf-8")

    first = compute_workspace_sha(workspace_root)

    (workspace_root / ".planningtree" / "ignored.txt").write_text("still ignored\n", encoding="utf-8")
    second = compute_workspace_sha(workspace_root)
    assert second == first

    (workspace_root / "src.txt").write_text("hello world\n", encoding="utf-8")
    third = compute_workspace_sha(workspace_root)
    assert third != first
    assert third.startswith("sha256:")


def test_finish_task_v2_rehearsal_uses_v2_snapshot_without_legacy_conversation_events(
    storage,
    tree_service,
    detail_service,
    chat_event_broker,
    project_id,
    root_node_id,
) -> None:
    _confirm_spec(storage, project_id, root_node_id)
    codex_client = FakeExecutionV2CodexClient()
    thread_lineage_service = ThreadLineageService(storage, codex_client, tree_service)
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        max_message_chars=10000,
    )
    thread_runtime_service_v2, workflow_event_publisher_v2 = _build_v2_runtime(
        storage=storage,
        tree_service=tree_service,
        chat_service=chat_service,
        codex_client=codex_client,
    )
    published: list[dict[str, object]] = []
    original_publish = chat_event_broker.publish

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

    chat_event_broker.publish = capture_publish  # type: ignore[method-assign]
    finish_service = FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=detail_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service_v2=thread_runtime_service_v2,
        workflow_event_publisher_v2=workflow_event_publisher_v2,
        execution_audit_v2_rehearsal_enabled=True,
        rehearsal_workspace_root=Path(storage.workspace_store.get_folder_path(project_id)).parent,
    )

    result = finish_service.finish_task(project_id, root_node_id)
    assert result["execution_started"] is True

    execution_snapshot = _wait_for_condition(
        lambda: (
            snapshot := storage.thread_snapshot_store_v2.read_snapshot(project_id, root_node_id, "execution")
        )
        and snapshot.get("processingState") == "idle"
        and snapshot.get("activeTurnId") is None
        and any(item.get("kind") == "tool" for item in snapshot.get("items", []))
        and (
            exec_state := storage.execution_state_store.read_state(project_id, root_node_id)
        )
        and exec_state.get("status") == "completed"
        and snapshot,
    )
    exec_state = storage.execution_state_store.read_state(project_id, root_node_id)
    assert exec_state is not None
    assert exec_state["status"] == "completed"

    session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="execution")
    assert session["active_turn_id"] is None
    assert session["messages"] == []

    assistant_messages = [
        item for item in execution_snapshot["items"]
        if item.get("kind") == "message" and item.get("role") == "assistant"
    ]
    assert len(assistant_messages) == 1
    assert assistant_messages[0]["text"] == "Implemented the task."

    tool_items = [item for item in execution_snapshot["items"] if item.get("kind") == "tool"]
    assert len(tool_items) == 1
    tool_item = tool_items[0]
    assert tool_item["id"] == "file-1"
    assert tool_item["argumentsText"] == '{"path": "execution-output.txt"}'
    assert tool_item["outputFiles"] == [{"path": "final.txt", "changeType": "updated", "summary": "final"}]
    assert all(item.get("id") != "tool-call:call-1" for item in execution_snapshot["items"])
    assert Path(storage.workspace_store.get_folder_path(project_id), "execution-output.txt").exists()

    legacy_types = {
        "message_created",
        "assistant_delta",
        "assistant_tool_call",
        "assistant_completed",
        "execution_completed",
    }
    assert not any(
        item["thread_role"] == "execution"
        and isinstance(item["event"], dict)
        and item["event"].get("type") in legacy_types
        for item in published
    )


def test_finish_task_v2_raw_event_callbacks_do_not_reenter_thread_binding(
    storage,
    tree_service,
    detail_service,
    chat_event_broker,
    project_id,
    root_node_id,
) -> None:
    _confirm_spec(storage, project_id, root_node_id)
    codex_client = FakeExecutionV2CodexClient()
    original_run_turn_streaming = codex_client.run_turn_streaming
    callback_depth = 0

    def wrapped_run_turn_streaming(prompt: str, **kwargs: object) -> dict[str, str]:
        on_raw_event = kwargs.get("on_raw_event")
        if callable(on_raw_event):
            def wrapped_on_raw_event(raw_event: dict[str, object]) -> None:
                nonlocal callback_depth
                callback_depth += 1
                try:
                    on_raw_event(raw_event)
                finally:
                    callback_depth -= 1

            kwargs = dict(kwargs)
            kwargs["on_raw_event"] = wrapped_on_raw_event
        return original_run_turn_streaming(prompt, **kwargs)

    codex_client.run_turn_streaming = wrapped_run_turn_streaming  # type: ignore[method-assign]
    thread_lineage_service = ThreadLineageService(storage, codex_client, tree_service)
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        max_message_chars=10000,
    )
    thread_runtime_service_v2, workflow_event_publisher_v2 = _build_v2_runtime(
        storage=storage,
        tree_service=tree_service,
        chat_service=chat_service,
        codex_client=codex_client,
    )
    original_get_thread_snapshot = thread_runtime_service_v2._query_service.get_thread_snapshot
    callback_snapshot_calls: list[dict[str, object]] = []

    def wrapped_get_thread_snapshot(
        project_id_arg: str,
        node_id_arg: str,
        thread_role_arg: str,
        **kwargs: object,
    ):
        if callback_depth:
            callback_snapshot_calls.append(
                {
                    "project_id": project_id_arg,
                    "node_id": node_id_arg,
                    "thread_role": thread_role_arg,
                    **kwargs,
                }
            )
            assert kwargs.get("ensure_binding") is False
            assert kwargs.get("allow_thread_read_hydration") is False
        return original_get_thread_snapshot(project_id_arg, node_id_arg, thread_role_arg, **kwargs)

    thread_runtime_service_v2._query_service.get_thread_snapshot = wrapped_get_thread_snapshot  # type: ignore[method-assign]
    finish_service = FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=detail_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service_v2=thread_runtime_service_v2,
        workflow_event_publisher_v2=workflow_event_publisher_v2,
        execution_audit_v2_rehearsal_enabled=True,
        rehearsal_workspace_root=Path(storage.workspace_store.get_folder_path(project_id)).parent,
    )

    result = finish_service.finish_task(project_id, root_node_id)
    assert result["execution_started"] is True
    assert callback_snapshot_calls
    assert all(call["thread_role"] == "execution" for call in callback_snapshot_calls)


def test_finish_task_v2_rehearsal_rejects_workspace_outside_sandbox_root(
    storage,
    tree_service,
    detail_service,
    chat_event_broker,
    project_id,
    root_node_id,
) -> None:
    _confirm_spec(storage, project_id, root_node_id)
    codex_client = FakeExecutionV2CodexClient()
    thread_lineage_service = ThreadLineageService(storage, codex_client, tree_service)
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        max_message_chars=10000,
    )
    thread_runtime_service_v2, workflow_event_publisher_v2 = _build_v2_runtime(
        storage=storage,
        tree_service=tree_service,
        chat_service=chat_service,
        codex_client=codex_client,
    )
    finish_service = FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=detail_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service_v2=thread_runtime_service_v2,
        workflow_event_publisher_v2=workflow_event_publisher_v2,
        execution_audit_v2_rehearsal_enabled=True,
        rehearsal_workspace_root=Path(storage.workspace_store.get_folder_path(project_id)) / "outside-root",
    )

    with pytest.raises(ExecutionAuditRehearsalWorkspaceUnsafe):
        finish_service.finish_task(project_id, root_node_id)


def test_finish_task_v2_production_cuts_execution_and_auto_review_to_v2(
    storage,
    tree_service,
    detail_service,
    chat_event_broker,
    project_id,
    root_node_id,
) -> None:
    _confirm_spec(storage, project_id, root_node_id)
    codex_client = FakeExecutionV2CodexClient()
    thread_lineage_service = ThreadLineageService(storage, codex_client, tree_service)
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        max_message_chars=10000,
    )
    thread_runtime_service_v2, workflow_event_publisher_v2 = _build_v2_runtime(
        storage=storage,
        tree_service=tree_service,
        chat_service=chat_service,
        codex_client=codex_client,
    )
    review_service = ReviewService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service_v2=thread_runtime_service_v2,
        workflow_event_publisher_v2=workflow_event_publisher_v2,
        execution_audit_v2_enabled=True,
    )
    published: list[dict[str, object]] = []
    original_publish = chat_event_broker.publish

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

    chat_event_broker.publish = capture_publish  # type: ignore[method-assign]
    workflow_events: list[tuple[str, dict[str, object]]] = []
    original_workflow_updated = workflow_event_publisher_v2.publish_workflow_updated
    original_detail_invalidate = workflow_event_publisher_v2.publish_detail_invalidate

    def capture_workflow_updated(**kwargs):
        envelope = original_workflow_updated(**kwargs)
        workflow_events.append(("updated", envelope))
        return envelope

    def capture_detail_invalidate(**kwargs):
        envelope = original_detail_invalidate(**kwargs)
        workflow_events.append(("invalidate", envelope))
        return envelope

    workflow_event_publisher_v2.publish_workflow_updated = capture_workflow_updated  # type: ignore[method-assign]
    workflow_event_publisher_v2.publish_detail_invalidate = capture_detail_invalidate  # type: ignore[method-assign]
    finish_service = FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=detail_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        review_service=review_service,
        thread_runtime_service_v2=thread_runtime_service_v2,
        workflow_event_publisher_v2=workflow_event_publisher_v2,
        execution_audit_v2_enabled=True,
    )

    result = finish_service.finish_task(project_id, root_node_id)
    assert result["execution_started"] is True

    execution_snapshot = _wait_for_condition(
        lambda: (
            snapshot := storage.thread_snapshot_store_v2.read_snapshot(project_id, root_node_id, "execution")
        )
        and snapshot.get("processingState") == "idle"
        and snapshot.get("activeTurnId") is None
        and any(item.get("kind") == "tool" for item in snapshot.get("items", []))
        and snapshot
    )
    audit_snapshot = _wait_for_condition(
        lambda: (
            snapshot := storage.thread_snapshot_store_v2.read_snapshot(project_id, root_node_id, "audit")
        )
        and snapshot.get("processingState") == "idle"
        and snapshot.get("activeTurnId") is None
        and any(
            item.get("kind") == "message" and item.get("role") == "assistant"
            for item in snapshot.get("items", [])
        )
        and (
            exec_state := storage.execution_state_store.read_state(project_id, root_node_id)
        )
        and isinstance(exec_state.get("auto_review"), dict)
        and exec_state["auto_review"].get("status") == "completed"
        and snapshot
    )

    exec_state = _wait_for_condition(
        lambda: (
            state := storage.execution_state_store.read_state(project_id, root_node_id)
        )
        and state.get("status") == "review_accepted"
        and state
    )
    assert exec_state is not None
    assert exec_state["auto_review"]["summary"] == "Looks solid overall."

    execution_session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="execution")
    audit_session = storage.chat_state_store.read_session(project_id, root_node_id, thread_role="audit")
    assert execution_session["messages"] == []
    assert audit_session["messages"] == []

    tool_items = [item for item in execution_snapshot["items"] if item.get("kind") == "tool"]
    assert len(tool_items) == 1
    assert tool_items[0]["outputFiles"] == [{"path": "final.txt", "changeType": "updated", "summary": "final"}]

    audit_messages = [
        item for item in audit_snapshot["items"]
        if item.get("kind") == "message" and item.get("role") == "assistant"
    ]
    assert len(audit_messages) == 1
    assert "Looks solid overall." in audit_messages[0]["text"]

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
