from __future__ import annotations

from pathlib import Path

import pytest

from backend.errors.app_errors import ConfirmationNotAllowed
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


FRAME_WITH_UNRESOLVED = """\
# Task Title
Build login page

# Task-Shaping Fields
- target platform:
- auth provider: OAuth2
- storage level:
"""


FRAME_ALL_RESOLVED = """\
# Task Title
Build login page

# Task-Shaping Fields
- target platform: web
- auth provider: OAuth2
- storage level: local
"""


def test_seed_clarify_extracts_unresolved_fields(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    clarify = detail_service.get_clarify(project_id, root_id)
    questions = clarify["questions"]
    field_names = [q["field_name"] for q in questions]

    # "auth provider" has a value, so it should not appear
    assert "target platform" in field_names
    assert "storage level" in field_names
    assert "auth provider" not in field_names
    assert all(q["resolution_status"] == "open" for q in questions)


def test_seed_clarify_no_questions_when_all_resolved(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_ALL_RESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    clarify = detail_service.get_clarify(project_id, root_id)
    assert clarify["questions"] == []


def test_update_clarify_answers(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    updated = detail_service.update_clarify_answers(
        project_id,
        root_id,
        [
            {"field_name": "target platform", "answer": "web + mobile", "resolution_status": "answered"},
            {"field_name": "storage level", "answer": "", "resolution_status": "deferred"},
        ],
    )
    questions = {q["field_name"]: q for q in updated["questions"]}
    assert questions["target platform"]["answer"] == "web + mobile"
    assert questions["target platform"]["resolution_status"] == "answered"
    assert questions["storage level"]["resolution_status"] == "deferred"


def test_confirm_clarify_requires_all_resolved(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # Should fail — questions are open
    with pytest.raises(ConfirmationNotAllowed, match="still open"):
        detail_service.confirm_clarify(project_id, root_id)

    # Resolve all
    detail_service.update_clarify_answers(
        project_id,
        root_id,
        [
            {"field_name": "target platform", "answer": "web", "resolution_status": "answered"},
            {"field_name": "storage level", "answer": "", "resolution_status": "assumed"},
        ],
    )

    result = detail_service.confirm_clarify(project_id, root_id)
    assert result["clarify_confirmed"] is True
    assert result["spec_unlocked"] is True


def test_reseed_preserves_existing_answers(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # Answer one question
    detail_service.update_clarify_answers(
        project_id,
        root_id,
        [{"field_name": "target platform", "answer": "web", "resolution_status": "answered"}],
    )

    # Re-seed (e.g., frame re-confirmed)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    clarify = detail_service.get_clarify(project_id, root_id)
    questions = {q["field_name"]: q for q in clarify["questions"]}

    # Previously answered field should preserve its answer
    assert questions["target platform"]["answer"] == "web"
    assert questions["target platform"]["resolution_status"] == "answered"
    # New/unchanged field should still be open
    assert questions["storage level"]["resolution_status"] == "open"


def test_reseed_preserves_deferred_status_without_answer(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # Mark a question as deferred with NO answer text
    detail_service.update_clarify_answers(
        project_id,
        root_id,
        [{"field_name": "target platform", "answer": "", "resolution_status": "deferred"}],
    )

    # Re-seed (frame re-confirmed)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    clarify = detail_service.get_clarify(project_id, root_id)
    questions = {q["field_name"]: q for q in clarify["questions"]}

    # Deferred status should be preserved even though answer is empty
    assert questions["target platform"]["resolution_status"] == "deferred"
    assert questions["target platform"]["answer"] == ""
