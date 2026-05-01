from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.business.workflow_v2.artifact_orchestrator import ArtifactOrchestratorV2
from backend.business.workflow_v2.artifact_turn_runner import WorkflowArtifactTurnRunnerV2
from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.events import WorkflowEventPublisherV2
from backend.business.workflow_v2.execution_audit_orchestrator import ExecutionAuditOrchestratorV2
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.config.app_config import (
    build_app_paths,
    get_clarify_gen_timeout,
    get_codex_cmd,
    get_frame_gen_timeout,
    get_port,
    get_session_core_v2_event_queue_capacity,
    get_session_core_v2_protocol_gate_timeout_sec,
    get_session_core_v2_retention_days,
    get_session_core_v2_retention_max_events,
    get_session_core_v2_server_request_queue_capacity,
    get_session_core_v2_thread_read_mode,
    get_spec_gen_timeout,
    get_split_timeout,
    get_sse_subscriber_queue_max,
    is_session_core_v2_events_enabled,
    is_session_core_v2_protocol_gate_enabled,
    is_session_core_v2_requests_enabled,
    is_session_core_v2_turns_enabled,
)
from backend.errors.app_errors import AppError
from backend.mcp import McpIntegrationService
from backend.skills import SkillIntegrationService
from backend.middleware.auth_token import AuthTokenMiddleware, get_auth_token
from backend.routes import (
    artifacts_v4,
    bootstrap,
    codex,
    nodes,
    projects,
    session_v4,
    workflow_v4,
)
from backend.services.clarify_generation_service import ClarifyGenerationService
from backend.services.frame_generation_service import FrameGenerationService
from backend.services.git_checkpoint_service import GitCheckpointService
from backend.services.local_usage_snapshot_service import LocalUsageSnapshotService
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.snapshot_view_service import SnapshotViewService
from backend.services.spec_generation_service import SpecGenerationService
from backend.services.split_service import SplitService
from backend.services.tree_service import TreeService
from backend.services.workspace_file_service import WorkspaceFileService
from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.protocol import (
    SessionProtocolClientV2,
    ensure_session_core_v2_protocol_compatible,
)
from backend.session_core_v2.storage import RuntimeStoreV2
from backend.session_core_v2.thread_store import ThreadMetadataStore, ThreadRolloutRecorder
from backend.session_core_v2.transport import StdioJsonRpcTransportV2
from backend.storage.storage import Storage
from backend.streaming.sse_broker import GlobalEventBroker

logger = logging.getLogger(__name__)


