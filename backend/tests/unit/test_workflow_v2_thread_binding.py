from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.errors import (
    WorkflowIdempotencyConflictError,
)
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

    def native_rollout_metadata_exists(self, thread_id: str) -> bool:
        return True


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


def _assert_no_workflow_routing_fields(payload: dict[str, Any]) -> None:
    assert "projectId" not in payload
    assert "nodeId" not in payload
    assert "role" not in payload
    assert "idempotencyKey" not in payload


def test_new_thread_starts_injects_context_and_persists_binding(storage, workspace_root) -> None:
    project_id, node_id, _ = _project_with_confirmed_docs(storage, workspace_root)
    fake_session = FakeSessionManager()
    repository, service = _service(storage, fake_session)

    response = service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:new",
        model="gpt-5.4",
        model_provider="openai",
    )

    assert fake_session.starts == [
        {"cwd": str(workspace_root), "model": "gpt-5.4", "modelProvider": "openai"}
    ]
    _assert_no_workflow_routing_fields(fake_session.starts[0])
    assert len(fake_session.injects) == 1
    assert fake_session.injects[0]["threadId"] == "thread-1"
    _assert_no_workflow_routing_fields(fake_session.injects[0]["payload"])
    assert "clientActionId" not in fake_session.injects[0]["payload"]
    injected_item = fake_session.injects[0]["payload"]["items"][0]
    assert injected_item["type"] == "message"
    assert injected_item["role"] == "developer"
    assert injected_item["content"][0]["type"] == "input_text"
    assert "end_turn" not in injected_item
    assert injected_item["metadata"]["workflowContext"] is True
    assert injected_item["metadata"]["contextPayload"]["artifactContext"]["currentContext"]["frame"]["content"] == "Frame v2"
    assert injected_item["workflowContext"]["contextPayload"]["artifactContext"]["currentContext"]["spec"]["content"] == "Spec v2"
    assert injected_item["content"][0]["text"].startswith('<planning_tree_context kind="execution_context"')
    state = repository.read_state(project_id, node_id)
    assert state.thread_id_for("execution") == "thread-1"
    assert state.thread_bindings["execution"].created_from == "new_thread"
    assert state.thread_bindings["execution"].source_versions.frame_version == 2
    raw_state = json.loads(repository.canonical_path(project_id, node_id).read_text(encoding="utf-8"))
    assert raw_state["thread_bindings"]["execution"]["threadId"] == "thread-1"
    assert "thread_id" not in raw_state["thread_bindings"]["execution"]
    assert response["binding"]["threadId"] == "thread-1"
    assert response["workflowState"]["threads"]["execution"] == "thread-1"


def test_matching_existing_binding_reuses_thread_without_inject(storage, workspace_root) -> None:
    project_id, node_id, _ = _project_with_confirmed_docs(storage, workspace_root)
    fake_session = FakeSessionManager()
    _, service = _service(storage, fake_session)
    service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:first",
    )
    fake_session.clear()

    response = service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:second",
    )

    assert fake_session.starts == []
    assert fake_session.injects == []
    assert response["binding"]["threadId"] == "thread-1"


def test_changed_context_auto_updates_binding(storage, workspace_root) -> None:
    project_id, node_id, node_dir = _project_with_confirmed_docs(storage, workspace_root)
    fake_session = FakeSessionManager()
    repository, service = _service(storage, fake_session)
    first = service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:first",
    )
    fake_session.clear()
    _write_confirmed_docs(node_dir, revision=3, frame_text="Frame v3", spec_text="Spec v3")

    response = service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:update",
    )

    assert fake_session.starts == []
    assert len(fake_session.injects) == 1
    _assert_no_workflow_routing_fields(fake_session.injects[0]["payload"])
    item = fake_session.injects[0]["payload"]["items"][0]
    assert item["type"] == "message"
    assert item["role"] == "developer"
    assert item["metadata"]["packetKind"] == "execution_context"
    assert item["metadata"]["contextPayload"]["artifactContext"]["currentContext"]["frame"]["content"] == "Frame v3"
    assert '"kind":"execution_context"' in item["content"][0]["text"]
    assert response["binding"]["threadId"] == "thread-1"
    assert response["binding"]["contextPacketHash"] != first["binding"]["contextPacketHash"]
    state = repository.read_state(project_id, node_id)
    assert state.thread_bindings["execution"].context_packet_hash == response["binding"]["contextPacketHash"]


def test_idempotency_replay_and_conflict(storage, workspace_root) -> None:
    project_id, node_id, _ = _project_with_confirmed_docs(storage, workspace_root)
    fake_session = FakeSessionManager()
    _, service = _service(storage, fake_session)
    first = service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:idempotent",
    )
    fake_session.clear()

    replay = service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-thread:idempotent",
    )

    assert replay["binding"]["threadId"] == first["binding"]["threadId"]
    assert replay == first
    assert fake_session.starts == []
    assert fake_session.injects == []
    with pytest.raises(WorkflowIdempotencyConflictError) as exc_info:
        service.ensure_thread(
            project_id=project_id,
            node_id=node_id,
            role="execution",
            idempotency_key="ensure-thread:idempotent",
            model="gpt-5.4",
        )
    assert exc_info.value.code == "ERR_WORKFLOW_IDEMPOTENCY_CONFLICT"


def test_clears_stale_binding_when_native_rollout_is_missing_for_thread_id(
    storage,
    workspace_root,
) -> None:
    ghost_uuid = "f47ac10b-58cc-4372-a567-0e02b2c3d479"

    class FakeNativeMissingForGhost(FakeSessionManager):
        def native_rollout_metadata_exists(self, thread_id: str) -> bool:
            return str(thread_id or "").strip() != ghost_uuid

    project_id, node_id, _ = _project_with_confirmed_docs(storage, workspace_root)
    fake = FakeNativeMissingForGhost()
    repository, service = _service(storage, fake)
    service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-ghost-1",
        model="m",
        model_provider="o",
    )
    state = repository.read_state(project_id, node_id)
    binding = state.thread_bindings["execution"]
    ghost_binding = binding.model_copy(update={"thread_id": ghost_uuid})
    repository.write_state(
        project_id,
        node_id,
        state.model_copy(
            deep=True,
            update={
                "thread_bindings": {**state.thread_bindings, "execution": ghost_binding},
            },
        ),
    )
    fake.clear()

    service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-ghost-2",
        model="m",
        model_provider="o",
    )
    assert len(fake.starts) == 1
    _assert_no_workflow_routing_fields(fake.starts[0])
    assert fake.injects[-1]["threadId"] == "thread-1"
    _assert_no_workflow_routing_fields(fake.injects[-1]["payload"])
    reloaded = repository.read_state(project_id, node_id)
    assert reloaded.thread_bindings["execution"].thread_id == "thread-1"
