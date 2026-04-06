"""Shared workspace SHA computation.

SHA always means workspace/subtree state — not artifact fingerprint.
Placeholder until real git integration replaces with commit SHAs.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from backend.services import planningtree_workspace

_EXCLUDED_DIR_NAMES = {
    planningtree_workspace.PLANNINGTREE_DIR,
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}


def compute_workspace_sha(workspace_root: Path) -> str:
    """Compute a deterministic SHA-256 of the workspace directory tree.

    Excludes metadata/dependency/cache directories that are not source-of-truth
    for PlanningTree execution state.
    Format: ``sha256:<hex-digest>``.
    """
    digest = hashlib.sha256()
    if not workspace_root.exists():
        return "sha256:" + digest.hexdigest()

    entries: list[Path] = []
    for root, dirnames, filenames in os.walk(workspace_root, topdown=True):
        root_path = Path(root)
        rel_parts = root_path.relative_to(workspace_root).parts
        if rel_parts and rel_parts[0] in _EXCLUDED_DIR_NAMES:
            dirnames[:] = []
            continue

        # Prune heavy/external directories before descending for performance.
        dirnames[:] = [name for name in dirnames if name not in _EXCLUDED_DIR_NAMES]

        for dirname in dirnames:
            entries.append(root_path / dirname)
        for filename in filenames:
            entries.append(root_path / filename)

    entries.sort(key=lambda item: item.relative_to(workspace_root).as_posix())

    for path in entries:
        rel = path.relative_to(workspace_root).as_posix()
        if path.is_dir():
            digest.update(f"D {rel}\n".encode("utf-8"))
            continue
        if path.is_symlink():
            digest.update(f"S {rel}\n".encode("utf-8"))
            digest.update(str(path.readlink()).encode("utf-8", errors="replace"))
            continue
        if path.is_file():
            digest.update(f"F {rel}\n".encode("utf-8"))
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
