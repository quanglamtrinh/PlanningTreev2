from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from typing import Any

from backend.session_core_v2.errors import SessionCoreError

logger = logging.getLogger(__name__)

NotificationHandler = Callable[[str, dict[str, Any]], None]


class StdioJsonRpcTransportV2:
    """Thin JSON-RPC 2.0 stdio transport for Codex app-server."""

    def __init__(
        self,
        *,
        codex_cmd: str | None,
        default_timeout_sec: int = 30,
    ) -> None:
        self._codex_cmd = str(codex_cmd or "codex").strip() or "codex"
        self._default_timeout_sec = max(1, int(default_timeout_sec))
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._pending: dict[str, Future[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._notification_handler: NotificationHandler | None = None

    def set_notification_handler(self, handler: NotificationHandler) -> None:
        self._notification_handler = handler

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        env = {**os.environ}
        command = self._command_args()
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
            )
        except FileNotFoundError as exc:
            raise SessionCoreError(
                code="ERR_PROVIDER_UNAVAILABLE",
                message=f"Codex binary not found for Session Core V2: {self._codex_cmd}",
                status_code=503,
                details={"command": command, "reason": str(exc)},
            ) from exc
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_thread.start()

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        self._process = None
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        with self._pending_lock:
            for pending in self._pending.values():
                if not pending.done():
                    pending.set_exception(
                        SessionCoreError(
                            code="ERR_PROVIDER_UNAVAILABLE",
                            message="Transport stopped",
                            status_code=503,
                            details={},
                        )
                    )
            self._pending.clear()

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        self.start()
        request_id = str(uuid.uuid4())
        future: Future[dict[str, Any]] = Future()
        with self._pending_lock:
            self._pending[request_id] = future
        self._write_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        effective_timeout = timeout_sec if timeout_sec is not None else self._default_timeout_sec
        try:
            return future.result(timeout=max(1, int(effective_timeout)))
        except FutureTimeoutError as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise SessionCoreError(
                code="ERR_PROVIDER_UNAVAILABLE",
                message=f"RPC timeout for method {method!r}.",
                status_code=503,
                details={"method": method, "timeoutSec": effective_timeout},
            ) from exc

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.start()
        self._write_json(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
        )

    def _read_loop(self) -> None:
        while True:
            process = self._process
            if process is None or process.stdout is None:
                return
            line = process.stdout.readline()
            if not line:
                return
            try:
                message = json.loads(line)
            except Exception:
                logger.debug("session_core_v2: ignoring non-json line: %s", line.strip())
                continue
            self._handle_incoming_message(message)

    def _stderr_loop(self) -> None:
        while True:
            process = self._process
            if process is None or process.stderr is None:
                return
            line = process.stderr.readline()
            if not line:
                return
            logger.debug("session_core_v2 app-server stderr: %s", line.rstrip())

    def _handle_incoming_message(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            request_id = str(message.get("id"))
            with self._pending_lock:
                pending = self._pending.pop(request_id, None)
            if pending is None:
                return
            if "error" in message:
                pending.set_exception(self._map_rpc_error(message.get("error")))
                return
            result = message.get("result")
            if isinstance(result, dict):
                pending.set_result(result)
            else:
                pending.set_result({"result": result})
            return

        if "method" in message and "id" not in message:
            method = str(message.get("method") or "")
            params = message.get("params")
            if not isinstance(params, dict):
                params = {}
            handler = self._notification_handler
            if handler is not None:
                try:
                    handler(method, params)
                except Exception:
                    logger.debug("session_core_v2 notification handler failed", exc_info=True)
            return

        if "method" in message and "id" in message:
            request_id = message.get("id")
            logger.warning(
                "session_core_v2 received unsupported server request %s; auto-ack empty result",
                message.get("method"),
            )
            self._write_json(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {},
                }
            )

    def _write_json(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise SessionCoreError(
                code="ERR_PROVIDER_UNAVAILABLE",
                message="Transport is not running.",
                status_code=503,
                details={},
            )
        serialized = json.dumps(payload, ensure_ascii=True)
        try:
            with self._write_lock:
                process.stdin.write(serialized + "\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise SessionCoreError(
                code="ERR_PROVIDER_UNAVAILABLE",
                message="Failed to write JSON-RPC payload to app-server.",
                status_code=503,
                details={"reason": str(exc)},
            ) from exc

    def _command_args(self) -> list[str]:
        command = self._codex_cmd
        if command.lower().endswith(".py"):
            return [sys.executable, command, "app-server"]
        return [command, "app-server"]

    @staticmethod
    def _map_rpc_error(error: Any) -> SessionCoreError:
        if not isinstance(error, dict):
            return SessionCoreError(
                code="ERR_PROVIDER_UNAVAILABLE",
                message="Malformed JSON-RPC error response.",
                status_code=502,
                details={},
            )
        code = int(error.get("code", -32000))
        message = str(error.get("message") or "Unknown JSON-RPC error")
        if "not initialized" in message.lower():
            mapped_code = "ERR_SESSION_NOT_INITIALIZED"
            status_code = 409
        elif code == -32602:
            mapped_code = "ERR_INTERNAL"
            status_code = 400
        else:
            mapped_code = "ERR_PROVIDER_UNAVAILABLE"
            status_code = 502
        return SessionCoreError(
            code=mapped_code,
            message=message,
            status_code=status_code,
            details={"rpcCode": code, "rpcData": error.get("data")},
        )

