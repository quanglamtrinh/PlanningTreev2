from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.business.workflow_v2.artifact_orchestrator import ArtifactOrchestratorV2
from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.events import WorkflowEventPublisherV2
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService


class RecordingBroker:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


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


class FakeGenerationService:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.starts: list[tuple[str, str]] = []

    def generate_frame(self, project_id: str, node_id: str) -> dict[str, Any]:
        return self._start(project_id, node_id)

    def generate_clarify(self, project_id: str, node_id: str) -> dict[str, Any]:
        return self._start(project_id, node_id)

    def generate_spec(self, project_id: str, node_id: str) -> dict[str, Any]:
        return self._start(project_id, node_id)

    def get_generation_status(self, project_id: str, node_id: str) -> dict[str, Any]:
        return {
            "status": "idle",
            "job_id": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
        }

    def _start(self, project_id: str, node_id: str) -> dict[str, Any]:
        self.starts.append((project_id, node_id))
        return {
            "status": "accepted",
            "job_id": f"{self.kind}-job-{len(self.starts)}",
            "node_id": node_id,
        }


class FakeSplitService:
    def split_node(self, project_id: str, node_id: str, mode: str) -> dict[str, Any]:
        return {
            "status": "accepted",
            "job_id": "split-job-1",
            "node_id": node_id,
            "mode": mode,
        }

    def get_split_status(self, project_id: str) -> dict[str, Any]:
        return {
            "status": "idle",
            "job_id": None,
            "node_id": None,
            "mode": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
        }


def _create_project(storage: Any, workspace_root: Path) -> tuple[str, str]:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def _confirm_frame(
    storage: Any,
    detail_service: NodeDetailService,
    project_id: str,
    node_id: str,
    content: str,
) -> None:
    NodeDocumentService(storage).put_document(project_id, node_id, "frame", content)
    detail_service.bump_frame_revision(project_id, node_id)
    detail_service.confirm_frame(project_id, node_id)


def _orchestrator(
    storage: Any,
    *,
    frame_service: FakeGenerationService | None = None,
    broker: RecordingBroker | None = None,
) -> tuple[ArtifactOrchestratorV2, WorkflowStateRepositoryV2, ThreadBindingServiceV2, RecordingBroker]:
    tree_service = TreeService()
    repository = WorkflowStateRepositoryV2(storage)
    event_broker = broker or RecordingBroker()
    publisher = WorkflowEventPublisherV2(event_broker)  # type: ignore[arg-type]
    binding_service = ThreadBindingServiceV2(
        repository=repository,
        context_builder=WorkflowContextBuilderV2(storage),
        session_manager=FakeSessionManager(),
        event_publisher=publisher,
    )
    detail_service = NodeDetailService(storage, tree_service)
    return (
        ArtifactOrchestratorV2(
            repository=repository,
            thread_binding_service=binding_service,
            event_publisher=publisher,
            storage=storage,
            node_detail_service=detail_service,
            frame_generation_service=frame_service or FakeGenerationService("frame"),
            clarify_generation_service=FakeGenerationService("clarify"),
            spec_generation_service=FakeGenerationService("spec"),
            split_service=FakeSplitService(),
        ),
        repository,
        binding_service,
        event_broker,
    )


def test_start_frame_generation_is_idempotent(storage, workspace_root) -> None:
    project_id, node_id = _create_project(storage, workspace_root)
    frame_service = FakeGenerationService("frame")
    orchestrator, _repository, _binding_service, broker = _orchestrator(
        storage,
        frame_service=frame_service,
    )

    first = orchestrator.start_frame_generation(
        project_id,
        node_id,
        idempotency_key="frame-generate:once",
    )
    replay = orchestrator.start_frame_generation(
        project_id,
        node_id,
        idempotency_key="frame-generate:once",
    )

    assert first == replay
    assert frame_service.starts == [(project_id, node_id)]
    assert [event["type"] for event in broker.events] == ["workflow/artifact_job_started"]


def test_confirm_frame_syncs_source_versions_without_context_rebase_side_effects(
    storage,
    workspace_root,
) -> None:
    project_id, node_id = _create_project(storage, workspace_root)
    tree_service = TreeService()
    detail_service = NodeDetailService(storage, tree_service)
    _confirm_frame(storage, detail_service, project_id, node_id, "# Task Title\nFrame v1")
    orchestrator, repository, binding_service, broker = _orchestrator(storage)
    binding_service.ensure_thread(
        project_id=project_id,
        node_id=node_id,
        role="execution",
        idempotency_key="ensure-execution",
    )
    broker.events.clear()

    NodeDocumentService(storage).put_document(project_id, node_id, "frame", "# Task Title\nFrame v2")
    detail_service.bump_frame_revision(project_id, node_id)
    response = orchestrator.confirm_frame(
        project_id,
        node_id,
        idempotency_key="frame-confirm:v2",
    )

    state = repository.read_state(project_id, node_id)
    assert response["confirmed"] is True
    assert response["artifact"]["frameVersion"] == 2
    assert state.frame_version == 2
    assert "workflow/state_changed" in [event["type"] for event in broker.events]
    assert "workflow/artifact_confirmed" in [event["type"] for event in broker.events]
