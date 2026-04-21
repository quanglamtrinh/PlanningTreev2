from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai.codex_client import CodexAppClient, StdioTransport
from backend.conversation.services.request_ledger_service_v3 import RequestLedgerServiceV3
from backend.conversation.services.thread_actor_runtime_v3 import ThreadActorRuntimeV3
from backend.conversation.services.thread_checkpoint_policy_v3 import ThreadCheckpointPolicyV3
from backend.conversation.services.thread_query_service_v3 import ThreadQueryServiceV3
from backend.conversation.services.thread_replay_buffer_service_v3 import ThreadReplayBufferServiceV3
from backend.conversation.services.thread_registry_service import ThreadRegistryService
from backend.conversation.services.thread_runtime_service_v3 import ThreadRuntimeServiceV3
from backend.conversation.services.system_message_writer import ConversationSystemMessageWriter
from backend.conversation.services.thread_transcript_builder import ThreadTranscriptBuilder
from backend.conversation.services.workflow_event_publisher import WorkflowEventPublisher
from backend.config.app_config import (
    build_app_paths,
    get_chat_timeout,
    get_clarify_gen_timeout,
    get_codex_cmd,
    get_execution_timeout,
    get_frame_gen_timeout,
    get_max_chat_message_chars,
    get_port,
    get_phase5_log_compact_min_events,
    get_rehearsal_workspace_root,
    get_session_core_v2_event_queue_capacity,
    get_session_core_v2_protocol_gate_timeout_sec,
    get_session_core_v2_server_request_queue_capacity,
    get_session_core_v2_retention_days,
    get_session_core_v2_retention_max_events,
    get_thread_raw_event_coalesce_ms,
    get_thread_stream_cadence_profile,
    get_sse_subscriber_queue_max,
    get_spec_gen_timeout,
    get_split_timeout,
    get_thread_actor_mode,
    is_session_core_v2_events_enabled,
    is_session_core_v2_protocol_gate_enabled,
    is_session_core_v2_requests_enabled,
    is_session_core_v2_turns_enabled,
    is_ask_v3_backend_enabled,
    is_ask_v3_frontend_enabled,
)
from backend.config.api_version import API_PREFIX
from backend.errors.app_errors import AppError
from backend.middleware.auth_token import AuthTokenMiddleware, get_auth_token
from backend.routes import bootstrap, chat, codex, nodes, projects, session_v4, split, workflow_v3
from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.protocol import (
    SessionProtocolClientV2,
    ensure_session_core_v2_protocol_compatible,
)
from backend.session_core_v2.storage import RuntimeStoreV2
from backend.session_core_v2.transport import StdioJsonRpcTransportV2
from backend.services.chat_service import ChatService
from backend.services.ask_rollout_metrics_service import AskRolloutMetricsService
from backend.services.codex_account_service import CodexAccountService
from backend.services.clarify_generation_service import ClarifyGenerationService
from backend.services.execution_audit_workflow_service import ExecutionAuditWorkflowService
from backend.services.frame_generation_service import FrameGenerationService
from backend.services.finish_task_service import FinishTaskService
from backend.services.git_checkpoint_service import GitCheckpointService
from backend.services.node_detail_service import NodeDetailService
from backend.services.local_usage_snapshot_service import LocalUsageSnapshotService
from backend.services.spec_generation_service import SpecGenerationService
from backend.services.node_document_service import NodeDocumentService
from backend.services.workspace_file_service import WorkspaceFileService
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.review_service import ReviewService
from backend.services.snapshot_view_service import SnapshotViewService
from backend.services.split_service import SplitService
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker, GlobalEventBroker

logger = logging.getLogger(__name__)


