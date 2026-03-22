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
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import atomic_write_json, load_json
from backend.storage.storage import Storage


def _create_project(storage: Storage, workspace_root: str) -> dict:
    project_service = ProjectService(storage)
    return project_service.attach_project_folder(workspace_root)


def _make_codex_mock(
    questions: list[dict[str, Any]] | None = None,
) -> MagicMock:
    if questions is None:
        questions = [
            {
                "field_name": "auth_provider",
                "question": "Which auth provider should we use?",
                "why_it_matters": "Affects security model",
                "current_value": "",
                "options": [
                    {"id": "oauth2", "label": "OAuth2", "value": "OAuth2", "rationale": "Standard", "recommended": True},
                    {"id": "api_key", "label": "API Key", "value": "API Key", "rationale": "Simple", "recommended": False},
                ],
                "allow_custom": True,
            },
            {
                "field_name": "storage_backend",
                "question": "What storage backend?",
                "why_it_matters": "Affects persistence",
                "current_value": "",
                "options": [
                    {"id": "local_disk", "label": "Local Disk", "value": "Local Disk", "rationale": "Simple", "recommended": True},
                    {"id": "cloud_s3", "label": "Cloud S3", "value": "Cloud S3", "rationale": "Scalable", "recommended": False},
                ],
                "allow_custom": True,
            },
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
                        "questions": [{
                            "field_name": "x",
                            "question": "y?",
                            "options": [],
                        }]
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
        {
            "field_name": "auth_provider",
            "question": "Which auth?",
            "why_it_matters": "Security",
            "current_value": "",
            "options": [
                {"id": "oauth2", "label": "OAuth2", "value": "OAuth2", "rationale": "Standard", "recommended": True},
            ],
            "allow_custom": True,
        },
        {
            "field_name": "error_handling",
            "question": "How to handle errors?",
            "why_it_matters": "UX",
            "current_value": "",
            "options": [
                {"id": "toast", "label": "Toast", "value": "Toast", "rationale": "Non-blocking", "recommended": True},
            ],
            "allow_custom": True,
        },
    ]
    codex_mock = _make_codex_mock(expected_questions)
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    # Verify clarify.json was written
    detail_service = NodeDetailService(storage, tree_service)
    clarify = detail_service.get_clarify(project_id, root_id)
    assert clarify["schema_version"] == 2
    assert len(clarify["questions"]) == 2
    assert clarify["questions"][0]["field_name"] == "auth_provider"
    assert clarify["questions"][0]["selected_option_id"] is None
    assert clarify["questions"][0]["custom_answer"] == ""
    assert clarify["questions"][0]["allow_custom"] is True
    assert len(clarify["questions"][0]["options"]) == 1
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
    assert clarify["questions"][0]["selected_option_id"] is None
    assert clarify["questions"][0]["custom_answer"] == ""


