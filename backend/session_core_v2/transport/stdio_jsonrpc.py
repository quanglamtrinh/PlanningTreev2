from __future__ import annotations

import json
import logging
import os
import queue
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
ServerRequestHandler = Callable[[Any, str, dict[str, Any]], None]
_QueuedServerRequest = tuple[Any, str, dict[str, Any]]


class StdioJsonRpcTransportV2:
    """Thin JSON-RPC 2.0 stdio transport for Codex app-server."""

    def __init__(
        self,
        *,
        codex_cmd: str | None,
        default_timeout_sec: int = 30,
        server_request_queue_capacity: int = 128,
    ) -> None:
        self._codex_cmd = str(codex_cmd or "codex").strip() or "codex"
        self._default_timeout_sec = max(1, int(default_timeout_sec))
        self._server_request_queue_capacity = max(1, int(server_request_queue_capacity))
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._server_request_worker_thread: threading.Thread | None = None
        self._pending: dict[str, Future[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._notification_handler: NotificationHandler | None = None
        self._server_request_handler: ServerRequestHandler | None = None
        self._server_request_queue: queue.Queue[_QueuedServerRequest] | None = None
        self._server_request_worker_stop = threading.Event()

    def set_notification_handler(self, handler: NotificationHandler) -> None:
        self._notification_handler = handler

    def set_server_request_handler(self, handler: ServerRequestHandler) -> None:
        self._server_request_handler = handler

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
        self._server_request_worker_stop.clear()
        self._server_request_queue = queue.Queue(maxsize=self._server_request_queue_capacity)
        self._server_request_worker_thread = threading.Thread(target=self._server_request_loop, daemon=True)
        self._server_request_worker_thread.start()

    def stop(self) -> None:
        process = self._process
        self._stop_server_request_worker(
            reject_pending=True,
            error_code=-32001,
            error_message="Session Core V2 transport shutting down.",
        )
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

    def respond_to_server_request(self, request_id: Any, result: dict[str, Any] | None = None) -> None:
        self._write_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result or {},
            }
        )

    def fail_server_request(self, request_id: Any, error: dict[str, Any] | None = None) -> None:
        payload_error: dict[str, Any]
        if isinstance(error, dict):
            payload_error = {
                "code": int(error.get("code", -32000)),
                "message": str(error.get("message") or "Server request rejected."),
            }
            if "data" in error:
                payload_error["data"] = error.get("data")
        else:
            payload_error = {
                "code": -32000,
                "message": "Server request rejected.",
            }
        self._write_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": payload_error,
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
            method = str(message.get("method") or "")
            params = message.get("params")
            if not isinstance(params, dict):
                params = {}
            self._enqueue_server_request(request_id=request_id, method=method, params=params)

    def _enqueue_server_request(self, *, request_id: Any, method: str, params: dict[str, Any]) -> None:
        request_queue = self._server_request_queue
        if request_queue is None:
            logger.warning(
                "session_core_v2 received server request %s without queue; rejecting",
                method,
            )
            self._reject_server_request_no_start(
                request_id=request_id,
                code=-32001,
                message="Session Core V2 server request queue is not available.",
            )
            return
        try:
            request_queue.put_nowait((request_id, method, dict(params)))
        except queue.Full:
            logger.warning(
                "session_core_v2 dropping server request %s because queue is full",
                method,
            )
            self._reject_server_request_no_start(
                request_id=request_id,
                code=-32001,
                message="Session Core V2 server request queue is full.",
            )

    def _server_request_loop(self) -> None:
        request_queue = self._server_request_queue
        if request_queue is None:
            return
        while not self._server_request_worker_stop.is_set():
            try:
                request_id, method, params = request_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            self._dispatch_server_request(request_id=request_id, method=method, params=params)

    def _dispatch_server_request(self, *, request_id: Any, method: str, params: dict[str, Any]) -> None:
        handler = self._server_request_handler
        if handler is None:
            logger.warning(
                "session_core_v2 received server request %s without handler; rejecting",
                method,
            )
            self._reject_server_request_no_start(
                request_id=request_id,
                code=-32001,
                message="Server request handler is not available.",
            )
            return
        try:
            handler(request_id, method, params)
        except Exception:
            logger.exception(
                "session_core_v2 server request handler failed for %s; rejecting",
                method,
            )
            self._reject_server_request_no_start(
                request_id=request_id,
                code=-32001,
                message="Session Core V2 rejected server request.",
            )

    def _stop_server_request_worker(
        self,
        *,
        reject_pending: bool,
        error_code: int,
        error_message: str,
    ) -> None:
        self._server_request_worker_stop.set()
        worker = self._server_request_worker_thread
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)
        self._server_request_worker_thread = None

        request_queue = self._server_request_queue
        self._server_request_queue = None
        if request_queue is None:
            return
        if not reject_pending:
            return
        while True:
            try:
                request_id, _, _ = request_queue.get_nowait()
            except queue.Empty:
                return
            self._reject_server_request_no_start(
                request_id=request_id,
                code=error_code,
                message=error_message,
            )

    def _reject_server_request_no_start(self, *, request_id: Any, code: int, message: str) -> None:
        try:
            self._write_json(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": int(code),
                        "message": str(message or "Server request rejected."),
                    },
                }
            )
        except SessionCoreError:
            logger.debug("session_core_v2 failed to reject server request %r", request_id, exc_info=True)

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
