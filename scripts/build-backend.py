#!/usr/bin/env python3
"""
Build the PyInstaller backend binary.

Bootstraps the venv (like dev.py), installs build deps, builds frontend,
then runs PyInstaller. Designed to work from a clean shell without
requiring manual venv activation.

Usage:
    python scripts/build-backend.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
FRONTEND_DIR = ROOT / "frontend"
SPEC_FILE = ROOT / "planningtree-server.spec"
DIST_DIR = ROOT / "build" / "dist"


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


def build_deps_ready(python_cmd: str) -> bool:
    try:
        result = run_quiet([python_cmd, "-c", "import fastapi, uvicorn, PyInstaller"])
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


def install_build_dependencies(python_cmd: str) -> None:
    req_file = ROOT / "backend" / "requirements-build.txt"
    if not req_file.exists():
        print(f"ERROR: {req_file} not found.", file=sys.stderr)
        sys.exit(1)

    print("Installing build dependencies...")
    subprocess.run([python_cmd, "-m", "ensurepip", "--upgrade"], check=True)
    subprocess.run(
        [python_cmd, "-m", "pip", "install", "-r", str(req_file)],
        check=True,
    )


def resolve_build_python(base_python: str) -> str:
    venv_python = venv_python_path()
    activate_script = venv_activate_path()
    venv_missing = not VENV_DIR.exists()
    venv_broken = VENV_DIR.exists() and (
        not venv_python.exists() or not activate_script.exists()
    )

    if not venv_missing and not venv_broken:
        python_cmd = str(venv_python)
        if build_deps_ready(python_cmd):
            return python_cmd
        install_build_dependencies(python_cmd)
        if build_deps_ready(python_cmd):
            return python_cmd

    if venv_broken:
        print("Detected a broken virtual environment. Recreating...")
    elif venv_missing:
        print("Virtual environment not found. Creating...")

    python_cmd = create_or_repair_venv(base_python)
    install_build_dependencies(python_cmd)
    if build_deps_ready(python_cmd):
        return python_cmd

    print("ERROR: could not prepare a Python environment with build deps.", file=sys.stderr)
    sys.exit(1)


def build_frontend() -> None:
    print("\n=== Building frontend ===")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"

    if not (FRONTEND_DIR / "node_modules").exists():
        print("Installing frontend dependencies...")
        subprocess.run([npm_cmd, "install"], cwd=str(FRONTEND_DIR), check=True)

    subprocess.run([npm_cmd, "run", "build"], cwd=str(FRONTEND_DIR), check=True)

    index_html = FRONTEND_DIR / "dist" / "index.html"
    if not index_html.exists():
        print("ERROR: frontend build did not produce dist/index.html", file=sys.stderr)
        sys.exit(1)

    print("Frontend build complete.")


def build_backend(python_cmd: str) -> None:
    print("\n=== Building backend (PyInstaller) ===")
    if not SPEC_FILE.exists():
        print(f"ERROR: {SPEC_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    subprocess.run(
        [python_cmd, "-m", "PyInstaller", str(SPEC_FILE), "--distpath", str(DIST_DIR), "-y"],
        cwd=str(ROOT),
        check=True,
    )

    binary_name = (
        "planningtree-server.exe" if sys.platform == "win32" else "planningtree-server"
    )
    binary_path = DIST_DIR / "planningtree-server" / binary_name
    if not binary_path.exists():
        print(f"ERROR: expected binary not found at {binary_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Backend build complete: {binary_path}")


def main() -> None:
    print("=== PlanningTree Build ===\n")

    base_python = find_python()
    python_cmd = resolve_build_python(base_python)
    print(f"Using Python: {python_cmd}\n")

    build_frontend()
    build_backend(python_cmd)

    print("\n=== Build complete ===")
    print(f"Backend binary: {DIST_DIR / 'planningtree-server'}")
    print("Next: npm run build:electron")


if __name__ == "__main__":
    main()
