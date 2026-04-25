from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.services import planningtree_workspace
from backend.services.project_service import ProjectService


class FakeSessionManager:
    def __init__(self) -> None:
        self.starts: list[dict[str, Any]] = []
        self.injects: list[dict[str, Any]] = []

    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.starts.append(dict(payload or {}))
        return {"thread": {"id": f"thread-{len(self.starts)}"}}

    def thread_inject_items(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.injects.append({"threadId": thread_id, "payload": dict(payload)})
        return {"accepted": True}

    def clear(self) -> None:
        self.starts.clear()
        self.injects.clear()


def _project_with_confirmed_docs(storage: Any, workspace_root: Path) -> tuple[str, str, Path]:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = snapshot["project"]["id"]
    node_id = snapshot["tree_state"]["root_node_id"]
    node_dir = planningtree_workspace.resolve_node_dir(workspace_root, snapshot, node_id)
    assert node_dir is not None
    _write_confirmed_docs(node_dir, revision=2, frame_text="Frame v2", spec_text="Spec v2")
    return project_id, node_id, node_dir


def _write_confirmed_docs(node_dir: Path, *, revision: int, frame_text: str, spec_text: str) -> None:
    (node_dir / "frame.md").write_text(frame_text, encoding="utf-8")
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "revision": revision,
                "confirmed_revision": revision,
                "confirmed_at": "2026-04-24T00:00:00Z",
                "confirmed_content": frame_text,
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "spec.md").write_text(spec_text, encoding="utf-8")
    (node_dir / "spec.meta.json").write_text(
        json.dumps(
            {
                "source_frame_revision": revision,
                "confirmed_at": "2026-04-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _service(storage: Any, fake_session: FakeSessionManager) -> tuple[WorkflowStateRepositoryV2, ThreadBindingServiceV2]:
    repository = WorkflowStateRepositoryV2(storage)
    return repository, ThreadBindingServiceV2(
        repository=repository,
        context_builder=WorkflowContextBuilderV2(storage),
        session_manager=fake_session,
    )


def test_rebase_context_appends_updates_for_all_stale_bindings(storage, workspace_root) -> None:
    project_id, node_id, node_dir = _project_with_confirmed_docs(storage, workspace_root)
    fake_session = FakeSessionManager()
    repository, service = _service(storage, fake_session)
    service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:execution",
    )
    service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="audit",
        idempotency_key="ensure-thread:audit",
    )
    fake_session.clear()
    _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")

    stale_state = service.refresh_context_freshness(project_id, node_id)

    assert stale_state.context_stale is True
    assert [detail.role for detail in stale_state.context_stale_details] == ["audit", "execution"]
    assert stale_state.context_stale_reason == "Multiple workflow context packets changed."

    response = service.rebase_context(
        project_id=project_id,
        node_id=node_id,
        idempotency_key="context-rebase:all",
        expected_workflow_version=stale_state.state_version,
    )

    assert response["rebased"] is True
    assert [binding["role"] for binding in response["updatedBindings"]] == ["audit", "execution"]
    assert response["workflowState"]["context"]["stale"] is False
    assert response["workflowState"]["context"]["staleBindings"] == []
    assert len(fake_session.injects) == 2
    assert {entry["payload"]["items"][0]["metadata"]["packetKind"] for entry in fake_session.injects} == {
        "context_update"
    }
    assert all('"kind":"context_update"' in entry["payload"]["items"][0]["text"] for entry in fake_session.injects)
    assert repository.read_state(project_id, node_id).context_stale is False

    fake_session.clear()
    replay = service.rebase_context(
        project_id=project_id,
        node_id=node_id,
        idempotency_key="context-rebase:all",
        expected_workflow_version=stale_state.state_version,
    )

    assert replay == response
    assert fake_session.injects == []


def test_rebase_context_can_update_a_role_subset_and_keep_remaining_stale(storage, workspace_root) -> None:
    project_id, node_id, node_dir = _project_with_confirmed_docs(storage, workspace_root)
    fake_session = FakeSessionManager()
    repository, service = _service(storage, fake_session)
    service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:execution",
    )
    service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="audit",
        idempotency_key="ensure-thread:audit",
    )
    fake_session.clear()
    _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")
    stale_state = service.refresh_context_freshness(project_id, node_id)

    response = service.rebase_context(
        project_id=project_id,
        node_id=node_id,
        idempotency_key="context-rebase:execution",
        expected_workflow_version=stale_state.state_version,
        roles=["execution"],
    )

    assert [binding["role"] for binding in response["updatedBindings"]] == ["execution"]
    assert response["workflowState"]["context"]["stale"] is True
    assert [detail["role"] for detail in response["workflowState"]["context"]["staleBindings"]] == ["audit"]
    assert len(fake_session.injects) == 1
    assert repository.read_state(project_id, node_id).context_stale_details[0].role == "audit"
