from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import ANY, MagicMock

import pytest

from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import FrameGenerationNotAllowed, NodeNotFound
from backend.services.frame_generation_service import FRAME_GEN_STATE_FILE, FrameGenerationService
from backend.services.node_document_service import NodeDocumentService
from backend.services.planningtree_workspace import FRAME_FILE_NAME
from backend.services.project_service import ProjectService
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import load_json
from backend.storage.storage import Storage


def _create_project(storage: Storage, workspace_root: str) -> dict:
    project_service = ProjectService(storage)
    return project_service.attach_project_folder(workspace_root)


def _make_codex_mock(frame_content: str = "# Task Title\nGenerated frame") -> MagicMock:
    mock = MagicMock()
    mock.start_thread.return_value = {"thread_id": "audit-thread-123"}
    mock.resume_thread.return_value = {"thread_id": "audit-thread-123"}
    mock.fork_thread.return_value = {"thread_id": "ask-thread-123"}
    mock.run_turn_streaming.return_value = {
        "tool_calls": [
            {
                "tool_name": "emit_frame_content",
                "arguments": {"content": frame_content},
            }
        ],
        "stdout": "",
    }
    return mock


def _make_service(storage: Storage, tree_service: TreeService, codex_mock: MagicMock) -> FrameGenerationService:
    return FrameGenerationService(
        storage,
        tree_service,
        codex_mock,
        thread_lineage_service=ThreadLineageService(storage, codex_mock, tree_service),
        frame_gen_timeout=30,
    )


def test_generate_frame_returns_accepted(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    service = _make_service(storage, tree_service, codex_mock)

    result = service.generate_frame(project_id, root_id)
    assert result["status"] == "accepted"
    assert result["node_id"] == root_id
    assert "job_id" in result
    ask_session = storage.chat_state_store.read_session(project_id, root_id, thread_role="ask_planning")
    assert ask_session["thread_id"] == "ask-thread-123"
    assert ask_session["fork_reason"] == "ask_bootstrap"
    state = load_json(workspace_root / ".planningtree" / "tasks" / root_id / FRAME_GEN_STATE_FILE, default={})
    assert "thread_id" not in state
    codex_mock.fork_thread.assert_called_once()


def test_generate_frame_rebuilds_missing_root_audit_source_before_forking_ask(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    missing_root_audit_thread_id = "missing-root-audit-thread"
    recovered_root_audit_thread_id = "recovered-root-audit-thread"
    codex_mock = _make_codex_mock()

    def resume_thread(thread_id: str, **_: Any) -> dict[str, str]:
        if thread_id == missing_root_audit_thread_id:
            raise CodexTransportError(
                f"no rollout found for thread id {thread_id}",
                "not_found",
            )
        return {"thread_id": thread_id}

    codex_mock.resume_thread.side_effect = resume_thread
    codex_mock.start_thread.side_effect = [{"thread_id": recovered_root_audit_thread_id}]
    codex_mock.fork_thread.return_value = {"thread_id": "ask-thread-recovered"}

    def run_turn_streaming(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("thread_id") == missing_root_audit_thread_id:
            raise CodexTransportError(
                f"thread not found: {missing_root_audit_thread_id}",
                "not_found",
            )
        return {
            "tool_calls": [
                {
                    "tool_name": "emit_frame_content",
                    "arguments": {"content": "# Task Title\nGenerated frame"},
                }
            ],
            "stdout": "",
        }

    codex_mock.run_turn_streaming.side_effect = run_turn_streaming

    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": missing_root_audit_thread_id,
            "thread_role": "audit",
            "fork_reason": "root_bootstrap",
            "lineage_root_thread_id": missing_root_audit_thread_id,
            "messages": [],
        },
        thread_role="audit",
    )

    service = _make_service(storage, tree_service, codex_mock)

    result = service.generate_frame(project_id, root_id)

    assert result["status"] == "accepted"
    audit_session = storage.chat_state_store.read_session(project_id, root_id, thread_role="audit")
    ask_session = storage.chat_state_store.read_session(project_id, root_id, thread_role="ask_planning")
    assert audit_session["thread_id"] == recovered_root_audit_thread_id
    assert audit_session["lineage_root_thread_id"] == recovered_root_audit_thread_id
    assert ask_session["thread_id"] == "ask-thread-recovered"
    codex_mock.start_thread.assert_called_once()
    codex_mock.fork_thread.assert_called_once_with(
        recovered_root_audit_thread_id,
        cwd=str(workspace_root),
        timeout_sec=30,
        base_instructions=ANY,
        dynamic_tools=ANY,
        writable_roots=None,
    )


def test_generate_frame_rejects_double_start(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Second generate call while first is active should raise."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    # Block the codex call to keep the job active
    barrier = threading.Event()
    codex_mock = _make_codex_mock()

    def slow_run(*args: Any, **kwargs: Any) -> dict:
        if kwargs.get("thread_id") == "audit-thread-123":
            return {"tool_calls": [], "stdout": "READY"}
        barrier.wait(timeout=5)
        return {
            "tool_calls": [
                {"tool_name": "emit_frame_content", "arguments": {"content": "# Frame"}}
            ],
            "stdout": "",
        }

    codex_mock.run_turn_streaming.side_effect = slow_run
    service = _make_service(storage, tree_service, codex_mock)

    service.generate_frame(project_id, root_id)

    with pytest.raises(FrameGenerationNotAllowed, match="already in progress"):
        service.generate_frame(project_id, root_id)

    barrier.set()  # Unblock the background thread


def test_generate_frame_writes_content(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    expected_content = "# Task Title\nGenerated login frame"
    codex_mock = _make_codex_mock(expected_content)
    service = _make_service(storage, tree_service, codex_mock)

    service.generate_frame(project_id, root_id)

    # Wait for background thread to complete
    time.sleep(1)

    # Verify frame.md was written
    doc_service = NodeDocumentService(storage)
    doc = doc_service.get_document(project_id, root_id, "frame")
    assert doc["content"] == expected_content


def test_generate_frame_status_lifecycle(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    service = _make_service(storage, tree_service, codex_mock)

    # Before generation — idle
    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "idle"

    service.generate_frame(project_id, root_id)

    # Wait for completion
    time.sleep(1)

    # After completion — idle with last_completed_at set
    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "idle"


def test_generate_frame_failed_status(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    codex_mock.run_turn_streaming.return_value = {"tool_calls": [], "stdout": ""}
    service = _make_service(storage, tree_service, codex_mock)

    service.generate_frame(project_id, root_id)
    time.sleep(1)

    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "failed"
    assert status["error"] is not None


def test_generate_frame_invalid_node(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]

    codex_mock = _make_codex_mock()
    service = _make_service(storage, tree_service, codex_mock)

    with pytest.raises(NodeNotFound):
        service.generate_frame(project_id, "nonexistent_node")


def test_generate_frame_stdout_fallback(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Falls back to stdout if no tool call is found."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    codex_mock.run_turn_streaming.return_value = {
        "tool_calls": [],
        "stdout": "# Task Title\nFallback content",
    }
    service = _make_service(storage, tree_service, codex_mock)

    service.generate_frame(project_id, root_id)
    time.sleep(1)

    doc_service = NodeDocumentService(storage)
    doc = doc_service.get_document(project_id, root_id, "frame")
    assert doc["content"] == "# Task Title\nFallback content"