def test_generate_clarify_zero_questions_auto_confirms(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Zero questions from AI auto-confirms clarify and unlocks spec."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    # Confirm frame first so detail_state can derive spec_unlocked
    detail_service = NodeDetailService(storage, tree_service)
    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", "# Task Title\nTest\n")
    detail_service.confirm_frame(project_id, root_id)

    codex_mock = _make_codex_mock(questions=[])
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    clarify = detail_service.get_clarify(project_id, root_id)
    assert clarify["questions"] == []
    assert clarify["confirmed_at"] is not None
    assert clarify["confirmed_revision"] == 1

    # Spec should be unlocked
    state = detail_service.get_detail_state(project_id, root_id)
    assert state["clarify_confirmed"] is True
    assert state["spec_unlocked"] is True


def test_generate_clarify_uses_confirmed_content_not_draft(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Generation uses confirmed frame content, not post-confirm draft edits."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    detail_service = NodeDetailService(storage, tree_service)
    doc_service = NodeDocumentService(storage)

    # Write and confirm frame
    confirmed_text = "# Task Title\nConfirmed Content\n"
    doc_service.put_document(project_id, root_id, "frame", confirmed_text)
    detail_service.confirm_frame(project_id, root_id)

    # Write draft edit AFTER confirm (this changes frame.md but not confirmed_content)
    doc_service.put_document(project_id, root_id, "frame", "# Task Title\nDraft Content\n")

    # Capture what the AI receives
    received_prompts: list[str] = []
    codex_mock = _make_codex_mock()

    def capture_run(prompt: str, **kwargs: Any) -> dict:
        received_prompts.append(prompt)
        return {
            "tool_calls": [
                {
                    "tool_name": "emit_clarify_questions",
                    "arguments": {"questions": [{"field_name": "q1", "question": "Q?", "options": []}]},
                }
            ],
            "stdout": "",
        }

    codex_mock.run_turn_streaming.side_effect = capture_run
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    assert len(received_prompts) == 1
    assert "Confirmed Content" in received_prompts[0]
    assert "Draft Content" not in received_prompts[0]


def test_generate_clarify_preserves_custom_answer_on_regenerate(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Regeneration preserves custom_answer from previous generation."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    detail_service = NodeDetailService(storage, tree_service)
    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", "# Task Title\nTest\n")
    detail_service.confirm_frame(project_id, root_id)

    # Seed initial clarify with a question
    codex_mock = _make_codex_mock([
        {
            "field_name": "auth_provider",
            "question": "Which auth?",
            "options": [
                {"id": "oauth2", "label": "OAuth2", "value": "OAuth2", "rationale": "Standard", "recommended": True},
            ],
        },
    ])
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    # Set custom answer
    detail_service.update_clarify_answers(project_id, root_id, [
        {"field_name": "auth_provider", "custom_answer": "custom auth method"},
    ])

    # Regenerate — AI returns the same field
    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    clarify = detail_service.get_clarify(project_id, root_id)
    assert len(clarify["questions"]) == 1
    assert clarify["questions"][0]["field_name"] == "auth_provider"
    assert clarify["questions"][0]["custom_answer"] == "custom auth method"


def test_generate_clarify_preserves_selected_option_when_still_available(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Regeneration preserves selected_option_id if option ID still exists in new options."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    detail_service = NodeDetailService(storage, tree_service)
    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", "# Task Title\nTest\n")
    detail_service.confirm_frame(project_id, root_id)

    # First generation with options
    first_questions = [
        {
            "field_name": "auth_provider",
            "question": "Which auth?",
            "options": [
                {"id": "oauth2", "label": "OAuth2", "value": "OAuth2", "rationale": "Standard", "recommended": True},
                {"id": "api_key", "label": "API Key", "value": "API Key", "rationale": "Simple", "recommended": False},
            ],
        },
    ]
    codex_mock = _make_codex_mock(first_questions)
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    # Select an option
    detail_service.update_clarify_answers(project_id, root_id, [
        {"field_name": "auth_provider", "selected_option_id": "oauth2"},
    ])

    # Regenerate with same option still available
    second_questions = [
        {
            "field_name": "auth_provider",
            "question": "Which auth? (revised)",
            "options": [
                {"id": "oauth2", "label": "OAuth2", "value": "OAuth2", "rationale": "Revised", "recommended": True},
                {"id": "saml", "label": "SAML", "value": "SAML", "rationale": "Enterprise", "recommended": False},
            ],
        },
    ]
    codex_mock.run_turn_streaming.return_value = {
        "tool_calls": [{"tool_name": "emit_clarify_questions", "arguments": {"questions": second_questions}}],
        "stdout": "",
    }
    service.generate_clarify(project_id, root_id)
    time.sleep(1)

    clarify = detail_service.get_clarify(project_id, root_id)
    assert clarify["questions"][0]["selected_option_id"] == "oauth2"


def test_stale_job_does_not_overwrite_newer_clarify(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """If frame is re-confirmed during generation, old job skips write."""
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    detail_service = NodeDetailService(storage, tree_service)
    doc_service = NodeDocumentService(storage)

    # Write and confirm frame (revision 1)
    doc_service.put_document(project_id, root_id, "frame", "# Task Title\nFirst\n")
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    barrier = threading.Event()
    codex_mock = _make_codex_mock()

    def slow_run(*args: Any, **kwargs: Any) -> dict:
        barrier.wait(timeout=5)
        return {
            "tool_calls": [
                {
                    "tool_name": "emit_clarify_questions",
                    "arguments": {
                        "questions": [{"field_name": "stale_q", "question": "Stale?", "options": []}]
                    },
                }
            ],
            "stdout": "",
        }

    codex_mock.run_turn_streaming.side_effect = slow_run
    service = ClarifyGenerationService(storage, tree_service, codex_mock, clarify_gen_timeout=30)

    # Start generation (captures source_frame_revision = 1)
    service.generate_clarify(project_id, root_id)

    # Re-confirm frame while generation is running (bumps to revision 2)
    doc_service.put_document(project_id, root_id, "frame", "# Task Title\nSecond\n")
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # Let the old job complete
    barrier.set()
    time.sleep(1)

    # The stale job should NOT have overwritten the newer clarify
    clarify = detail_service.get_clarify(project_id, root_id)
    # The newer clarify was seeded by the second confirm_frame — it should have
    # source_frame_revision == 2, not the stale job's revision 1
    assert clarify["source_frame_revision"] == 2
    # The stale question should NOT be present
    field_names = [q["field_name"] for q in clarify["questions"]]
    assert "stale_q" not in field_names
