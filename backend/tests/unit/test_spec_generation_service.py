from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.errors.app_errors import NodeNotFound, SpecGenerationNotAllowed
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.spec_generation_service import SpecGenerationService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import atomic_write_json, load_json
from backend.storage.storage import Storage


def _create_project(storage: Storage, workspace_root: str) -> dict:
    project_service = ProjectService(storage)
    return project_service.attach_project_folder(workspace_root)


def _make_codex_mock(spec_content: str = "# Overview\nGenerated spec") -> MagicMock:
    mock = MagicMock()
    mock.start_thread.return_value = {"thread_id": "test-thread-spec-123"}
    mock.resume_thread.return_value = {"thread_id": "test-thread-spec-123"}
    mock.run_turn_streaming.return_value = {
        "tool_calls": [
            {
                "tool_name": "emit_spec_content",
                "arguments": {"content": spec_content},
            }
        ],
        "stdout": "",
    }
    return mock


def _setup_confirmed_frame(
    storage: Storage,
    workspace_root: Path,
    tree_service: TreeService,
) -> tuple[str, str, NodeDetailService, NodeDocumentService]:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    detail_service = NodeDetailService(storage, tree_service)
    doc_service = NodeDocumentService(storage)
    doc_service.put_document(
        project_id,
        root_id,
        "frame",
        "# Task Title\nBuild login page\n\n# Task-Shaping Fields\n- target platform: web\n",
    )
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)
    return project_id, root_id, detail_service, doc_service


def test_generate_spec_returns_accepted(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, _detail_service, _doc_service = _setup_confirmed_frame(
        storage, workspace_root, tree_service
    )
    codex_mock = _make_codex_mock()
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    result = service.generate_spec(project_id, root_id)
    assert result["status"] == "accepted"
    assert result["node_id"] == root_id
    assert "job_id" in result


def test_generate_spec_rejects_double_start(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, _detail_service, _doc_service = _setup_confirmed_frame(
        storage, workspace_root, tree_service
    )
    barrier = threading.Event()
    codex_mock = _make_codex_mock()

    def slow_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        barrier.wait(timeout=5)
        return {
            "tool_calls": [
                {
                    "tool_name": "emit_spec_content",
                    "arguments": {"content": "# Overview\nSlow spec"},
                }
            ],
            "stdout": "",
        }

    codex_mock.run_turn_streaming.side_effect = slow_run
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    service.generate_spec(project_id, root_id)

    with pytest.raises(SpecGenerationNotAllowed, match="already in progress"):
        service.generate_spec(project_id, root_id)

    barrier.set()


def test_generate_spec_requires_confirmed_frame(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    codex_mock = _make_codex_mock()
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    with pytest.raises(SpecGenerationNotAllowed, match="Frame must be confirmed"):
        service.generate_spec(project_id, root_id)


def test_generate_spec_writes_spec_md(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, _detail_service, doc_service = _setup_confirmed_frame(
        storage, workspace_root, tree_service
    )
    codex_mock = _make_codex_mock("# Overview\nGenerated login spec")
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    service.generate_spec(project_id, root_id)
    time.sleep(1)

    doc = doc_service.get_document(project_id, root_id, "spec")
    assert doc["content"] == "# Overview\nGenerated login spec"


def test_generate_spec_status_lifecycle(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, _detail_service, _doc_service = _setup_confirmed_frame(
        storage, workspace_root, tree_service
    )
    codex_mock = _make_codex_mock()
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "idle"

    service.generate_spec(project_id, root_id)
    time.sleep(1)

    status = service.get_generation_status(project_id, root_id)
    assert status["status"] == "idle"


def test_generate_spec_invalid_node(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    snapshot = _create_project(storage, str(workspace_root))
    project_id = snapshot["project"]["id"]

    codex_mock = _make_codex_mock()
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    with pytest.raises(NodeNotFound):
        service.generate_spec(project_id, "nonexistent_node")


def test_write_spec_content_skips_when_source_frame_revision_is_stale(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, detail_service, doc_service = _setup_confirmed_frame(
        storage, workspace_root, tree_service
    )
    codex_mock = _make_codex_mock()
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    doc_service.put_document(project_id, root_id, "spec", "# Existing spec")
    snapshot = storage.project_store.load_snapshot(project_id)
    node_dir = detail_service._resolve_node_dir(snapshot, root_id)
    atomic_write_json(
        node_dir / "spec.meta.json",
        {"source_frame_revision": 2, "confirmed_at": "2026-03-22T00:00:00Z"},
    )

    service._write_spec_content(project_id, root_id, "# New spec", source_frame_revision=1)

    doc = doc_service.get_document(project_id, root_id, "spec")
    assert doc["content"] == "# Existing spec"
    meta = load_json(node_dir / "spec.meta.json", default={})
    assert meta["source_frame_revision"] == 2
    assert meta["confirmed_at"] == "2026-03-22T00:00:00Z"


def test_generate_spec_overwrites_existing_spec_and_resets_confirmation(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, detail_service, doc_service = _setup_confirmed_frame(
        storage, workspace_root, tree_service
    )
    codex_mock = _make_codex_mock("# Overview\nFresh generated spec")
    service = SpecGenerationService(storage, tree_service, codex_mock, spec_gen_timeout=30)

    doc_service.put_document(project_id, root_id, "spec", "# Old spec\nKeep me?")
    snapshot = storage.project_store.load_snapshot(project_id)
    node_dir = detail_service._resolve_node_dir(snapshot, root_id)
    atomic_write_json(
        node_dir / "spec.meta.json",
        {"source_frame_revision": 1, "confirmed_at": "2026-03-22T00:00:00Z"},
    )

    service.generate_spec(project_id, root_id)
    time.sleep(1)

    doc = doc_service.get_document(project_id, root_id, "spec")
    assert doc["content"] == "# Overview\nFresh generated spec"
    meta = load_json(node_dir / "spec.meta.json", default={})
    assert meta["source_frame_revision"] == 1
    assert meta["confirmed_at"] is None


def test_confirm_frame_route_starts_spec_generation_after_apply_and_reconfirm(
    client, workspace_root: Path
) -> None:
    app = client.app
    snapshot = app.state.project_service.attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = app.state.node_document_service
    detail_service = app.state.node_detail_service

    doc_service.put_document(
        project_id,
        root_id,
        "frame",
        "# Task Title\nBuild login page\n\n# Task-Shaping Fields\n- target platform:\n",
    )
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)
    detail_service.update_clarify_answers(
        project_id,
        root_id,
        [{"field_name": "target platform", "custom_answer": "web"}],
    )
    detail_service.apply_clarify_to_frame(project_id, root_id)

    generate_spec_mock = MagicMock(
        return_value={"status": "accepted", "job_id": "sgen_123", "node_id": root_id}
    )
    app.state.spec_generation_service.generate_spec = generate_spec_mock

    response = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/confirm-frame")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_step"] == "spec"
    generate_spec_mock.assert_called_once_with(project_id, root_id)