def create_app(data_root: Path | None = None) -> FastAPI:
    paths = build_app_paths(data_root)
    storage = Storage(paths)
    tree_service = TreeService()
    git_checkpoint_service = GitCheckpointService()
    sse_subscriber_queue_max = get_sse_subscriber_queue_max()
    session_core_v2_event_queue_capacity = get_session_core_v2_event_queue_capacity()
    session_core_v2_server_request_queue_capacity = get_session_core_v2_server_request_queue_capacity()
    session_core_v2_retention_max_events = get_session_core_v2_retention_max_events()
    session_core_v2_retention_days = get_session_core_v2_retention_days()
    session_core_v2_enable_turns = is_session_core_v2_turns_enabled()
    session_core_v2_enable_events = is_session_core_v2_events_enabled()
    session_core_v2_enable_requests = is_session_core_v2_requests_enabled()
    session_core_v2_protocol_gate_enabled = is_session_core_v2_protocol_gate_enabled()
    session_core_v2_protocol_gate_timeout_sec = get_session_core_v2_protocol_gate_timeout_sec()
    session_core_v2_thread_read_mode = get_session_core_v2_thread_read_mode()
    codex_cmd = get_codex_cmd() or "codex"
    snapshot_view_service = SnapshotViewService(storage, git_checkpoint_service=git_checkpoint_service)
    local_usage_snapshot_service = LocalUsageSnapshotService()
    project_service = ProjectService(
        storage,
        snapshot_view_service,
        git_checkpoint_service=git_checkpoint_service,
    )
    node_service = NodeService(storage, tree_service, snapshot_view_service)
    node_document_service = NodeDocumentService(storage)
    workspace_file_service = WorkspaceFileService(storage)
    node_detail_service = NodeDetailService(
        storage,
        tree_service,
        git_checkpoint_service=git_checkpoint_service,
    )
    workflow_event_broker = GlobalEventBroker(subscriber_queue_max=sse_subscriber_queue_max)
    mcp_integration_service = McpIntegrationService(
        paths,
        project_cwd_resolver=storage.workspace_store.get_folder_path,
    )
    skill_integration_service = SkillIntegrationService(
        paths,
        project_cwd_resolver=storage.workspace_store.get_folder_path,
    )
    session_transport_v2 = StdioJsonRpcTransportV2(
        codex_cmd=codex_cmd,
        server_request_queue_capacity=session_core_v2_server_request_queue_capacity,
    )
    session_protocol_v2 = SessionProtocolClientV2(session_transport_v2)
    session_runtime_store_v2 = RuntimeStoreV2(
        db_path=paths.data_root / "session_core_v2.sqlite3",
        subscriber_queue_capacity=session_core_v2_event_queue_capacity,
        retention_max_events=session_core_v2_retention_max_events,
        retention_days=session_core_v2_retention_days,
    )
    native_thread_root_v2 = paths.data_root / "session_core_v2"
    session_thread_metadata_store_v2 = ThreadMetadataStore(
        db_path=native_thread_root_v2 / "thread_metadata.sqlite3",
        rollout_root=native_thread_root_v2 / "rollouts",
    )
    session_thread_rollout_recorder_v2 = ThreadRolloutRecorder(
        metadata_store=session_thread_metadata_store_v2,
    )
    session_connection_state_v2 = ConnectionStateMachine()
    session_manager_v2 = SessionManagerV2(
        protocol_client=session_protocol_v2,
        runtime_store=session_runtime_store_v2,
        connection_state_machine=session_connection_state_v2,
        thread_rollout_recorder=session_thread_rollout_recorder_v2,
        thread_read_mode=session_core_v2_thread_read_mode,
        mcp_service=mcp_integration_service,
        skills_service=skill_integration_service,
    )
    workflow_state_repository_v2 = WorkflowStateRepositoryV2(storage)
    workflow_context_builder_v2 = WorkflowContextBuilderV2(storage)
    workflow_event_publisher_v2 = WorkflowEventPublisherV2(workflow_event_broker)
    workflow_thread_binding_service_v2 = ThreadBindingServiceV2(
        repository=workflow_state_repository_v2,
        context_builder=workflow_context_builder_v2,
        session_manager=session_manager_v2,
        event_publisher=workflow_event_publisher_v2,
    )
    artifact_turn_runner_v2 = WorkflowArtifactTurnRunnerV2(
        thread_binding_service=workflow_thread_binding_service_v2,
        session_manager=session_manager_v2,
        timeout_sec=max(get_frame_gen_timeout(), get_clarify_gen_timeout(), get_spec_gen_timeout(), get_split_timeout()),
    )
    split_service = SplitService(
        storage=storage,
        tree_service=tree_service,
        split_timeout=get_split_timeout(),
        artifact_turn_runner=artifact_turn_runner_v2,
        git_checkpoint_service=git_checkpoint_service,
    )
    frame_generation_service = FrameGenerationService(
        storage=storage,
        tree_service=tree_service,
        frame_gen_timeout=get_frame_gen_timeout(),
        artifact_turn_runner=artifact_turn_runner_v2,
    )
    clarify_generation_service = ClarifyGenerationService(
        storage=storage,
        tree_service=tree_service,
        clarify_gen_timeout=get_clarify_gen_timeout(),
        artifact_turn_runner=artifact_turn_runner_v2,
    )
    spec_generation_service = SpecGenerationService(
        storage=storage,
        tree_service=tree_service,
        spec_gen_timeout=get_spec_gen_timeout(),
        artifact_turn_runner=artifact_turn_runner_v2,
    )
    execution_audit_orchestrator_v2 = ExecutionAuditOrchestratorV2(
        repository=workflow_state_repository_v2,
        thread_binding_service=workflow_thread_binding_service_v2,
        session_manager=session_manager_v2,
        event_publisher=workflow_event_publisher_v2,
        storage=storage,
        tree_service=tree_service,
        git_checkpoint_service=git_checkpoint_service,
    )
    artifact_orchestrator_v2 = ArtifactOrchestratorV2(
        repository=workflow_state_repository_v2,
        thread_binding_service=workflow_thread_binding_service_v2,
        event_publisher=workflow_event_publisher_v2,
        storage=storage,
        node_detail_service=node_detail_service,
        frame_generation_service=frame_generation_service,
        clarify_generation_service=clarify_generation_service,
        spec_generation_service=spec_generation_service,
        split_service=split_service,
    )
    session_runtime_store_v2.add_event_observer(execution_audit_orchestrator_v2.handle_session_event)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if session_core_v2_enable_turns and session_core_v2_protocol_gate_enabled:
            logger.info(
                "Session Core V2 protocol compatibility gate started",
                extra={
                    "codex_cmd": codex_cmd,
                    "timeout_sec": session_core_v2_protocol_gate_timeout_sec,
                },
            )
            ensure_session_core_v2_protocol_compatible(
                codex_cmd=codex_cmd,
                timeout_sec=session_core_v2_protocol_gate_timeout_sec,
            )
            logger.info("Session Core V2 protocol compatibility gate passed")
        try:
            yield
        finally:
            session_runtime_store_v2.close()
            session_thread_metadata_store_v2.close()
            session_transport_v2.stop()

    app = FastAPI(
        title="PlanningTree",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    auth_token = get_auth_token()
    if auth_token:
        cors_origins = [f"http://127.0.0.1:{get_port()}"]
    else:
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(AuthTokenMiddleware, token=auth_token)

    app.state.paths = paths
    app.state.storage = storage
    app.state.git_checkpoint_service = git_checkpoint_service
    app.state.tree_service = tree_service
    app.state.project_service = project_service
    app.state.node_service = node_service
    app.state.node_document_service = node_document_service
    app.state.workspace_file_service = workspace_file_service
    app.state.node_detail_service = node_detail_service
    app.state.snapshot_view_service = snapshot_view_service
    app.state.local_usage_snapshot_service = local_usage_snapshot_service
    app.state.split_service = split_service
    app.state.frame_generation_service = frame_generation_service
    app.state.clarify_generation_service = clarify_generation_service
    app.state.spec_generation_service = spec_generation_service
    app.state.workflow_event_broker = workflow_event_broker
    app.state.session_manager_v2 = session_manager_v2
    app.state.mcp_integration_service = mcp_integration_service
    app.state.skill_integration_service = skill_integration_service
    app.state.workflow_state_repository_v2 = workflow_state_repository_v2
    app.state.workflow_context_builder_v2 = workflow_context_builder_v2
    app.state.workflow_event_publisher_v2 = workflow_event_publisher_v2
    app.state.workflow_thread_binding_service_v2 = workflow_thread_binding_service_v2
    app.state.artifact_turn_runner_v2 = artifact_turn_runner_v2
    app.state.execution_audit_orchestrator_v2 = execution_audit_orchestrator_v2
    app.state.artifact_orchestrator_v2 = artifact_orchestrator_v2
    app.state.session_runtime_store_v2 = session_runtime_store_v2
    app.state.session_thread_metadata_store_v2 = session_thread_metadata_store_v2
    app.state.session_thread_rollout_recorder_v2 = session_thread_rollout_recorder_v2
    app.state.session_connection_state_v2 = session_connection_state_v2
    app.state.session_core_v2_enable_turns = session_core_v2_enable_turns
    app.state.session_core_v2_enable_events = session_core_v2_enable_events
    app.state.session_core_v2_enable_requests = session_core_v2_enable_requests
    app.state.session_core_v2_thread_read_mode = session_core_v2_thread_read_mode

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error for %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "An unexpected internal error occurred.",
            },
        )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    for product_router in (bootstrap.router, codex.router, projects.router, nodes.router):
        app.include_router(product_router, prefix="/v4")
    app.include_router(session_v4.router)
    app.include_router(workflow_v4.router)
    app.include_router(artifacts_v4.router)

    if getattr(sys, "frozen", False):
        dist = Path(sys._MEIPASS) / "frontend" / "dist"  # type: ignore[attr-defined]
    else:
        dist = Path(__file__).parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


app = create_app()
