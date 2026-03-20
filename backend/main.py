from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai.codex_client import CodexAppClient, StdioTransport
from backend.config.app_config import build_app_paths, get_chat_timeout, get_codex_cmd, get_max_chat_message_chars, get_split_timeout
from backend.errors.app_errors import AppError
from backend.routes import bootstrap, chat, nodes, projects, settings, split
from backend.services.chat_service import ChatService
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.snapshot_view_service import SnapshotViewService
from backend.services.split_service import SplitService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)


def create_app(data_root: Optional[Path] = None) -> FastAPI:
    paths = build_app_paths(data_root)
    storage = Storage(paths)
    tree_service = TreeService()
    snapshot_view_service = SnapshotViewService()
    project_service = ProjectService(storage, snapshot_view_service, chat_service=None)
    node_service = NodeService(storage, tree_service, snapshot_view_service)
    codex_client = CodexAppClient(StdioTransport(codex_cmd=get_codex_cmd() or "codex"))
    split_service = SplitService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        split_timeout=get_split_timeout(),
    )
    chat_event_broker = ChatEventBroker()
    chat_service = ChatService(
        storage=storage,
        tree_service=tree_service,
        codex_client=codex_client,
        chat_event_broker=chat_event_broker,
        chat_timeout=get_chat_timeout(),
        max_message_chars=get_max_chat_message_chars(),
    )
    project_service._chat_service = chat_service

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
    app.state.snapshot_view_service = snapshot_view_service
    app.state.codex_client = codex_client
    app.state.split_service = split_service
    app.state.chat_service = chat_service
    app.state.chat_event_broker = chat_event_broker

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
    app.include_router(settings.router, prefix="/v1")
    app.include_router(projects.router, prefix="/v1")
    app.include_router(nodes.router, prefix="/v1")
    app.include_router(split.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")

    dist = Path(__file__).parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


app = create_app()
