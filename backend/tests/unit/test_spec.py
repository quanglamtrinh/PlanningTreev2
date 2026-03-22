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
"""


def _setup_confirmed_clarify(
    storage: Storage,
    workspace_root: Path,
    tree_service: TreeService,
) -> tuple[str, str, NodeDetailService, NodeDocumentService]:
    """Create a project and advance the workflow through confirmed clarify."""
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)

    # Write and confirm frame
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # Answer all clarify questions and confirm
    detail_service.update_clarify_answers(
        project_id,
        root_id,
        [{"field_name": "target platform", "custom_answer": "web"}],
    )
    detail_service.confirm_clarify(project_id, root_id)

    return project_id, root_id, detail_service, doc_service


def test_confirm_spec_requires_clarify_confirmed(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)

    # Write frame content and confirm frame
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    # Write spec content
    doc_service.put_document(project_id, root_id, "spec", "# Spec content")

    # Should fail — clarify not confirmed
    with pytest.raises(ConfirmationNotAllowed, match="Clarify must be confirmed"):
        detail_service.confirm_spec(project_id, root_id)


def test_confirm_spec_requires_non_empty_content(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, detail_service, _doc_service = _setup_confirmed_clarify(
        storage, workspace_root, tree_service
    )

    # spec.md is empty by default
    with pytest.raises(ConfirmationNotAllowed, match="empty spec"):
        detail_service.confirm_spec(project_id, root_id)


def test_confirm_spec_succeeds(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, detail_service, doc_service = _setup_confirmed_clarify(
        storage, workspace_root, tree_service
    )

    doc_service.put_document(project_id, root_id, "spec", "# Spec\nFull spec content here.")
    result = detail_service.confirm_spec(project_id, root_id)

    assert result["spec_confirmed"] is True
    assert result["spec_stale"] is False


def test_frame_reconfirm_relocks_spec(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Re-confirming frame re-seeds clarify (confirmed_at=None), which re-locks spec."""
    project_id, root_id, detail_service, doc_service = _setup_confirmed_clarify(
        storage, workspace_root, tree_service
    )

    # Confirm spec
    doc_service.put_document(project_id, root_id, "spec", "# Spec\nContent.")
    detail_service.confirm_spec(project_id, root_id)

    # Re-confirm frame — this re-seeds clarify, resetting confirmed_at
    doc_service.put_document(project_id, root_id, "frame", FRAME_WITH_UNRESOLVED)
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)

    state = detail_service.get_detail_state(project_id, root_id)
    # Clarify was re-seeded → spec locked (not stale)
    assert state["spec_unlocked"] is False
    assert state["clarify_confirmed"] is False
    # Spec content preserved on disk (not wiped)
    spec = doc_service.get_document(project_id, root_id, "spec")
    assert spec["content"] == "# Spec\nContent."


def test_spec_stale_detection(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Spec is stale when its source revisions are behind the current confirmed revisions."""
    project_id, root_id, detail_service, doc_service = _setup_confirmed_clarify(
        storage, workspace_root, tree_service
    )

    # Confirm spec at frame revision 1
    doc_service.put_document(project_id, root_id, "spec", "# Spec\nContent.")
    result = detail_service.confirm_spec(project_id, root_id)
    assert result["spec_stale"] is False

    # Manually bump frame confirmed_revision to simulate a frame change
    # without re-seeding clarify (future AI-driven flow)
    snapshot = storage.project_store.load_snapshot(project_id)
    node_dir = detail_service._resolve_node_dir(snapshot, node_id=root_id)
    frame_meta = detail_service._load_frame_meta(node_dir)
    frame_meta["revision"] = 2
    frame_meta["confirmed_revision"] = 2
    detail_service._save_frame_meta(node_dir, frame_meta)

    state = detail_service.get_detail_state(project_id, root_id)
    assert state["spec_stale"] is True


def test_spec_stale_after_clarify_reconfirm(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    """Spec detects staleness when clarify is re-confirmed (no frame change)."""
    project_id, root_id, detail_service, doc_service = _setup_confirmed_clarify(
        storage, workspace_root, tree_service
    )

    # Confirm spec (clarify confirmed_revision == 1)
    doc_service.put_document(project_id, root_id, "spec", "# Spec\nContent.")
    result = detail_service.confirm_spec(project_id, root_id)
    assert result["spec_stale"] is False

    # Re-confirm clarify (bumps confirmed_revision to 2) without any frame change
    detail_service.confirm_clarify(project_id, root_id)

    state = detail_service.get_detail_state(project_id, root_id)
    assert state["spec_stale"] is True


def test_detail_state_spec_unlocked_after_clarify_confirm(
    storage: Storage, workspace_root: Path, tree_service: TreeService
) -> None:
    project_id, root_id, detail_service, _doc_service = _setup_confirmed_clarify(
        storage, workspace_root, tree_service
    )

    state = detail_service.get_detail_state(project_id, root_id)
    assert state["spec_unlocked"] is True
    assert state["spec_confirmed"] is False
    assert state["clarify_confirmed"] is True