def create_app(data_root: Optional[Path] = None) -> FastAPI:
    paths = build_app_paths(data_root)
    storage = Storage(paths)
    tree_service = TreeService()
    git_checkpoint_service = GitCheckpointService()
    ask_v3_backend_enabled = is_ask_v3_backend_enabled()
    ask_v3_frontend_enabled = is_ask_v3_frontend_enabled()
    rehearsal_workspace_root = get_rehearsal_workspace_root()
    sse_subscriber_queue_max = get_sse_subscriber_queue_max()
    phase5_log_compact_min_events = get_phase5_log_compact_min_events()
    thread_stream_cadence_profile = get_thread_stream_cadence_profile()
    thread_raw_event_coalesce_ms = get_thread_raw_event_coalesce_ms()
    session_core_v2_event_queue_capacity = get_session_core_v2_event_queue_capacity()
    session_core_v2_server_request_queue_capacity = get_session_core_v2_server_request_queue_capacity()
    session_core_v2_retention_max_events = get_session_core_v2_retention_max_events()
    session_core_v2_retention_days = get_session_core_v2_retention_days()
    session_core_v2_enable_turns = is_session_core_v2_turns_enabled()
    session_core_v2_enable_events = is_session_core_v2_events_enabled()
    session_core_v2_enable_requests = is_session_core_v2_requests_enabled()
    session_core_v2_protocol_gate_enabled = is_session_core_v2_protocol_gate_enabled()
    session_core_v2_protocol_gate_timeout_sec = get_session_core_v2_protocol_gate_timeout_sec()
    codex_cmd = get_codex_cmd() or "codex"
    ask_rollout_metrics_service = AskRolloutMetricsService()
    snapshot_view_service = SnapshotViewService(storage, git_checkpoint_service=git_checkpoint_service)
    project_service = ProjectService(
        storage, snapshot_view_service, chat_service=None,
        git_checkpoint_service=git_checkpoint_service,
    )
    node_service = NodeService(storage, tree_service, snapshot_view_service)
    node_document_service = NodeDocumentService(storage)
    workspace_file_service = WorkspaceFileService(storage)
    thread_registry_service_v2 = ThreadRegistryService(storage.thread_registry_store)
    system_message_writer_v2 = ConversationSystemMessageWriter(storage)
    node_detail_service = NodeDetailService(
        storage,
        tree_service,
        git_checkpoint_service=git_checkpoint_service,
    )
    codex_client = CodexAppClient(StdioTransport(codex_cmd=codex_cmd))
    thread_lineage_service = ThreadLineageService(
        storage,
        codex_client,
        tree_service,
        thread_registry_service_v2=thread_registry_service_v2,
    )
    thread_transcript_builder_v2 = ThreadTranscriptBuilder(storage, storage.thread_snapshot_store_v2)
    codex_event_broker = GlobalEventBroker(subscriber_queue_max=sse_subscriber_queue_max)
    codex_account_service = CodexAccountService(
        codex_client=codex_client,
        event_broker=codex_event_broker,
    )
    local_usage_snapshot_service = LocalUsageSnapshotService()
    split_service = SplitService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        split_timeout=get_split_timeout(),
        git_checkpoint_service=git_checkpoint_service,
    )
    frame_generation_service = FrameGenerationService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        frame_gen_timeout=get_frame_gen_timeout(),
        thread_transcript_builder=thread_transcript_builder_v2,
    )
    clarify_generation_service = ClarifyGenerationService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        clarify_gen_timeout=get_clarify_gen_timeout(),
    )
    spec_generation_service = SpecGenerationService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        spec_gen_timeout=get_spec_gen_timeout(),
    )
    chat_event_broker = ChatEventBroker(subscriber_queue_max=sse_subscriber_queue_max)
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=get_chat_timeout(),
        max_message_chars=get_max_chat_message_chars(),
    )
    request_ledger_service_v3 = RequestLedgerServiceV3()
    thread_replay_buffer_service_v3 = ThreadReplayBufferServiceV3(max_events=500, ttl_seconds=15 * 60)
    thread_actor_runtime_v3 = ThreadActorRuntimeV3()
    checkpoint_policy_v3 = ThreadCheckpointPolicyV3(timer_checkpoint_ms=5000)
    thread_actor_mode = get_thread_actor_mode()
    conversation_event_broker_v3 = ChatEventBroker(subscriber_queue_max=sse_subscriber_queue_max)
    workflow_event_broker = GlobalEventBroker(subscriber_queue_max=sse_subscriber_queue_max)
    workflow_event_publisher = WorkflowEventPublisher(workflow_event_broker)
    thread_query_service_v3 = ThreadQueryServiceV3(
        storage=storage,
        chat_service=chat_service,
        thread_lineage_service=thread_lineage_service,
        codex_client=codex_client,
        snapshot_store_v3=storage.thread_snapshot_store_v3,
        snapshot_store_v2=storage.thread_snapshot_store_v2,
        registry_service_v2=thread_registry_service_v2,
        request_ledger_service=request_ledger_service_v3,
        thread_event_broker=conversation_event_broker_v3,
        replay_buffer_service=thread_replay_buffer_service_v3,
        mini_journal_store_v3=storage.thread_mini_journal_store_v3,
        event_log_store_v3=storage.thread_event_log_store_v3,
        checkpoint_policy_v3=checkpoint_policy_v3,
        actor_runtime_v3=thread_actor_runtime_v3,
        thread_actor_mode=thread_actor_mode,
        log_compact_min_events=phase5_log_compact_min_events,
    )
    thread_runtime_service_v3 = ThreadRuntimeServiceV3(
        storage=storage,
        tree_service=tree_service,
        chat_service=chat_service,
        codex_client=codex_client,
        query_service=thread_query_service_v3,
        request_ledger_service=request_ledger_service_v3,
        chat_timeout=get_chat_timeout(),
        max_message_chars=get_max_chat_message_chars(),
        ask_rollout_metrics_service=ask_rollout_metrics_service,
        coalescing_window_ms=thread_raw_event_coalesce_ms,
        thread_actor_mode=thread_actor_mode,
    )
    logger.info(
        "Thread stream cadence configured",
        extra={
            "thread_stream_cadence_profile": thread_stream_cadence_profile,
            "thread_raw_event_coalesce_ms": thread_raw_event_coalesce_ms,
        },
    )
    system_message_writer_v2.set_runtime_service(thread_runtime_service_v3)
    review_service = ReviewService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=get_chat_timeout(),
        chat_service=chat_service,
        system_message_writer=system_message_writer_v2,
        thread_runtime_service=thread_runtime_service_v3,
        workflow_event_publisher=workflow_event_publisher,
        rehearsal_workspace_root=rehearsal_workspace_root,
    )
    finish_task_service = FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=node_detail_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=get_execution_timeout(),
        chat_service=chat_service,
        git_checkpoint_service=git_checkpoint_service,
        review_service=review_service,
        thread_runtime_service=thread_runtime_service_v3,
        thread_query_service=thread_query_service_v3,
        workflow_event_publisher=workflow_event_publisher,
        rehearsal_workspace_root=rehearsal_workspace_root,
    )
    execution_audit_workflow_service = ExecutionAuditWorkflowService(
        storage=storage,
        tree_service=tree_service,
        finish_task_service=finish_task_service,
        review_service=review_service,
        thread_runtime_service=thread_runtime_service_v3,
        thread_query_service=thread_query_service_v3,
        workflow_event_publisher=workflow_event_publisher,
        git_checkpoint_service=git_checkpoint_service,
        codex_client=codex_client,
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
    session_connection_state_v2 = ConnectionStateMachine()
    session_manager_v2 = SessionManagerV2(
        protocol_client=session_protocol_v2,
        runtime_store=session_runtime_store_v2,
        connection_state_machine=session_connection_state_v2,
    )
    project_service._chat_service = chat_service
    chat_service._review_service = review_service
    thread_lineage_service.set_thread_registry_service(thread_registry_service_v2)

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
            session_transport_v2.stop()
            codex_client.stop()

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
    app.state.codex_client = codex_client
    app.state.thread_lineage_service = thread_lineage_service
    app.state.codex_event_broker = codex_event_broker
    app.state.codex_account_service = codex_account_service
    app.state.local_usage_snapshot_service = local_usage_snapshot_service
    app.state.split_service = split_service
    app.state.frame_generation_service = frame_generation_service
    app.state.clarify_generation_service = clarify_generation_service
    app.state.spec_generation_service = spec_generation_service
    app.state.chat_service = chat_service
    app.state.chat_event_broker = chat_event_broker
    app.state.review_service = review_service
    app.state.finish_task_service = finish_task_service
    app.state.thread_registry_service_v2 = thread_registry_service_v2
    app.state.request_ledger_service_v3 = request_ledger_service_v3
    app.state.thread_replay_buffer_service_v3 = thread_replay_buffer_service_v3
    app.state.conversation_event_broker_v3 = conversation_event_broker_v3
    app.state.workflow_event_broker = workflow_event_broker
    app.state.thread_query_service_v3 = thread_query_service_v3
    app.state.thread_runtime_service_v3 = thread_runtime_service_v3
    app.state.thread_transcript_builder_v2 = thread_transcript_builder_v2
    app.state.workflow_event_publisher = workflow_event_publisher
    app.state.system_message_writer_v2 = system_message_writer_v2
    app.state.execution_audit_workflow_service = execution_audit_workflow_service
    app.state.ask_v3_backend_enabled = ask_v3_backend_enabled
    app.state.ask_v3_frontend_enabled = ask_v3_frontend_enabled
    app.state.ask_rollout_metrics_service = ask_rollout_metrics_service
    app.state.session_manager_v2 = session_manager_v2
    app.state.session_runtime_store_v2 = session_runtime_store_v2
    app.state.session_connection_state_v2 = session_connection_state_v2
    app.state.session_core_v2_enable_turns = session_core_v2_enable_turns
    app.state.session_core_v2_enable_events = session_core_v2_enable_events
    app.state.session_core_v2_enable_requests = session_core_v2_enable_requests

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

    app.include_router(bootstrap.router, prefix=API_PREFIX)
    app.include_router(codex.router, prefix=API_PREFIX)
    app.include_router(projects.router, prefix=API_PREFIX)
    app.include_router(nodes.router, prefix=API_PREFIX)
    app.include_router(split.router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    app.include_router(workflow_v3.router, prefix=API_PREFIX)
    app.include_router(session_v4.router)

    if getattr(sys, "frozen", False):
        dist = Path(sys._MEIPASS) / "frontend" / "dist"  # type: ignore[attr-defined]
    else:
        dist = Path(__file__).parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


app = create_app()
