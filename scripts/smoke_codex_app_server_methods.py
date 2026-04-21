from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _resolve_codex_cmd(explicit: str | None) -> str | None:
    if explicit:
        candidate = str(explicit).strip()
        if not candidate:
            return None
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return str(Path(resolved).resolve())
        return None

    env_cmd = str(os.environ.get("PLANNINGTREE_CODEX_CMD", "") or "").strip()
    if env_cmd:
        resolved = _resolve_codex_cmd(env_cmd)
        if resolved:
            return resolved

    for candidate in ("codex.cmd", "codex.exe", "codex"):
        resolved = shutil.which(candidate)
        if resolved:
            return str(Path(resolved).resolve())
    return None


def _looks_like_unsupported_method(error_obj: dict[str, Any], method_name: str) -> bool:
    msg = str(error_obj.get("message") or "").lower()
    if method_name.lower() not in msg:
        return False
    return ("unknown variant" in msg) or ("method not found" in msg)


@dataclass
class ProbeResult:
    ok: bool
    codex_cmd: str
    method_supported: bool
    error_code: int | None = None
    error_message: str | None = None
    detail: str | None = None


class StdioJsonRpcProbe:
    def __init__(self, codex_cmd: str) -> None:
        self.codex_cmd = codex_cmd
        self._proc: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._stop = threading.Event()
        self._next_id = 1
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        cmd = [self.codex_cmd, "app-server"]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except PermissionError:
            self._proc = subprocess.Popen(
                ["cmd", "/c", self.codex_cmd, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise RuntimeError(f"failed to start app-server: {exc}") from exc

        if self._proc.stdout is None or self._proc.stderr is None:
            raise RuntimeError("failed to capture stdio for app-server process")

        def _read_stdout() -> None:
            assert self._proc is not None and self._proc.stdout is not None
            for raw in self._proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    self._stderr_lines.append(f"[stdout-nonjson] {line}")
                    continue
                self._stdout_queue.put(payload)
                if self._stop.is_set():
                    return

        def _read_stderr() -> None:
            assert self._proc is not None and self._proc.stderr is not None
            for raw in self._proc.stderr:
                line = raw.rstrip("\r\n")
                if line:
                    self._stderr_lines.append(line)
                if self._stop.is_set():
                    return

        self._stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def close(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

    def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("app-server process is not running")
        proc.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
        proc.stdin.flush()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
        )

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: float) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        deadline = time.time() + timeout_sec
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"timeout waiting for response id={request_id} method={method}")
            try:
                msg = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(f"timeout waiting for response id={request_id} method={method}") from exc
            if msg.get("id") == request_id:
                return msg

    @property
    def stderr_text(self) -> str:
        return "\n".join(self._stderr_lines[-30:])


def run_smoke(codex_cmd: str, *, timeout_sec: float) -> ProbeResult:
    probe = StdioJsonRpcProbe(codex_cmd)
    probe.start()
    try:
        init = probe.request(
            "initialize",
            {
                "protocolVersion": "2",
                "clientInfo": {"name": "planningtree-smoke", "version": "1"},
            },
            timeout_sec=timeout_sec,
        )
        if "error" in init:
            err = init["error"] if isinstance(init["error"], dict) else {}
            return ProbeResult(
                ok=False,
                codex_cmd=codex_cmd,
                method_supported=False,
                error_code=int(err.get("code", -1)),
                error_message=str(err.get("message") or "initialize failed"),
                detail=probe.stderr_text,
            )

        probe.notify("initialized", {})

        loaded_resp = probe.request("thread/loaded/list", {}, timeout_sec=timeout_sec)
        if "error" in loaded_resp:
            err = loaded_resp["error"] if isinstance(loaded_resp["error"], dict) else {}
            return ProbeResult(
                ok=False,
                codex_cmd=codex_cmd,
                method_supported=False,
                error_code=int(err.get("code", -1)),
                error_message=f"thread/loaded/list failed: {err.get('message')}",
                detail=probe.stderr_text,
            )

        thread_id = f"probe-{uuid.uuid4()}"
        turns_resp = probe.request(
            "thread/turns/list",
            {"threadId": thread_id, "limit": 1},
            timeout_sec=timeout_sec,
        )

        if "error" in turns_resp:
            err = turns_resp["error"] if isinstance(turns_resp["error"], dict) else {}
            if _looks_like_unsupported_method(err, "thread/turns/list"):
                return ProbeResult(
                    ok=False,
                    codex_cmd=codex_cmd,
                    method_supported=False,
                    error_code=int(err.get("code", -1)),
                    error_message=str(err.get("message") or "unsupported method"),
                    detail=probe.stderr_text,
                )
            return ProbeResult(
                ok=True,
                codex_cmd=codex_cmd,
                method_supported=True,
                error_code=int(err.get("code", -1)),
                error_message=str(err.get("message") or ""),
                detail="method is present; request failed at runtime/params/state level",
            )

        return ProbeResult(
            ok=True,
            codex_cmd=codex_cmd,
            method_supported=True,
            detail="thread/turns/list returned a result payload",
        )
    finally:
        probe.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test codex app-server JSON-RPC method support for Session V2 cutover.",
    )
    parser.add_argument(
        "--codex-cmd",
        default=None,
        help="Path or command for codex binary. Defaults to PLANNINGTREE_CODEX_CMD then PATH lookup.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=12.0,
        help="Per-request timeout in seconds (default: 12).",
    )
    args = parser.parse_args()

    codex_cmd = _resolve_codex_cmd(args.codex_cmd)
    if not codex_cmd:
        print("SMOKE=FAIL")
        print("reason=unable_to_resolve_codex_cmd")
        print("hint=set_PLANNINGTREE_CODEX_CMD_or_pass_--codex-cmd")
        return 2

    try:
        result = run_smoke(codex_cmd, timeout_sec=float(args.timeout_sec))
    except Exception as exc:
        print("SMOKE=FAIL")
        print(f"codex_cmd={codex_cmd}")
        print(f"reason=probe_exception")
        print(f"error={exc}")
        return 2

    if result.ok and result.method_supported:
        print("SMOKE=PASS")
        print(f"codex_cmd={result.codex_cmd}")
        print("method.thread_turns_list=supported")
        if result.error_message:
            print(f"runtime_error_code={result.error_code}")
            print(f"runtime_error_message={result.error_message}")
        if result.detail:
            print(f"detail={result.detail}")
        return 0

    print("SMOKE=FAIL")
    print(f"codex_cmd={result.codex_cmd}")
    print("method.thread_turns_list=unsupported")
    if result.error_code is not None:
        print(f"rpc_error_code={result.error_code}")
    if result.error_message:
        print(f"rpc_error_message={result.error_message}")
    if result.detail:
        print("stderr_tail_start")
        print(result.detail)
        print("stderr_tail_end")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
