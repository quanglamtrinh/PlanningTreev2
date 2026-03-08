from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.errors.app_errors import AppError


def create_app() -> FastAPI:
    app = FastAPI(
        title="PlanningTree",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    # Routers registered here as features are implemented
    # from backend.routes import bootstrap, auth, settings, projects, nodes, chat
    # app.include_router(bootstrap.router, prefix="/v1")
    # app.include_router(auth.router, prefix="/v1")
    # app.include_router(settings.router, prefix="/v1")
    # app.include_router(projects.router, prefix="/v1")
    # app.include_router(nodes.router, prefix="/v1")
    # app.include_router(chat.router, prefix="/v1")

    # Serve built frontend in production
    dist = Path(__file__).parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


app = create_app()
