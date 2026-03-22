from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.errors.app_errors import ClarifyGenerationNotAllowed, NodeNotFound
from backend.services.clarify_generation_service import CLARIFY_GEN_STATE_FILE, ClarifyGenerationService
from backend.services.node_detail_service import NodeDetailService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import load_json
from backend.storage.storage import Storage


def _create_project(storage: Storage, workspace_root: str) -> dict:
    project_service = ProjectService(storage)
    return project_service.attach_project_folder(workspace_root)


def _make_codex_mock(
    questions: list[dict[str, str]] | None = None,
) -> MagicMock:
    if questions is None:
        questions = [
            {"field_name": "auth_provider", "question": "Which auth provider should we use?"},
            {"field_name": "storage_backend", "question": "What storage backend?"},
        ]
    mock = MagicMock()
    mock.start_thread.return_value = {"thread_id": "test-thread-456"}
    mock.resume_thread.return_value = {"thread_id": "test-thread-456"}
    mock.run_turn_streaming.return_value = {
        "tool_calls": [
            {
                "tool_name": "emit_clarify_questions",
                "arguments": {"questions": questions},
            }
        ],
        "stdout": "",
    }
    return mock


def test_generate_clarify_returns_accepted(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    result = service.generate_clarify(project_id, root_id)
    assert result["status"] == "accepted"
    assert result["node_id"] == root_id
    assert "job_id" in result


def test_generate_clarify_rejects_double_start(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    barrier = threading.Event()
    codex_mock = _make_codex_mock()

    def slow_run(*args: Any, **kwargs: Any) -> dict:
        barrier.wait(timeout=5)
        return {
            "tool_calls": [
                {
                    "tool_name": "emit_clarify_questions",
                    "arguments": {
                        "questions": [{"field_name": "x", "question": "y?"}]
                    },
                }
            ],
            "stdout": "",
        }

    codex_mock.run_turn_streaming.side_effect = slow_run
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)

    with pytest.raises(ClarifyGenerationNotAllowed, match="already in progress"):
        service.generate_clarify(project_id, root_id)

    barrier.set()


def test_generate_clarify_writes_clarify_json(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    expected_questions = [
        {"field_name": "auth_provider", "question": "Which auth?"},
        {"field_name": "error_handling", "question": "How to handle errors?"},
    ]
    codex_mock = _make_codex_mock(expected_questions)
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    # Verify clarify.json was written
    detail_service = NodeDetailService(storage, tree_service)
    clarify = detail_service.get_clarify(project_id, root_id)
    assert clarify["schema_version"] == 1
    assert len(clarify["questions"]) == 2
    assert clarify["questions"][0]["field_name"] == "auth_provider"
    assert clarify["questions"][0]["answer"] == ""
    assert clarify["questions"][0]["resolution_status"] == "open"
    assert clarify["questions"][1]["field_name"] == "error_handling"


def test_generate_clarify_status_lifecycle(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    # Before generation — idle
    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "idle"

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    # After completion — idle
    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "idle"


def test_generate_clarify_failed_status(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    codex_mock.run_turn_streaming.return_value = {"tool_calls": [], "stdout": ""}
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "failed"
    assert status["error"] is not None


def test_generate_clarify_invalid_node(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]

    codex_mock = _make_codex_mock()
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    with pytest.raises(NodeNotFound):
        service.generate_clarify(project_id, "nonexistent_node")


def test_generate_clarify_stdout_fallback(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Falls back to stdout JSON if no tool call is found."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    codex_mock.run_turn_streaming.return_value = {
        "tool_calls": [],
        "stdout": '[{"field_name": "fallback_q", "question": "Fallback question?"}]',
    }
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    detail_service = NodeDetailService(storage, tree_service)
    clarify = detail_service.get_clarify(project_id, root_id)
    assert len(clarify["questions"]) == 1
    assert clarify["questions"][0]["field_name"] == "fallback_q"
