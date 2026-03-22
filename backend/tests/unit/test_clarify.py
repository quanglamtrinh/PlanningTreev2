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
    # New schema: questions have choice-based fields
    for q in questions:
        assert q["selected_option_id"] is None
        assert q["custom_answer"] == ""
        assert q["allow_custom"] is True
        assert isinstance(q["options"], list)


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


def test_update_clarify_with_custom_answer(
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
            {"field_name": "target platform", "custom_answer": "web + mobile"},
            {"field_name": "storage level", "custom_answer": "cloud"},
        ],
    )
    questions = {q["field_name"]: q for q in updated["questions"]}
    assert questions["target platform"]["custom_answer"] == "web + mobile"
    assert questions["target platform"]["selected_option_id"] is None
    assert questions["storage level"]["custom_answer"] == "cloud"


def test_update_clarify_with_selected_option(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Selecting an option clears custom_answer (mutual exclusivity)."""
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # Manually add options to clarify for testing
    snapshot = storage.project_store.load_snapshot(project_id)
    node_dir = detail_service._resolve_node_dir(snapshot, root_id)
    clarify = detail_service._load_clarify(node_dir)
    for q in clarify["questions"]:
        if q["field_name"] == "target platform":
            q["options"] = [
                {"id": "web", "label": "Web", "value": "web", "rationale": "Standard", "recommended": True},
                {"id": "mobile", "label": "Mobile", "value": "mobile", "rationale": "Mobile first", "recommended": False},
            ]
            q["custom_answer"] = "some draft"
    detail_service._save_clarify(node_dir, clarify)

    # Select an option — should clear custom_answer
    updated = detail_service.update_clarify_answers(
        project_id,
        root_id,
        [{"field_name": "target platform", "selected_option_id": "web"}],
    )
    questions = {q["field_name"]: q for q in updated["questions"]}
    assert questions["target platform"]["selected_option_id"] == "web"
    assert questions["target platform"]["custom_answer"] == ""


def test_clear_selection_reopens_question(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Sending both null clears the question (reopen)."""
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)

    detail_service = NodeDetailService(storage, tree_service)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # First set a custom answer
    detail_service.update_clarify_answers(
        project_id, root_id,
        [{"field_name": "target platform", "custom_answer": "web"}],
    )

    # Now clear both — should reopen
    updated = detail_service.update_clarify_answers(
        project_id, root_id,
        [{"field_name": "target platform", "selected_option_id": None, "custom_answer": ""}],
    )
    questions = {q["field_name"]: q for q in updated["questions"]}
    assert questions["target platform"]["selected_option_id"] is None
    assert questions["target platform"]["custom_answer"] == ""


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

    # Should fail — questions are unresolved (no option or custom answer)
    with pytest.raises(ConfirmationNotAllowed, match="still open"):
        detail_service.confirm_clarify(project_id, root_id)

    # Resolve all via custom_answer
    detail_service.update_clarify_answers(
        project_id,
        root_id,
        [
            {"field_name": "target platform", "custom_answer": "web"},
            {"field_name": "storage level", "custom_answer": "local"},
        ],
    )

    result = detail_service.confirm_clarify(project_id, root_id)
    assert result["clarify_confirmed"] is True
    assert result["spec_unlocked"] is True


def test_reseed_preserves_custom_answer(
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
        [{"field_name": "target platform", "custom_answer": "web"}],
    )

    # Re-seed (e.g., frame re-confirmed)
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    clarify = detail_service.get_clarify(project_id, root_id)
    questions = {q["field_name"]: q for q in clarify["questions"]}

    # Previously answered field should preserve its custom answer
    assert questions["target platform"]["custom_answer"] == "web"
    # New/unchanged field should still be unresolved
    assert questions["storage level"]["custom_answer"] == ""
    assert questions["storage level"]["selected_option_id"] is None


def test_schema_version_is_2(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Seeded clarify should have schema_version 2."""
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
    assert clarify["schema_version"] == 2
    assert "confirmed_revision" in clarify
