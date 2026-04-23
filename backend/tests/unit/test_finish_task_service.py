"""Tests for FinishTaskService execution lifecycle and state transitions."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_actor_runtime_v3 import ThreadActorRuntimeV3
from backend.conversation.services.thread_checkpoint_policy_v3 import ThreadCheckpointPolicyV3
from backend.conversation.services.thread_query_service_v3 import ThreadQueryServiceV3
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.services.thread_replay_buffer_service_v3 import ThreadReplayBufferServiceV3
from backend.conversation.services.thread_runtime_service_v3 import ThreadRuntimeServiceV3
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
        on_raw_event = kwargs.get("on_raw_event")
        output_schema = kwargs.get("output_schema")

        if callable(on_raw_event):
            if self.fail:
                raise CodexTransportError("Execution failed", "rpc_error")

            if output_schema is not None:
                rendered_message = "## Automated Local Review\n\nLooks solid overall."
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
    assert ThreadRuntimeServiceV3._tool_call_arguments_text(arguments) == patch_body


def test_thread_runtime_service_matches_provisional_call_from_item_id_when_call_id_missing() -> None:
    patch_body = "*** Begin Patch\n*** Update File: src/app.ts\n@@\n+const ok = true\n*** End Patch"
    raw_event = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "fileChange",
                "id": "call_patch_123",
            }
        },
    }
    provisional_tool_calls = {
        "call_patch_123": {
            "callId": "call_patch_123",
            "toolName": "apply_patch",
            "arguments": {"input": patch_body, "path": "src/app.ts"},
            "matched": False,
        }
    }

    ThreadRuntimeServiceV3._enrich_started_item_from_provisional_call(raw_event, provisional_tool_calls)

    item = raw_event["params"]["item"]
    assert item["callId"] == "call_patch_123"
    assert item["toolName"] == "apply_patch"
    assert item["argumentsText"] == patch_body
    assert provisional_tool_calls["call_patch_123"]["matched"] is True


def _build_runtime_services(
    *,
    storage,
    tree_service,
    codex_client,
    chat_event_broker,
):
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
    request_ledger_service = RequestLedgerServiceV3()
    thread_registry_service = ThreadRegistryService(storage.thread_registry_store)
    thread_lineage_service.set_thread_registry_service(thread_registry_service)
    conversation_event_broker = ChatEventBroker()
    workflow_event_broker = GlobalEventBroker()
    query_service = ThreadQueryServiceV3(
        storage=storage,
        chat_service=chat_service,
        thread_lineage_service=thread_lineage_service,
        codex_client=codex_client,
        snapshot_store_v3=storage.thread_snapshot_store_v3,
        snapshot_store_v2=storage.thread_snapshot_store_v2,
        registry_service_v2=thread_registry_service,
        request_ledger_service=request_ledger_service,
        thread_event_broker=conversation_event_broker,
        replay_buffer_service=ThreadReplayBufferServiceV3(max_events=500, ttl_seconds=15 * 60),
        mini_journal_store_v3=storage.thread_mini_journal_store_v3,
        event_log_store_v3=storage.thread_event_log_store_v3,
        checkpoint_policy_v3=ThreadCheckpointPolicyV3(timer_checkpoint_ms=5000),
        actor_runtime_v3=ThreadActorRuntimeV3(),
        thread_actor_mode="off",
    )
    runtime = ThreadRuntimeServiceV3(
        storage=storage,
        tree_service=tree_service,
        chat_service=chat_service,
        codex_client=codex_client,
        query_service=query_service,
        request_ledger_service=request_ledger_service,
        chat_timeout=5,
        max_message_chars=10000,
        thread_actor_mode="off",
    )
    workflow_publisher = WorkflowEventPublisher(workflow_event_broker)
    return thread_lineage_service, chat_service, runtime, query_service, workflow_publisher


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
    (
        thread_lineage_service,
        chat_service,
        thread_runtime_service,
        thread_query_service,
        workflow_event_publisher,
    ) = _build_runtime_services(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        chat_event_broker=chat_event_broker,
    )
    return FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=detail_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service=thread_runtime_service,
        thread_query_service=thread_query_service,
        workflow_event_publisher=workflow_event_publisher,
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
    (
        thread_lineage_service,
        chat_service,
        thread_runtime_service,
        thread_query_service,
        workflow_event_publisher,
    ) = _build_runtime_services(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        chat_event_broker=chat_event_broker,
    )
    finish_service = FinishTaskService(
        storage,
        tree_service,
        detail_service,
        codex_client,
        thread_lineage_service,
        chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service=thread_runtime_service,
        thread_query_service=thread_query_service,
        workflow_event_publisher=workflow_event_publisher,
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

    execution_registry = storage.thread_registry_store.read_entry(project_id, root_node_id, "execution")
    assert execution_registry["threadId"] == "exec-fork-thread-1"
    execution_snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, root_node_id, "execution")
    assert execution_snapshot["threadId"] == "exec-fork-thread-1"
    assert execution_snapshot["activeTurnId"] is not None
    assert execution_snapshot["processingState"] == "running"
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
        and (
            snapshot := storage.thread_snapshot_store_v3.read_snapshot(project_id, root_node_id, "execution")
        )
        and snapshot.get("activeTurnId") is None
        and snapshot.get("processingState") == "idle"
    )

    snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, root_node_id, "execution")
    assistant_messages = [
        item
        for item in snapshot.get("items", [])
        if isinstance(item, dict) and item.get("kind") == "message" and item.get("role") == "assistant"
    ]
    assert assistant_messages
    assert "Implemented the task." in str(assistant_messages[-1].get("text") or "")
    assert Path(storage.workspace_store.get_folder_path(project_id), "execution-output.txt").exists()


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
    (
        thread_lineage_service,
        chat_service,
        thread_runtime_service,
        thread_query_service,
        workflow_event_publisher,
    ) = _build_runtime_services(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        chat_event_broker=chat_event_broker,
    )
    finish_service = FinishTaskService(
        storage,
        tree_service,
        detail_service,
        codex_client,
        thread_lineage_service,
        chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service=thread_runtime_service,
        thread_query_service=thread_query_service,
        workflow_event_publisher=workflow_event_publisher,
    )

    finish_service.finish_task(project_id, root_node_id)

    recovered_snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, root_node_id, "execution")
    assert recovered_snapshot["activeTurnId"] is not None
    assert recovered_snapshot["processingState"] == "running"

    barrier.set()
    _wait_for_condition(
        lambda: (
            snapshot := storage.thread_snapshot_store_v3.read_snapshot(
                project_id,
                root_node_id,
                "execution",
            )
        )
        and snapshot["activeTurnId"] is None
        and snapshot.get("processingState") == "idle"
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
    (
        thread_lineage_service,
        chat_service,
        thread_runtime_service,
        thread_query_service,
        workflow_event_publisher,
    ) = _build_runtime_services(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        chat_event_broker=chat_event_broker,
    )
    finish_service = FinishTaskService(
        storage,
        tree_service,
        detail_service,
        codex_client,
        thread_lineage_service,
        chat_event_broker,
        chat_timeout=5,
        chat_service=chat_service,
        thread_runtime_service=thread_runtime_service,
        thread_query_service=thread_query_service,
        workflow_event_publisher=workflow_event_publisher,
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

    snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, root_node_id, "execution")
    assert snapshot["activeTurnId"] is None
    assert snapshot["processingState"] == "idle"
    error_items = [
        item
        for item in snapshot.get("items", [])
        if isinstance(item, dict) and item.get("kind") == "error"
    ]
    assert error_items


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
