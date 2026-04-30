"""Per-launch auth token middleware for Electron desktop security.

When PLANNINGTREE_AUTH_TOKEN is set (by the Electron main process),
every request except /health must include a matching Authorization header.
When the env var is absent (plain dev mode), all requests pass through.
"""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


# Only API routes require auth.  Static assets, the HTML shell, /health,
# and docs are public — the BrowserWindow must load the page before the
# renderer can obtain the token via preload IPC.
_PROTECTED_PREFIXES = ("/v4/",)


def get_auth_token() -> str | None:
    return os.environ.get("PLANNINGTREE_AUTH_TOKEN") or None


class AuthTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str | None = None) -> None:  # noqa: ANN001
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self._token is None:
            return await call_next(request)

        # Only gate API routes — let static assets / HTML through.
        if not request.url.path.startswith(_PROTECTED_PREFIXES):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if auth == f"Bearer {self._token}":
            return await call_next(request)

        # SSE EventSource cannot send headers; accept token via query param.
        query_token = request.query_params.get("token", "")
        if query_token == self._token:
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"code": "unauthorized", "message": "Invalid or missing auth token."},
        )
