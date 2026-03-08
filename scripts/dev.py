#!/usr/bin/env python3
"""
Development server launcher.
Starts backend (uvicorn) and frontend (vite) for local development.

Usage:
    python scripts/dev.py

Requirements:
    - Python 3.9+ in PATH
    - Node.js + npm in PATH
    - OPENAI_API_KEY set in environment (for split operations)
"""

import subprocess
import sys
import os
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
BACKEND_DIR = ROOT
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = ROOT / ".venv"


def find_python() -> str:
    for cmd in ["python", "python3"]:
        try:
            result = subprocess.run(
                [cmd, "--version"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
    print("ERROR: Python not found in PATH.", file=sys.stderr)
    sys.exit(1)


def get_venv_python(base_python: str) -> str:
    if sys.platform == "win32":
        venv_python = VENV_DIR / "Scripts" / "python.exe"
        venv_pip = VENV_DIR / "Scripts" / "pip.exe"
    else:
        venv_python = VENV_DIR / "bin" / "python"
        venv_pip = VENV_DIR / "bin" / "pip"

    if not VENV_DIR.exists():
        print("Creating virtual environment...")
        subprocess.run([base_python, "-m", "venv", str(VENV_DIR)], check=True)

    req_file = BACKEND_DIR / "backend" / "requirements-dev.txt"
    if req_file.exists():
        print("Installing backend dependencies...")
        subprocess.run(
            [str(venv_pip), "install", "-r", str(req_file), "-q"],
            check=True,
        )

    return str(venv_python)


def ensure_frontend_deps() -> None:
    if not (FRONTEND_DIR / "node_modules").exists():
        print("Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=str(FRONTEND_DIR), check=True)


def main() -> None:
    base_python = find_python()
    python = get_venv_python(base_python)
    ensure_frontend_deps()

    procs: list[subprocess.Popen] = []

    try:
        print("\nStarting backend  →  http://localhost:8000")
        backend = subprocess.Popen(
            [
                python, "-m", "uvicorn",
                "backend.main:app",
                "--reload",
                "--port", "8000",
                "--log-level", "info",
            ],
            cwd=str(ROOT),
        )
        procs.append(backend)

        time.sleep(1)  # let uvicorn bind before vite starts

        print("Starting frontend →  http://localhost:5173")
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(FRONTEND_DIR),
        )
        procs.append(frontend)

        print("\nBoth servers running. Press Ctrl+C to stop.\n")

        for proc in procs:
            proc.wait()

    except KeyboardInterrupt:
        print("\nShutting down...")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
