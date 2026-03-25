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
from backend.config.app_config import build_app_paths, get_chat_timeout, get_clarify_gen_timeout, get_codex_cmd, get_execution_timeout, get_frame_gen_timeout, get_max_chat_message_chars, get_port, get_spec_gen_timeout, get_split_timeout
from backend.errors.app_errors import AppError
from backend.middleware.auth_token import AuthTokenMiddleware, get_auth_token
from backend.routes import bootstrap, chat, codex, nodes, projects, split
from backend.services.chat_service import ChatService
from backend.services.codex_account_service import CodexAccountService
from backend.services.clarify_generation_service import ClarifyGenerationService
from backend.services.frame_generation_service import FrameGenerationService
from backend.services.finish_task_service import FinishTaskService
from backend.services.node_detail_service import NodeDetailService
from backend.services.spec_generation_service import SpecGenerationService
from backend.services.node_document_service import NodeDocumentService
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
    snapshot_view_service = SnapshotViewService(storage)
    project_service = ProjectService(storage, snapshot_view_service, chat_service=None)
    node_service = NodeService(storage, tree_service, snapshot_view_service)
    node_document_service = NodeDocumentService(storage)
    node_detail_service = NodeDetailService(storage, tree_service)
    codex_client = CodexAppClient(StdioTransport(codex_cmd=get_codex_cmd() or "codex"))
    thread_lineage_service = ThreadLineageService(storage, codex_client, tree_service)
    codex_event_broker = GlobalEventBroker()
    codex_account_service = CodexAccountService(
        codex_client=codex_client,
        event_broker=codex_event_broker,
    )
    split_service = SplitService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        split_timeout=get_split_timeout(),
    )
    frame_generation_service = FrameGenerationService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        frame_gen_timeout=get_frame_gen_timeout(),
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
    chat_event_broker = ChatEventBroker()
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=chat_event_broker,
        chat_timeout=get_chat_timeout(),
        max_message_chars=get_max_chat_message_chars(),
    )
    review_service = ReviewService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        chat_event_broker=chat_event_broker,
        chat_timeout=get_chat_timeout(),
        chat_service=chat_service,
    )
    finish_task_service = FinishTaskService(
        storage=storage,
        tree_service=tree_service,
        node_detail_service=node_detail_service,
        codex_client=codex_client,
        chat_event_broker=chat_event_broker,
        chat_timeout=get_execution_timeout(),
        chat_service=chat_service,
    )
    project_service._chat_service = chat_service
    chat_service._review_service = review_service

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
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
    app.state.tree_service = tree_service
    app.state.project_service = project_service
    app.state.node_service = node_service
    app.state.node_document_service = node_document_service
    app.state.node_detail_service = node_detail_service
    app.state.snapshot_view_service = snapshot_view_service
    app.state.codex_client = codex_client
    app.state.thread_lineage_service = thread_lineage_service
    app.state.codex_event_broker = codex_event_broker
    app.state.codex_account_service = codex_account_service
    app.state.split_service = split_service
    app.state.frame_generation_service = frame_generation_service
    app.state.clarify_generation_service = clarify_generation_service
    app.state.spec_generation_service = spec_generation_service
    app.state.chat_service = chat_service
    app.state.chat_event_broker = chat_event_broker
    app.state.review_service = review_service
    app.state.finish_task_service = finish_task_service

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

    app.include_router(bootstrap.router, prefix="/v1")
    app.include_router(codex.router, prefix="/v1")
    app.include_router(projects.router, prefix="/v1")
    app.include_router(nodes.router, prefix="/v1")
    app.include_router(split.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")

    if getattr(sys, "frozen", False):
        dist = Path(sys._MEIPASS) / "frontend" / "dist"  # type: ignore[attr-defined]
    else:
        dist = Path(__file__).parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


app = create_app()
