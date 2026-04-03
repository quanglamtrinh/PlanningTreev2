#!/usr/bin/env python3
"""
Development server launcher.
Starts backend (uvicorn) and frontend (vite) for local development.

Usage:
    python scripts/dev.py
"""

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

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config.app_config import get_codex_cmd

BACKEND_DIR = ROOT
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = ROOT / ".venv"
FRONTEND_PORT = 5174
BACKEND_PORT = 8000
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


def run_quiet(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def find_python() -> str:
    candidates = [sys.executable, "python", "python3"]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            result = run_quiet([candidate, "--version"])
            if result.returncode == 0:
                return candidate
        except FileNotFoundError:
            continue
    print("ERROR: Python not found in PATH.", file=sys.stderr)
    sys.exit(1)


def venv_python_path() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_activate_path() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "Activate.ps1"
    return VENV_DIR / "bin" / "activate"


def backend_runtime_ready(python_cmd: str) -> bool:
    try:
        result = run_quiet([python_cmd, "-c", "import fastapi, uvicorn"])
    except FileNotFoundError:
        return False
    return result.returncode == 0


def create_or_repair_venv(base_python: str) -> str:
    print("Creating or repairing virtual environment...")
    subprocess.run([base_python, "-m", "venv", "--clear", str(VENV_DIR)], check=True)

    venv_python = venv_python_path()
    activate_script = venv_activate_path()
    if not venv_python.exists() or not activate_script.exists():
        print("ERROR: virtual environment was not created correctly.", file=sys.stderr)
        sys.exit(1)

    return str(venv_python)


def install_backend_dependencies(python_cmd: str) -> None:
    req_file = BACKEND_DIR / "backend" / "requirements-dev.txt"
    if not req_file.exists():
        return
    if backend_runtime_ready(python_cmd):
        return

    print("Installing backend dependencies...")
    subprocess.run([python_cmd, "-m", "ensurepip", "--upgrade"], check=True)
    subprocess.run([python_cmd, "-m", "pip", "install", "-r", str(req_file)], check=True)


def resolve_backend_python(base_python: str) -> str:
    venv_python = venv_python_path()
    activate_script = venv_activate_path()
    venv_missing = not VENV_DIR.exists()
    venv_broken = VENV_DIR.exists() and (not venv_python.exists() or not activate_script.exists())

    if not venv_missing and not venv_broken:
        python_cmd = str(venv_python)
        install_backend_dependencies(python_cmd)
        if backend_runtime_ready(python_cmd):
            return python_cmd

    if venv_broken:
        print("Detected a broken virtual environment. Falling back to system Python.")
    elif venv_missing:
        print("Virtual environment not found. Falling back to system Python.")

    if backend_runtime_ready(base_python):
        print("Using system Python for backend.")
        return base_python

    python_cmd = create_or_repair_venv(base_python)
    install_backend_dependencies(python_cmd)
    if backend_runtime_ready(python_cmd):
        return python_cmd

    print("ERROR: could not prepare a Python environment with FastAPI and uvicorn.", file=sys.stderr)
    sys.exit(1)


def ensure_frontend_deps() -> None:
    if not (FRONTEND_DIR / "node_modules").exists():
        print("Installing frontend dependencies...")
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        subprocess.run([npm_cmd, "install"], cwd=str(FRONTEND_DIR), check=True)


def port_is_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def ensure_port_available(port: int, name: str, env_var: str) -> None:
    if port_is_available(port):
        return
    print(
        f"ERROR: {name} port {port} is already in use. "
        f"Stop the existing process or set {env_var} to a different port.",
        file=sys.stderr,
    )
    sys.exit(1)


def backend_reload_enabled() -> bool:
    raw = os.environ.get("PLANNINGTREE_BACKEND_RELOAD")
    if raw is None:
        return os.name != "nt"
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def read_dev_flag(name: str, default: str = "1") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        return default
    return value


def create_windows_job() -> int | None:
    if os.name != "nt":
        return None
    job = _CREATE_JOB_OBJECT(None, None)
    if not job:
        error = ctypes.get_last_error()
        print(
            f"WARNING: could not create Windows job object (winerror={error}).",
            file=sys.stderr,
        )
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

    error = ctypes.get_last_error()
    print(
        f"WARNING: could not enable kill-on-close for child processes (winerror={error}).",
        file=sys.stderr,
    )
    return None


def assign_to_windows_job(job: int | None, proc: subprocess.Popen[bytes]) -> None:
    if os.name != "nt" or job is None:
        return
    result = _ASSIGN_PROCESS_TO_JOB_OBJECT(ctypes.c_void_p(job), ctypes.c_void_p(proc._handle))
    if result:
        return
    error = ctypes.get_last_error()
    print(
        f"WARNING: could not assign pid {proc.pid} to Windows job object (winerror={error}).",
        file=sys.stderr,
    )


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


def main() -> None:
    base_python = find_python()
    python = resolve_backend_python(base_python)
    ensure_frontend_deps()

    procs: list[subprocess.Popen[bytes]] = []
    windows_job = create_windows_job()
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    backend_port = int(os.environ.get("PLANNINGTREE_PORT", str(BACKEND_PORT)))
    frontend_port = int(os.environ.get("PLANNINGTREE_FRONTEND_PORT", str(FRONTEND_PORT)))
    reload_backend = backend_reload_enabled()
    backend_v3_enabled = read_dev_flag("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_BACKEND")
    backend_v3_frontend_shared = read_dev_flag("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND")
    backend_v3_frontend_execution = read_dev_flag("PLANNINGTREE_EXECUTION_UIUX_V3_FRONTEND")
    backend_v3_frontend_audit = read_dev_flag("PLANNINGTREE_AUDIT_UIUX_V3_FRONTEND")
    frontend_v3_shared = read_dev_flag(
        "VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND",
        default=backend_v3_frontend_shared,
    )
    frontend_v3_execution = read_dev_flag(
        "VITE_EXECUTION_UIUX_V3_FRONTEND",
        default=backend_v3_frontend_execution,
    )
    frontend_v3_audit = read_dev_flag(
        "VITE_AUDIT_UIUX_V3_FRONTEND",
        default=backend_v3_frontend_audit,
    )

    ensure_port_available(backend_port, "backend", "PLANNINGTREE_PORT")
    ensure_port_available(frontend_port, "frontend", "PLANNINGTREE_FRONTEND_PORT")

    try:
        print(f"\nStarting backend -> http://127.0.0.1:{backend_port}")
        codex_cmd = get_codex_cmd()
        if codex_cmd:
            print(f"Using Codex binary: {codex_cmd}")
        print(
            "V3 flags (backend/frontend shared/execution/audit): "
            f"{backend_v3_enabled}/{frontend_v3_shared}/{frontend_v3_execution}/{frontend_v3_audit}"
        )
        backend_command = [
            python,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--port",
            str(backend_port),
            "--log-level",
            "info",
        ]
        if reload_backend:
            backend_command.insert(4, "--reload")
        else:
            print("Backend auto-reload disabled for this platform. Set PLANNINGTREE_BACKEND_RELOAD=1 to override.")

        backend = spawn_process(
            backend_command,
            cwd=ROOT,
            env={
                **os.environ,
                "PLANNINGTREE_PORT": str(backend_port),
                "PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_BACKEND": backend_v3_enabled,
                "PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND": backend_v3_frontend_shared,
                "PLANNINGTREE_EXECUTION_UIUX_V3_FRONTEND": backend_v3_frontend_execution,
                "PLANNINGTREE_AUDIT_UIUX_V3_FRONTEND": backend_v3_frontend_audit,
                **({"PLANNINGTREE_CODEX_CMD": codex_cmd} if codex_cmd else {}),
            },
            windows_job=windows_job,
        )
        procs.append(backend)

        if not backend_ready(backend_port):
            print(
                f"ERROR: backend did not become ready on port {backend_port}.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Starting frontend -> http://127.0.0.1:{frontend_port}")
        frontend = spawn_process(
            [
                npm_cmd,
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(frontend_port),
                "--strictPort",
            ],
            cwd=FRONTEND_DIR,
            env={
                **os.environ,
                "PLANNINGTREE_BACKEND_PORT": str(backend_port),
                "PLANNINGTREE_PORT": str(backend_port),
                "VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND": frontend_v3_shared,
                "VITE_EXECUTION_UIUX_V3_FRONTEND": frontend_v3_execution,
                "VITE_AUDIT_UIUX_V3_FRONTEND": frontend_v3_audit,
            },
            windows_job=windows_job,
        )
        procs.append(frontend)

        print("\nBoth servers running. Press Ctrl+C to stop.\n")

        while True:
            for proc in procs:
                if proc.poll() is not None:
                    return
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for proc in procs:
            terminate_process_tree(proc)
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                terminate_process_tree(proc, force=True)
        for proc in procs:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass


if __name__ == "__main__":
    main()
