"""Codex app server client over local stdio JSON-RPC."""

from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

_DEFAULT_TOOL_RESPONSE = {
    "success": True,
    "contentItems": [
        {
            "type": "inputText",
            "text": "Render payload received.",
        }
    ],
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def copy_plan_item(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return {
        "id": str(payload.get("id") or ""),
        "text": str(payload.get("text") or ""),
        "turn_id": str(payload.get("turn_id") or ""),
        "thread_id": str(payload.get("thread_id") or ""),
    }


@dataclass
class RuntimeRequestRecord:
    request_id: str
    rpc_request_id: str | int
    thread_id: str
    turn_id: str
    node_id: str | None
    item_id: str
    prompt_payload: dict[str, Any]
    created_at: str = field(default_factory=_iso_now)
    resolved_at: str | None = None
    status: str = "pending"
    answer_payload: dict[str, Any] | None = None


@dataclass
class _TurnState:
    event: threading.Event = field(default_factory=threading.Event)
    stdout_parts: list[str] = field(default_factory=list)
    final_text: str | None = None
    final_plan_item: dict[str, Any] | None = None
    error_message: str | None = None
    turn_status: str | None = None
    thread_id: str | None = None
    on_delta: Callable[[str], None] | None = None
    on_plan_delta: Callable[[str, dict[str, Any]], None] | None = None
    on_tool_call: Callable[[str, dict[str, Any]], None] | None = None
    on_request_user_input: Callable[[dict[str, Any]], None] | None = None
    on_request_resolved: Callable[[dict[str, Any]], None] | None = None
    on_thread_status: Callable[[dict[str, Any]], None] | None = None
    on_item_event: Callable[[str, dict[str, Any]], None] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    runtime_request_ids: list[str] = field(default_factory=list)


class CodexTransportError(Exception):
    """Base error for transport failures."""

    def __init__(self, message: str, error_code: str = "transport_error"):
        super().__init__(message)
        self.error_code = error_code


class CodexTransportTimeout(CodexTransportError):
    """Transport call timed out."""

    def __init__(self, message: str = "Transport timeout"):
        super().__init__(message, "timeout")


class CodexTransportNotFound(CodexTransportError):
    """Transport binary or service not found."""

    def __init__(self, message: str = "Transport not found"):
        super().__init__(message, "not_found")


class CodexTransport(ABC):
    """Abstract transport for sending prompts to Codex."""

    @abstractmethod
    def start(self) -> None:
        """Initialize the transport."""

    @abstractmethod
    def stop(self) -> None:
        """Tear down the transport cleanly."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Return True if the transport is ready to accept calls."""

    @abstractmethod
    def send_prompt(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send a prompt and return {"stdout": text, "thread_id": id}."""

    @abstractmethod
    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
        on_plan_delta: Callable[[str, dict[str, Any]], None] | None = None,
        on_request_user_input: Callable[[dict[str, Any]], None] | None = None,
        on_request_resolved: Callable[[dict[str, Any]], None] | None = None,
        on_item_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Send a prompt and stream deltas when available."""


class StdioTransport(CodexTransport):
    """Persistent child process running `codex app-server` over stdio."""

    def __init__(
        self,
        codex_cmd: str = "codex",
        api_key: str | None = None,
    ) -> None:
        self.codex_cmd = codex_cmd
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._pending: dict[int, Future[dict[str, Any]]] = {}
        self._turn_states: dict[str, _TurnState] = {}
        self._runtime_request_registry: dict[str, RuntimeRequestRecord] = {}
        self._thread_statuses: dict[str, dict[str, Any]] = {}
        self._loaded_threads: set[str] = set()
        self._account_updated_callbacks: set[Callable[[dict[str, Any]], None]] = set()
        self._rate_limits_updated_callbacks: set[Callable[[dict[str, Any]], None]] = set()
        self._next_id = 0
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._initialize_lock = threading.Lock()
        self._initialized = False
        self._initialized_notified = False

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        env = {**os.environ}
        if self.api_key:
            env["OPENAI_API_KEY"] = self.api_key
        try:
            self._process = subprocess.Popen(
                self._command_args(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                env=env,
            )
        except FileNotFoundError as exc:
            raise CodexTransportNotFound(
                f"Codex binary not found at '{self.codex_cmd}': {exc}"
            ) from exc
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr_loop, daemon=True)
        self._stderr_thread.start()
        self._initialized = False
        self._initialized_notified = False
        logger.info("StdioTransport started (pid=%s)", self._process.pid)

    def stop(self) -> None:
        proc = self._process
        if proc is None:
            return
        self._process = None
        self._reader_thread = None
        self._stderr_thread = None
        self._initialized = False
        self._initialized_notified = False
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        with self._lock:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(CodexTransportError("Transport stopped", "stopped"))
            self._pending.clear()
            for state in self._turn_states.values():
                if not state.error_message:
                    state.error_message = "Transport stopped"
                state.event.set()
            self._turn_states.clear()
            self._runtime_request_registry.clear()
            self._thread_statuses.clear()
            self._loaded_threads.clear()
        logger.info("StdioTransport stopped")

    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def send_prompt(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.send_prompt_streaming(
            prompt,
            thread_id=thread_id,
            timeout_sec=timeout_sec,
            cwd=cwd,
            writable_roots=writable_roots,
            on_delta=None,
        )

    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
        on_plan_delta: Callable[[str, dict[str, Any]], None] | None = None,
        on_request_user_input: Callable[[dict[str, Any]], None] | None = None,
        on_request_resolved: Callable[[dict[str, Any]], None] | None = None,
        on_item_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            raise CodexTransportNotFound("StdioTransport process is not alive")
        return self._send_prompt_modern(
            prompt,
            thread_id=thread_id,
            timeout_sec=timeout_sec,
            cwd=cwd,
            writable_roots=writable_roots,
            on_delta=on_delta,
            on_tool_call=on_tool_call,
            on_plan_delta=on_plan_delta,
            on_request_user_input=on_request_user_input,
            on_request_resolved=on_request_resolved,
            on_item_event=on_item_event,
        )

    def start_thread(
        self,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        persist_extended_history: bool = False,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            raise CodexTransportNotFound("StdioTransport process is not alive")
        self._initialize_session(timeout_sec)
        params: dict[str, Any] = {
            "cwd": cwd or None,
            "approvalPolicy": "never",
            "sandbox": self._thread_sandbox_mode(writable_roots),
            "experimentalRawEvents": True,
            "persistExtendedHistory": bool(persist_extended_history),
        }
        if base_instructions:
            params["baseInstructions"] = base_instructions
        if dynamic_tools:
            params["dynamicTools"] = dynamic_tools
        return self._rpc("thread/start", params, timeout=min(30, timeout_sec))

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        if not thread_id.strip():
            raise CodexTransportError("thread_id is required", "invalid_request")
        if not self.is_alive():
            raise CodexTransportNotFound("StdioTransport process is not alive")
        self._initialize_session(timeout_sec)
        return self._resume_thread_rpc(
            thread_id,
            cwd=cwd,
            timeout_sec=timeout_sec,
            writable_roots=writable_roots,
            enable_raw_events=True,
        )

    def fork_thread(
        self,
        source_thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        persist_extended_history: bool = False,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        if not source_thread_id.strip():
            raise CodexTransportError("source_thread_id is required", "invalid_request")
        if not self.is_alive():
            raise CodexTransportNotFound("StdioTransport process is not alive")
        self._initialize_session(timeout_sec)
        params: dict[str, Any] = {
            "threadId": source_thread_id,
            "cwd": cwd or None,
            "approvalPolicy": "never",
            "sandbox": self._thread_sandbox_mode(writable_roots),
            "persistExtendedHistory": bool(persist_extended_history),
        }
        if base_instructions:
            params["baseInstructions"] = base_instructions
        if dynamic_tools:
            params["dynamicTools"] = dynamic_tools
        return self._rpc("thread/fork", params, timeout=min(30, timeout_sec))

    def run_turn_streaming(
        self,
        input_text: str,
        *,
        thread_id: str,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
        on_plan_delta: Callable[[str, dict[str, Any]], None] | None = None,
        on_request_user_input: Callable[[dict[str, Any]], None] | None = None,
        on_request_resolved: Callable[[dict[str, Any]], None] | None = None,
        on_thread_status: Callable[[dict[str, Any]], None] | None = None,
        on_item_event: Callable[[str, dict[str, Any]], None] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            raise CodexTransportNotFound("StdioTransport process is not alive")
        return self._run_turn_streaming_unlocked(
            input_text,
            thread_id=thread_id,
            timeout_sec=timeout_sec,
            cwd=cwd,
            writable_roots=writable_roots,
            on_delta=on_delta,
            on_tool_call=on_tool_call,
            on_plan_delta=on_plan_delta,
            on_request_user_input=on_request_user_input,
            on_request_resolved=on_request_resolved,
            on_thread_status=on_thread_status,
            on_item_event=on_item_event,
            output_schema=output_schema,
            initialize_session=True,
        )

    def _command_args(self) -> list[str]:
        command = str(self.codex_cmd or "").strip()
        if command.lower().endswith(".py"):
            return [sys.executable, command, "app-server"]
        return [command or "codex", "app-server"]

    def _rpc(
        self,
        method: str,
        params: dict[str, Any],
        timeout: int = 30,
    ) -> dict[str, Any]:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id

        future: Future[dict[str, Any]] = Future()
        with self._lock:
            self._pending[request_id] = future
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )

        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise CodexTransportTimeout(f"RPC '{method}' timed out after {timeout}s") from exc

    def _send_json(self, payload: dict[str, Any]) -> None:
        proc = self._process
        if proc is None or proc.stdin is None:
            raise CodexTransportNotFound("StdioTransport process is not alive")
        message = json.dumps(payload, ensure_ascii=True)
        try:
            with self._write_lock:
                proc.stdin.write(message + "\n")
                proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodexTransportError(f"Failed to write to stdin: {exc}", "io_error") from exc

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._send_json(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )

    def _send_response(self, request_id: int, result: dict[str, Any]) -> None:
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        )

    def _send_prompt_modern(
        self,
        prompt: str,
        *,
        thread_id: str | None,
        timeout_sec: int,
        cwd: str | None,
        writable_roots: list[str] | None,
        on_delta: Callable[[str], None] | None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None,
        on_plan_delta: Callable[[str, dict[str, Any]], None] | None,
        on_request_user_input: Callable[[dict[str, Any]], None] | None,
        on_request_resolved: Callable[[dict[str, Any]], None] | None,
        on_item_event: Callable[[str, dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        self._initialize_session(timeout_sec)
        resolved_thread_id = thread_id
        if resolved_thread_id:
            self._resume_thread_rpc(
                resolved_thread_id,
                cwd=cwd,
                timeout_sec=min(10, timeout_sec),
                writable_roots=writable_roots,
                enable_raw_events=True,
            )
        else:
            response = self._rpc(
                "thread/start",
                {
                    "cwd": cwd or None,
                    "approvalPolicy": "never",
                    "sandbox": self._thread_sandbox_mode(writable_roots),
                    "experimentalRawEvents": True,
                    "persistExtendedHistory": False,
                },
                timeout=min(10, timeout_sec),
            )
            resolved_thread_id = self._extract_thread_id(response)
        return self._run_turn_streaming_unlocked(
            prompt,
            thread_id=resolved_thread_id,
            timeout_sec=timeout_sec,
            cwd=cwd,
            writable_roots=writable_roots,
            on_delta=on_delta,
            on_tool_call=on_tool_call,
            on_plan_delta=on_plan_delta,
            on_request_user_input=on_request_user_input,
            on_request_resolved=on_request_resolved,
            on_thread_status=None,
            on_item_event=on_item_event,
            output_schema=None,
            initialize_session=False,
        )

    def _run_turn_streaming_unlocked(
        self,
        input_text: str,
        *,
        thread_id: str,
        timeout_sec: int,
        cwd: str | None,
        writable_roots: list[str] | None,
        on_delta: Callable[[str], None] | None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None,
        on_plan_delta: Callable[[str, dict[str, Any]], None] | None,
        on_request_user_input: Callable[[dict[str, Any]], None] | None,
        on_request_resolved: Callable[[dict[str, Any]], None] | None,
        on_thread_status: Callable[[dict[str, Any]], None] | None,
        on_item_event: Callable[[str, dict[str, Any]], None] | None,
        output_schema: dict[str, Any] | None,
        initialize_session: bool,
    ) -> dict[str, Any]:
        if initialize_session:
            self._initialize_session(timeout_sec)
        turn_params: dict[str, Any] = {
            "threadId": thread_id,
            "cwd": cwd or None,
            "approvalPolicy": "never",
            "sandboxPolicy": self._turn_sandbox_policy(cwd, writable_roots),
            "input": [
                {
                    "type": "text",
                    "text": input_text,
                    "text_elements": [],
                }
            ],
        }
        if output_schema is not None:
            turn_params["outputSchema"] = output_schema
        turn_response = self._rpc("turn/start", turn_params, timeout=min(30, timeout_sec))
        turn = turn_response.get("turn", {})
        if not isinstance(turn, dict):
            raise CodexTransportError("turn/start returned invalid response", "rpc_error")
        turn_id = turn.get("id")
        if not isinstance(turn_id, str) or not turn_id.strip():
            raise CodexTransportError("turn/start did not return a turn id", "rpc_error")
        state = self._get_turn_state(turn_id)
        completed_early = (
            state.event.is_set()
            or state.turn_status is not None
            or state.error_message is not None
        )
        if not completed_early:
            state.event.clear()
            state.stdout_parts = []
            state.final_text = None
            state.final_plan_item = None
            state.error_message = None
            state.turn_status = None
            state.tool_calls = []
            state.runtime_request_ids = []
        state.thread_id = thread_id
        state.on_delta = on_delta
        state.on_tool_call = on_tool_call
        state.on_plan_delta = on_plan_delta
        state.on_request_user_input = on_request_user_input
        state.on_request_resolved = on_request_resolved
        state.on_thread_status = on_thread_status
        state.on_item_event = on_item_event
        if on_delta is not None and state.stdout_parts:
            for chunk in list(state.stdout_parts):
                self._emit_delta(state, chunk)

        wait_result = self._wait_for_turn_result(turn_id, timeout_sec)
        if len(wait_result) == 2:
            stdout, tool_calls = wait_result
            turn_status = None
            final_plan_item = None
            runtime_request_ids = []
        else:
            stdout, tool_calls, turn_status, final_plan_item, runtime_request_ids = wait_result
        return {
            "stdout": stdout,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "tool_calls": tool_calls,
            "turn_status": turn_status,
            "final_plan_item": final_plan_item,
            "runtime_request_ids": runtime_request_ids,
        }

    def _thread_sandbox_mode(self, writable_roots: list[str] | None) -> str:
        if self._normalize_writable_roots(writable_roots):
            return "workspace-write"
        return "danger-full-access"

    def _turn_sandbox_policy(
        self,
        cwd: str | None,
        writable_roots: list[str] | None,
    ) -> dict[str, Any]:
        normalized_roots = self._normalize_writable_roots(writable_roots)
        if not normalized_roots:
            return {"type": "dangerFullAccess"}

        readable_roots: list[str] = []
        if isinstance(cwd, str) and cwd.strip():
            readable_roots.append(cwd.strip())
        readable_roots.extend(normalized_roots)
        readable_roots = self._dedupe_preserve_order(readable_roots)

        return {
            "type": "workspaceWrite",
            "writableRoots": normalized_roots,
            "readOnlyAccess": {
                "type": "fullAccess",
                "includePlatformDefaults": True,
                "readableRoots": readable_roots,
            },
            "networkAccess": False,
            "excludeTmpdirEnvVar": False,
            "excludeSlashTmp": False,
        }

    def _normalize_writable_roots(self, writable_roots: list[str] | None) -> list[str]:
        if not isinstance(writable_roots, list):
            return []
        roots = [item.strip() for item in writable_roots if isinstance(item, str) and item.strip()]
        return self._dedupe_preserve_order(roots)

    def _dedupe_preserve_order(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def _initialize_session(self, timeout_sec: int) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            self._rpc(
                "initialize",
                {
                    "clientInfo": {
                        "name": "PlanningTree",
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "experimentalApi": True,
                    },
                },
                timeout=min(10, timeout_sec),
            )
            if not self._initialized_notified:
                self._notify("initialized", {})
                self._initialized_notified = True
            self._initialized = True

    def list_loaded_threads(
        self,
        *,
        timeout_sec: int = 30,
        limit: int | None = None,
    ) -> dict[str, Any]:
        self._initialize_session(timeout_sec)
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = max(1, int(limit))
        return self._rpc("thread/loaded/list", params, timeout=min(30, timeout_sec))

    def read_thread(
        self,
        thread_id: str,
        *,
        include_turns: bool = False,
        timeout_sec: int = 30,
    ) -> dict[str, Any]:
        if not thread_id.strip():
            raise CodexTransportError("thread_id is required", "invalid_request")
        self._initialize_session(timeout_sec)
        return self._rpc(
            "thread/read",
            {"threadId": thread_id, "includeTurns": bool(include_turns)},
            timeout=min(30, timeout_sec),
        )

    def read_account(self, *, timeout_sec: int = 30) -> dict[str, Any]:
        self._initialize_session(timeout_sec)
        return self._rpc("account/read", {}, timeout=min(30, timeout_sec))

    def read_rate_limits(self, *, timeout_sec: int = 30) -> dict[str, Any]:
        self._initialize_session(timeout_sec)
        return self._rpc("account/rateLimits/read", {}, timeout=min(30, timeout_sec))

    def add_account_updated_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._account_updated_callbacks.add(callback)

    def add_rate_limits_updated_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._rate_limits_updated_callbacks.add(callback)

    def get_runtime_request(self, request_id: str) -> RuntimeRequestRecord | None:
        with self._lock:
            record = self._runtime_request_registry.get(str(request_id))
            if record is None:
                return None
            return RuntimeRequestRecord(**record.__dict__)

    def resolve_runtime_request_user_input(
        self,
        request_id: str,
        *,
        answers: dict[str, Any],
    ) -> RuntimeRequestRecord | None:
        request_key = str(request_id)
        with self._lock:
            record = self._runtime_request_registry.get(request_key)
            if record is None:
                return None
            if record.status != "pending":
                return RuntimeRequestRecord(**record.__dict__)
            rpc_request_id = record.rpc_request_id

        self._send_response(
            rpc_request_id,
            {
                "answers": answers,
            },
        )

        with self._lock:
            record = self._runtime_request_registry.get(request_key)
            if record is None:
                return None
            if record.status == "pending":
                record.status = "resolved"
                record.answer_payload = {"answers": answers}
                record.resolved_at = _iso_now()
            return RuntimeRequestRecord(**record.__dict__)

    def _extract_thread_id(self, payload: dict[str, Any]) -> str:
        thread = payload.get("thread", {})
        if isinstance(thread, dict):
            thread_id = thread.get("id")
            if isinstance(thread_id, str) and thread_id.strip():
                return thread_id
        thread_id = payload.get("thread_id")
        if isinstance(thread_id, str) and thread_id.strip():
            return thread_id
        raise CodexTransportError("App server did not return a thread id", "rpc_error")

    def _get_turn_state(self, turn_id: str) -> _TurnState:
        with self._lock:
            state = self._turn_states.get(turn_id)
            if state is None:
                state = _TurnState()
                self._turn_states[turn_id] = state
            return state

    def _wait_for_turn_result(
        self,
        turn_id: str,
        timeout_sec: int,
    ) -> tuple[str, list[dict[str, Any]], str | None, dict[str, Any] | None, list[str]]:
        state = self._get_turn_state(turn_id)
        if not state.event.wait(timeout_sec):
            with self._lock:
                self._turn_states.pop(turn_id, None)
            raise CodexTransportTimeout(f"turn/start timed out after {timeout_sec}s")

        with self._lock:
            self._turn_states.pop(turn_id, None)

        if state.error_message:
            raise CodexTransportError(state.error_message, "rpc_error")
        if state.stdout_parts:
            stdout = "".join(state.stdout_parts)
        else:
            stdout = state.final_text or ""
        final_plan_item = copy_plan_item(state.final_plan_item)
        return (
            stdout,
            list(state.tool_calls),
            state.turn_status,
            final_plan_item,
            list(state.runtime_request_ids),
        )

    def _emit_delta(self, state: _TurnState, delta: str) -> None:
        callback = state.on_delta
        if callback is None:
            return
        try:
            callback(delta)
        except Exception:
            logger.debug("StdioTransport delta callback failed", exc_info=True)

    def _emit_tool_call(
        self,
        state: _TurnState,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        callback = state.on_tool_call
        if callback is None:
            return
        try:
            callback(tool_name, arguments)
        except Exception:
            logger.debug("StdioTransport tool callback failed", exc_info=True)

    def _emit_plan_delta(self, state: _TurnState, delta: str, item: dict[str, Any]) -> None:
        callback = state.on_plan_delta
        if callback is None:
            return
        try:
            callback(delta, item)
        except Exception:
            logger.debug("StdioTransport plan delta callback failed", exc_info=True)

    def _emit_request_user_input(self, state: _TurnState, payload: dict[str, Any]) -> None:
        callback = state.on_request_user_input
        if callback is None:
            return
        try:
            callback(payload)
        except Exception:
            logger.debug("StdioTransport requestUserInput callback failed", exc_info=True)

    def _emit_request_resolved(self, state: _TurnState, payload: dict[str, Any]) -> None:
        callback = state.on_request_resolved
        if callback is None:
            return
        try:
            callback(payload)
        except Exception:
            logger.debug("StdioTransport request resolved callback failed", exc_info=True)

    def _emit_thread_status(self, state: _TurnState, payload: dict[str, Any]) -> None:
        callback = state.on_thread_status
        if callback is None:
            return
        try:
            callback(payload)
        except Exception:
            logger.debug("StdioTransport thread status callback failed", exc_info=True)

    def _emit_item_event(self, state: _TurnState, phase: str, item: dict[str, Any]) -> None:
        callback = state.on_item_event
        if callback is None:
            return
        try:
            callback(phase, copy.deepcopy(item))
        except Exception:
            logger.debug("StdioTransport item callback failed", exc_info=True)

    def _emit_global_notification_callbacks(
        self,
        callbacks: tuple[Callable[[dict[str, Any]], None], ...],
        payload: dict[str, Any],
        label: str,
    ) -> None:
        for callback in callbacks:
            try:
                callback(copy.deepcopy(payload))
            except Exception:
                logger.debug("StdioTransport %s callback failed", label, exc_info=True)

    def _handle_notification(self, method: str, params: Any) -> None:
        if not isinstance(params, dict):
            return

        if method == "account/updated":
            with self._lock:
                callbacks = tuple(self._account_updated_callbacks)
            self._emit_global_notification_callbacks(callbacks, params, "account/updated")
            return

        if method == "account/rateLimits/updated":
            with self._lock:
                callbacks = tuple(self._rate_limits_updated_callbacks)
            self._emit_global_notification_callbacks(
                callbacks,
                params,
                "account/rateLimits/updated",
            )
            return

        if method == "thread/status/changed":
            thread_id = params.get("threadId")
            status = params.get("status")
            if not isinstance(thread_id, str) or not isinstance(status, dict):
                return
            thread_payload = {
                "thread_id": thread_id,
                "status": status,
            }
            with self._lock:
                self._thread_statuses[thread_id] = thread_payload
                if status.get("type") == "notLoaded":
                    self._loaded_threads.discard(thread_id)
                else:
                    self._loaded_threads.add(thread_id)
                matching_states = [
                    state for state in self._turn_states.values() if state.thread_id == thread_id
                ]
            for state in matching_states:
                self._emit_thread_status(state, thread_payload)
            return

        if method == "item/agentMessage/delta":
            turn_id = params.get("turnId")
            delta = params.get("delta")
            if isinstance(turn_id, str) and isinstance(delta, str):
                state = self._get_turn_state(turn_id)
                state.stdout_parts.append(delta)
                self._emit_delta(state, delta)
            return

        if method == "item/plan/delta":
            turn_id = params.get("turnId")
            thread_id = params.get("threadId")
            item_id = params.get("itemId")
            delta = params.get("delta")
            if (
                isinstance(turn_id, str)
                and isinstance(thread_id, str)
                and isinstance(item_id, str)
                and isinstance(delta, str)
            ):
                state = self._get_turn_state(turn_id)
                self._emit_plan_delta(
                    state,
                    delta,
                    {
                        "id": item_id,
                        "turn_id": turn_id,
                        "thread_id": thread_id,
                    },
                )
            return

        if method == "item/started":
            turn_id = params.get("turnId")
            item = params.get("item", {})
            if not isinstance(turn_id, str) or not isinstance(item, dict):
                return
            state = self._get_turn_state(turn_id)
            self._emit_item_event(state, "started", item)
            return

        if method == "item/completed":
            turn_id = params.get("turnId")
            thread_id = params.get("threadId")
            item = params.get("item", {})
            if not isinstance(turn_id, str) or not isinstance(thread_id, str) or not isinstance(item, dict):
                return
            state = self._get_turn_state(turn_id)
            self._emit_item_event(state, "completed", item)
            item_type = item.get("type")
            if item_type == "agentMessage":
                text = item.get("text")
                if isinstance(text, str) and not state.stdout_parts:
                    state.final_text = text
            elif item_type == "plan":
                text = item.get("text")
                item_id = item.get("id")
                if isinstance(text, str) and isinstance(item_id, str):
                    state.final_plan_item = {
                        "id": item_id,
                        "text": text,
                        "turn_id": turn_id,
                        "thread_id": thread_id,
                    }
            return

        if method == "turn/completed":
            turn = params.get("turn", {})
            thread_id = params.get("threadId")
            if not isinstance(turn, dict):
                return
            turn_id = turn.get("id")
            if not isinstance(turn_id, str) or not isinstance(thread_id, str):
                return
            state = self._get_turn_state(turn_id)
            status = str(turn.get("status", "")).strip().lower()
            state.turn_status = status or None
            state.thread_id = thread_id
            error = turn.get("error")
            if status == "failed":
                if isinstance(error, dict):
                    message = error.get("message")
                    if isinstance(message, str) and message.strip():
                        state.error_message = message
                    else:
                        state.error_message = json.dumps(error, ensure_ascii=True)
                else:
                    state.error_message = "App server turn failed"
            elif status == "interrupted":
                state.error_message = "App server turn was interrupted"
            state.event.set()
            return

        if method == "serverRequest/resolved":
            thread_id = params.get("threadId")
            request_id = params.get("requestId")
            if not isinstance(thread_id, str) or request_id is None:
                return
            request_key = str(request_id)
            with self._lock:
                record = self._runtime_request_registry.get(request_key)
                if record is None:
                    return
                if record.status == "pending":
                    record.status = "stale"
                if not record.resolved_at:
                    record.resolved_at = _iso_now()
                state = self._turn_states.get(record.turn_id)
                payload = {
                    "request_id": record.request_id,
                    "thread_id": record.thread_id,
                    "turn_id": record.turn_id,
                    "status": record.status,
                    "resolved_at": record.resolved_at,
                }
            if state is not None:
                self._emit_request_resolved(state, payload)
            return

        if method == "error":
            turn_id = params.get("turnId")
            if not isinstance(turn_id, str):
                return
            state = self._get_turn_state(turn_id)
            error = params.get("error")
            if isinstance(error, dict):
                state.error_message = str(error.get("message") or json.dumps(error, ensure_ascii=True))
            else:
                state.error_message = str(params.get("message") or "App server error")
            state.event.set()

    def _handle_server_request(self, message_id: str | int, method: str, params: Any) -> None:
        if method == "item/tool/requestUserInput":
            if not isinstance(params, dict):
                self._send_response(message_id, {"answers": {}})
                return

            thread_id = params.get("threadId")
            turn_id = params.get("turnId")
            item_id = params.get("itemId")
            questions = params.get("questions")
            if (
                not isinstance(thread_id, str)
                or not isinstance(turn_id, str)
                or not isinstance(item_id, str)
                or not isinstance(questions, list)
            ):
                self._send_response(message_id, {"answers": {}})
                return

            request_key = str(message_id)
            record = RuntimeRequestRecord(
                request_id=request_key,
                rpc_request_id=message_id,
                thread_id=thread_id,
                turn_id=turn_id,
                node_id=None,
                item_id=item_id,
                prompt_payload={
                    "item_id": item_id,
                    "questions": questions,
                },
            )
            with self._lock:
                self._runtime_request_registry[request_key] = record
                state = self._turn_states.get(turn_id)
                if state is not None and request_key not in state.runtime_request_ids:
                    state.runtime_request_ids.append(request_key)
            if state is not None:
                self._emit_request_user_input(
                    state,
                    {
                        "request_id": record.request_id,
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "item_id": item_id,
                        "questions": list(questions),
                        "created_at": record.created_at,
                        "status": record.status,
                    },
                )
            return

        if method != "item/tool/call":
            return

        if not isinstance(params, dict):
            self._send_response(
                message_id,
                {
                    "success": False,
                    "contentItems": [
                        {
                            "type": "inputText",
                            "text": "Invalid tool call payload.",
                        }
                    ],
                },
            )
            return

        turn_id = params.get("turnId")
        tool_name = params.get("tool") or params.get("name") or params.get("toolName")
        tool_arguments = params.get("arguments")
        arguments = tool_arguments if isinstance(tool_arguments, dict) else {}

        if isinstance(turn_id, str) and isinstance(tool_name, str):
            state = self._get_turn_state(turn_id)
            tool_call = {
                "tool_name": tool_name,
                "arguments": arguments,
                "call_id": params.get("callId"),
                "turn_id": turn_id,
                "thread_id": params.get("threadId"),
            }
            state.tool_calls.append(tool_call)
            self._emit_tool_call(state, tool_name, arguments)

        try:
            self._send_response(message_id, _DEFAULT_TOOL_RESPONSE)
        except Exception:
            logger.debug("Failed to respond to dynamic tool request", exc_info=True)

    def _resume_thread_rpc(
        self,
        thread_id: str,
        *,
        cwd: str | None,
        timeout_sec: int,
        writable_roots: list[str] | None,
        enable_raw_events: bool,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "cwd": cwd or None,
            "approvalPolicy": "never",
            "sandbox": self._thread_sandbox_mode(writable_roots),
            "persistExtendedHistory": False,
        }
        if enable_raw_events:
            params["experimentalRawEvents"] = True
        try:
            return self._rpc(
                "thread/resume",
                params,
                timeout=min(30, timeout_sec),
            )
        except CodexTransportError as exc:
            if not enable_raw_events or not self._resume_raw_events_unsupported(exc):
                raise
            params.pop("experimentalRawEvents", None)
            return self._rpc(
                "thread/resume",
                params,
                timeout=min(30, timeout_sec),
            )

    @staticmethod
    def _resume_raw_events_unsupported(exc: Exception) -> bool:
        message = str(exc).lower()
        return "experimentalrawevents" in message and (
            "unknown field" in message or "invalid request" in message
        )

    def _read_loop(self) -> None:
        proc = self._process
        if proc is None or proc.stdout is None:
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("StdioTransport: non-JSON line: %s", line[:200])
                    continue

                method = message.get("method")
                message_id = message.get("id")
                if message_id is not None and isinstance(method, str):
                    self._handle_server_request(message_id, method, message.get("params"))
                    continue

                if message_id is not None:
                    with self._lock:
                        future = self._pending.pop(message_id, None)
                    if future is None:
                        continue
                    if "error" in message:
                        error = message["error"]
                        if isinstance(error, dict):
                            future.set_exception(
                                CodexTransportError(error.get("message", "RPC error"), "rpc_error")
                            )
                        else:
                            future.set_exception(CodexTransportError("RPC error", "rpc_error"))
                    else:
                        future.set_result(message.get("result", {}))
                    continue

                if isinstance(method, str):
                    self._handle_notification(method, message.get("params"))
        except Exception:
            logger.debug("StdioTransport reader loop exited", exc_info=True)
        finally:
            with self._lock:
                for future in list(self._pending.values()):
                    if not future.done():
                        future.set_exception(
                            CodexTransportError("Reader loop ended", "reader_closed")
                        )
                self._pending.clear()
                for state in self._turn_states.values():
                    if not state.error_message:
                        state.error_message = "Reader loop ended"
                    state.event.set()
                self._turn_states.clear()

    def _read_stderr_loop(self) -> None:
        proc = self._process
        if proc is None or proc.stderr is None:
            return
        try:
            for raw_line in proc.stderr:
                line = raw_line.rstrip()
                if not line:
                    continue
                logger.debug("StdioTransport stderr: %s", line[:500])
        except Exception:
            logger.debug("StdioTransport stderr loop exited", exc_info=True)


class CodexAppClient:
    """High-level client wrapping a CodexTransport."""

    def __init__(self, transport: CodexTransport) -> None:
        self._transport = transport
        self._started = False

    def start(self) -> None:
        self._transport.start()
        self._started = True

    def stop(self) -> None:
        if self._started:
            self._transport.stop()
            self._started = False

    def restart(self) -> None:
        self.stop()
        self.start()

    def is_alive(self) -> bool:
        return self._started and self._transport.is_alive()

    def status(self) -> dict[str, Any]:
        return {
            "client_class": type(self).__name__,
            "transport_class": type(self._transport).__name__,
            "client_started": self._started,
            "client_alive": self.is_alive(),
        }

    def probe(self, timeout_sec: int = 10, cwd: str | None = None) -> dict[str, Any]:
        response = self.send_prompt(
            "Reply with the exact text OK.",
            timeout_sec=max(1, int(timeout_sec)),
            cwd=cwd,
        )
        stdout = str(response.get("stdout", ""))
        return {
            "ok": True,
            "thread_id": response.get("thread_id"),
            "stdout_preview": stdout[:120],
        }

    def send_prompt(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.send_prompt_streaming(
            prompt,
            thread_id=thread_id,
            timeout_sec=timeout_sec,
            cwd=cwd,
            writable_roots=writable_roots,
            on_delta=None,
        )

    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
        on_plan_delta: Callable[[str, dict[str, Any]], None] | None = None,
        on_request_user_input: Callable[[dict[str, Any]], None] | None = None,
        on_request_resolved: Callable[[dict[str, Any]], None] | None = None,
        on_item_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport_kwargs: dict[str, Any] = {
            "thread_id": thread_id,
            "timeout_sec": timeout_sec,
            "cwd": cwd,
            "on_delta": on_delta,
            "on_tool_call": on_tool_call,
            "on_plan_delta": on_plan_delta,
            "on_request_user_input": on_request_user_input,
            "on_request_resolved": on_request_resolved,
            "on_item_event": on_item_event,
        }
        if writable_roots is not None:
            transport_kwargs["writable_roots"] = writable_roots
        return self._transport.send_prompt_streaming(
            prompt,
            **transport_kwargs,
        )

    def start_planning_thread(
        self,
        *,
        base_instructions: str,
        dynamic_tools: list[dict[str, Any]],
        cwd: str | None = None,
        timeout_sec: int = 30,
    ) -> dict[str, Any]:
        return self.start_thread(
            base_instructions=base_instructions,
            dynamic_tools=dynamic_tools,
            cwd=cwd,
            timeout_sec=timeout_sec,
        )

    def start_thread(
        self,
        *,
        base_instructions: str,
        dynamic_tools: list[dict[str, Any]],
        cwd: str | None = None,
        timeout_sec: int = 30,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        response = transport.start_thread(
            cwd=cwd,
            timeout_sec=timeout_sec,
            base_instructions=base_instructions,
            dynamic_tools=dynamic_tools,
            writable_roots=writable_roots,
        )
        return {"thread_id": transport._extract_thread_id(response)}

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        response = transport.resume_thread(
            thread_id,
            cwd=cwd,
            timeout_sec=timeout_sec,
            writable_roots=writable_roots,
        )
        return {"thread_id": transport._extract_thread_id(response)}

    def fork_thread(
        self,
        source_thread_id: str,
        *,
        cwd: str | None = None,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        timeout_sec: int = 30,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        response = transport.fork_thread(
            source_thread_id,
            cwd=cwd,
            timeout_sec=timeout_sec,
            base_instructions=base_instructions,
            dynamic_tools=dynamic_tools,
            writable_roots=writable_roots,
        )
        return {"thread_id": transport._extract_thread_id(response)}

    def run_turn_streaming(
        self,
        prompt: str,
        *,
        thread_id: str,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
        on_plan_delta: Callable[[str, dict[str, Any]], None] | None = None,
        on_request_user_input: Callable[[dict[str, Any]], None] | None = None,
        on_request_resolved: Callable[[dict[str, Any]], None] | None = None,
        on_thread_status: Callable[[dict[str, Any]], None] | None = None,
        on_item_event: Callable[[str, dict[str, Any]], None] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        return transport.run_turn_streaming(
            prompt,
            thread_id=thread_id,
            timeout_sec=timeout_sec,
            cwd=cwd,
            writable_roots=writable_roots,
            on_delta=on_delta,
            on_tool_call=on_tool_call,
            on_plan_delta=on_plan_delta,
            on_request_user_input=on_request_user_input,
            on_request_resolved=on_request_resolved,
            on_thread_status=on_thread_status,
            on_item_event=on_item_event,
            output_schema=output_schema,
        )

    def list_loaded_threads(
        self,
        *,
        timeout_sec: int = 30,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        return transport.list_loaded_threads(timeout_sec=timeout_sec, limit=limit)

    def read_thread(
        self,
        thread_id: str,
        *,
        include_turns: bool = False,
        timeout_sec: int = 30,
    ) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        return transport.read_thread(
            thread_id,
            include_turns=include_turns,
            timeout_sec=timeout_sec,
        )

    def read_account(self, *, timeout_sec: int = 30) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        return transport.read_account(timeout_sec=timeout_sec)

    def read_rate_limits(self, *, timeout_sec: int = 30) -> dict[str, Any]:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        return transport.read_rate_limits(timeout_sec=timeout_sec)

    def add_account_updated_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._require_stdio_transport().add_account_updated_listener(callback)

    def add_rate_limits_updated_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._require_stdio_transport().add_rate_limits_updated_listener(callback)

    def get_runtime_request(self, request_id: str) -> RuntimeRequestRecord | None:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        return transport.get_runtime_request(request_id)

    def resolve_runtime_request_user_input(
        self,
        request_id: str,
        *,
        answers: dict[str, Any],
    ) -> RuntimeRequestRecord | None:
        if not self.is_alive():
            self.start()
        transport = self._require_stdio_transport()
        return transport.resolve_runtime_request_user_input(request_id, answers=answers)

    def _require_stdio_transport(self) -> StdioTransport:
        if not isinstance(self._transport, StdioTransport):
            raise CodexTransportError(
                "Unsupported transport for thread operations",
                "unsupported_transport",
            )
        return self._transport
