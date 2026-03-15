from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai.codex_client import CodexAppClient, CodexTransportError, CodexTransportNotFound, StdioTransport
from backend.config.app_config import build_app_paths, get_codex_cmd, get_split_timeout
from backend.errors.app_errors import AppError
from backend.routes import agent, ask, bootstrap, chat, nodes, projects, settings, split
from backend.services.agent_operation_service import AgentOperationService
from backend.services.ask_service import AskService
from backend.services.brief_generation_service import BriefGenerationService
from backend.services.chat_service import ChatService
from backend.services.codex_session_manager import CodexSessionManager
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.snapshot_view_service import SnapshotViewService
from backend.services.spec_generation_service import SpecGenerationService
from backend.services.split_service import SplitService
from backend.services.thread_service import ThreadService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import AgentEventBroker, AskEventBroker, ChatEventBroker, PlanningEventBroker

logger = logging.getLogger(__name__)


def _build_project_codex_client(_workspace_root: str) -> CodexAppClient:
    transport = StdioTransport(codex_cmd=get_codex_cmd() or "codex")
    return CodexAppClient(transport)


def create_app(data_root: Optional[Path] = None) -> FastAPI:
    paths = build_app_paths(data_root)
    storage = Storage(paths)
    tree_service = TreeService()
    transport = StdioTransport(codex_cmd=get_codex_cmd() or "codex")
    codex_client = CodexAppClient(transport)
    codex_session_manager = CodexSessionManager(client_factory=_build_project_codex_client)
    snapshot_view_service = SnapshotViewService(storage.node_store)
    thread_service = ThreadService(storage, tree_service, codex_client)
    ask_event_broker = AskEventBroker()
    chat_event_broker = ChatEventBroker()
    planning_event_broker = PlanningEventBroker()
    agent_event_broker = AgentEventBroker()
    agent_operation_service = AgentOperationService(agent_event_broker)
    project_service = ProjectService(storage, snapshot_view_service, thread_service)
    node_service = NodeService(
        storage,
        tree_service,
        thread_service,
        snapshot_view_service,
        agent_operation_service,
    )
    ask_service = AskService(storage, codex_client, ask_event_broker, thread_service)
    brief_generation_service = BriefGenerationService(
        storage,
        tree_service,
        codex_client,
        agent_operation_service=agent_operation_service,
    )
    spec_generation_service = SpecGenerationService(
        storage,
        codex_client,
        node_service,
        agent_operation_service=agent_operation_service,
    )
    brief_generation_service.configure_spec_generation_service(spec_generation_service)
    node_service.configure_artifact_services(
        brief_generation_service=brief_generation_service,
        spec_generation_service=spec_generation_service,
    )
    chat_service = ChatService(
        storage,
        codex_client,
        chat_event_broker,
        thread_service,
        node_service,
        agent_operation_service,
    )
    split_service = SplitService(
        storage,
        tree_service,
        codex_client,
        thread_service,
        planning_event_broker,
        get_split_timeout(),
        agent_operation_service,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        chat_service.reconcile_interrupted_turns()
        ask_service.reconcile_interrupted_ask_turns()
        thread_service.reconcile_interrupted_planning_turns()
        brief_generation_service.reconcile_interrupted_generations()
        spec_generation_service.reconcile_interrupted_generations()
        yield
        codex_session_manager.shutdown()
        codex_client.stop()

    app = FastAPI(
        title="PlanningTree",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.paths = paths
    app.state.storage = storage
    app.state.tree_service = tree_service
    app.state.project_service = project_service
    app.state.node_service = node_service
    app.state.codex_client = codex_client
    app.state.codex_session_manager = codex_session_manager
    app.state.snapshot_view_service = snapshot_view_service
    app.state.thread_service = thread_service
    app.state.ask_event_broker = ask_event_broker
    app.state.chat_event_broker = chat_event_broker
    app.state.planning_event_broker = planning_event_broker
    app.state.agent_event_broker = agent_event_broker
    app.state.agent_operation_service = agent_operation_service
    app.state.ask_service = ask_service
    app.state.chat_service = chat_service
    app.state.brief_generation_service = brief_generation_service
    app.state.spec_generation_service = spec_generation_service
    app.state.split_service = split_service

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(CodexTransportNotFound)
    async def codex_not_found_handler(request: Request, exc: CodexTransportNotFound) -> JSONResponse:
        logger.error("Codex binary unavailable for %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=503,
            content={
                "code": "codex_binary_not_found",
                "message": str(exc),
            },
        )

    @app.exception_handler(CodexTransportError)
    async def codex_transport_error_handler(request: Request, exc: CodexTransportError) -> JSONResponse:
        logger.error("Codex transport error for %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=502,
            content={
                "code": exc.error_code or "codex_transport_error",
                "message": str(exc),
            },
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

    app.include_router(bootstrap.router, prefix="/v1")
    app.include_router(settings.router, prefix="/v1")
    app.include_router(projects.router, prefix="/v1")
    app.include_router(nodes.router, prefix="/v1")
    app.include_router(split.router, prefix="/v1")
    app.include_router(agent.router, prefix="/v1")
    app.include_router(ask.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")

    dist = Path(__file__).parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


app = create_app()
