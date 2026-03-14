#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
FRONTEND_DIR = ROOT / "frontend"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
FRONTEND_PORT = 5174
BACKEND_PORT = 8000
PROCS: list[subprocess.Popen[bytes]] = []
WINDOWS_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

if os.name == "nt":
    import ctypes

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CREATE_JOB_OBJECT = _KERNEL32.CreateJobObjectW
    _CREATE_JOB_OBJECT.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    _CREATE_JOB_OBJECT.restype = ctypes.c_void_p
    _SET_INFORMATION_JOB_OBJECT = _KERNEL32.SetInformationJobObject
    _SET_INFORMATION_JOB_OBJECT.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    _SET_INFORMATION_JOB_OBJECT.restype = ctypes.c_int
    _ASSIGN_PROCESS_TO_JOB_OBJECT = _KERNEL32.AssignProcessToJobObject
    _ASSIGN_PROCESS_TO_JOB_OBJECT.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _ASSIGN_PROCESS_TO_JOB_OBJECT.restype = ctypes.c_int


def require_path(path: Path, message: str) -> Path:
    if not path.exists():
        print(message, file=sys.stderr)
        raise SystemExit(1)
    return path


def resolve_backend_python() -> str:
    candidates = [VENV_PYTHON, Path(sys.executable)]
    for candidate in candidates:
        if not candidate.exists():
            continue
        probe = subprocess.run(
            [str(candidate), "-c", "import fastapi, uvicorn"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return str(candidate)

    print(
        "Could not find a Python interpreter with fastapi and uvicorn installed for Playwright.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def port_is_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(preferred_port: int, host: str = "127.0.0.1") -> int:
    for offset in range(50):
        candidate = preferred_port + offset
        if port_is_available(candidate, host):
            return candidate
    print(
        f"Could not find a free backend port starting at {preferred_port}.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def backend_ready(port: int, timeout_sec: float = 20.0) -> bool:
    deadline = time.time() + timeout_sec
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.25)
    return False


def create_windows_job() -> int | None:
    if os.name != "nt":
        return None
    job = _CREATE_JOB_OBJECT(None, None)
    if not job:
        return None
    limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    result = _SET_INFORMATION_JOB_OBJECT(
        job,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    )
    if result:
        return int(job)
    return None


def assign_to_windows_job(job: int | None, proc: subprocess.Popen[bytes]) -> None:
    if os.name != "nt" or job is None:
        return
    _ASSIGN_PROCESS_TO_JOB_OBJECT(ctypes.c_void_p(job), ctypes.c_void_p(proc._handle))


def spawn_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    windows_job: int | None,
) -> subprocess.Popen[bytes]:
    popen_kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = WINDOWS_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, **popen_kwargs)
    assign_to_windows_job(windows_job, proc)
    return proc


def terminate_process_tree(proc: subprocess.Popen[bytes], *, force: bool = False) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        command = ["taskkill", "/PID", str(proc.pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(command, capture_output=True, text=True, check=False)
        return
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return


def shutdown(*_args: object) -> None:
    for proc in PROCS:
        terminate_process_tree(proc)
    for proc in PROCS:
        if proc.poll() is None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                terminate_process_tree(proc, force=True)
    raise SystemExit(0)


def main() -> None:
    python = resolve_backend_python()
    require_path(
        FRONTEND_DIR / "node_modules",
        "Missing frontend/node_modules for Playwright dev server. Run npm install in frontend first.",
    )

    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    preferred_backend_port = int(os.environ.get("PLANNINGTREE_PORT", str(BACKEND_PORT)))
    backend_port = find_available_port(preferred_backend_port)
    windows_job = create_windows_job()
    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        backend = spawn_process(
            [
                python,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--port",
                str(backend_port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env={
                **os.environ,
                "PLANNINGTREE_PORT": str(backend_port),
            },
            windows_job=windows_job,
        )
        PROCS.append(backend)

        if not backend_ready(backend_port):
            print(
                f"Backend did not become ready on port {backend_port}.",
                file=sys.stderr,
            )
            shutdown()

        frontend = spawn_process(
            [npm_cmd, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
            env={
                **os.environ,
                "PLANNINGTREE_BACKEND_PORT": str(backend_port),
                "PLANNINGTREE_PORT": str(backend_port),
            },
            windows_job=windows_job,
        )
        PROCS.append(frontend)

        while True:
            for proc in PROCS:
                if proc.poll() is not None:
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()
    finally:
        for proc in PROCS:
            if proc.poll() is None:
                terminate_process_tree(proc, force=True)


if __name__ == "__main__":
    main()
