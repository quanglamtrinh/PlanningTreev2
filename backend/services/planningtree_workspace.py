from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

from backend.storage.file_utils import ensure_dir

logger = logging.getLogger(__name__)

PLANNINGTREE_DIR = ".planningtree"
ROOT_SEGMENT = "root"
NODE_MARKER_NAME = ".planningtree-node-id"

_MAX_SEGMENT_LEN = 200

# Windows reserved device names (case-insensitive).
_RESERVED_WIN_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
}


def bootstrap_if_absent(project_workspace: Path) -> None:
    """Create `.planningtree/root` only when `.planningtree` does not yet exist."""
    try:
        pt = project_workspace / PLANNINGTREE_DIR
        if pt.exists():
            return
        ensure_dir(pt / ROOT_SEGMENT)
    except OSError as exc:
        logger.warning("planningtree bootstrap failed for %s: %s", project_workspace, exc)


def is_sync_base_ready(project_workspace: Path) -> bool:
    return (project_workspace / PLANNINGTREE_DIR / ROOT_SEGMENT).is_dir()


def clear_root_children(project_workspace: Path) -> None:
    """Remove all entries directly under `.planningtree/root` (best-effort)."""
    root = project_workspace / PLANNINGTREE_DIR / ROOT_SEGMENT
    if not root.is_dir():
        return
    try:
        for child in root.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("planningtree clear failed for %s: %s", child, exc)
    except OSError as exc:
        logger.warning("planningtree clear_root_children failed for %s: %s", root, exc)


def segment_for_node(node: Dict[str, Any]) -> str:
    hnum = str(node.get("hierarchical_number") or "1").strip() or "1"
    title = str(node.get("title") or "").strip() or "untitled"
    return _sanitize_dir_segment(f"{hnum} {title}")


def ensure_node_path(project_workspace: Path, snapshot: Dict[str, Any], node_id: str) -> None:
    """Create nested directories for the node under `.planningtree/root` (best-effort)."""
    if not is_sync_base_ready(project_workspace):
        return
    try:
        chain = _node_chain_to_root(snapshot, node_id)
        if not chain:
            return
        base = project_workspace / PLANNINGTREE_DIR / ROOT_SEGMENT
        current = base
        for node in chain:
            seg = _resolve_unique_segment(current, node)
            current = current / seg
            ensure_dir(current)
            _write_node_marker(current, str(node.get("node_id") or ""))
    except OSError as exc:
        logger.warning(
            "planningtree ensure_node_path failed for project %s node %s: %s",
            project_workspace,
            node_id,
            exc,
        )


def ensure_node_paths(project_workspace: Path, snapshot: Dict[str, Any], node_ids: List[str]) -> None:
    for nid in node_ids:
        ensure_node_path(project_workspace, snapshot, nid)


def _node_chain_to_root(snapshot: Dict[str, Any], node_id: str) -> List[Dict[str, Any]]:
    tree_state = snapshot.get("tree_state", {})
    node_index = tree_state.get("node_index", {})
    if not isinstance(node_index, dict):
        return []

    chain: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = node_index.get(node_id) if isinstance(node_index.get(node_id), dict) else None
    if current is None:
        return []

    while current is not None:
        chain.append(current)
        parent_id = current.get("parent_id")
        if not isinstance(parent_id, str) or not parent_id:
            break
        nxt = node_index.get(parent_id)
        current = nxt if isinstance(nxt, dict) else None

    chain.reverse()
    return chain


def _sanitize_dir_segment(raw: str) -> str:
    # Replace forbidden characters with space (Windows + sane cross-platform).
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned, flags=re.UNICODE).strip()
    cleaned = cleaned.rstrip(" .")
    if not cleaned:
        cleaned = "untitled"
    if len(cleaned) > _MAX_SEGMENT_LEN:
        cleaned = cleaned[:_MAX_SEGMENT_LEN].rstrip(" .")
    base = cleaned.split(" ", 1)[0] if cleaned else ""
    if base.casefold() in _RESERVED_WIN_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned or "untitled"


def _read_node_marker(dir_path: Path) -> str | None:
    marker = dir_path / NODE_MARKER_NAME
    if not marker.is_file():
        return None
    try:
        return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _write_node_marker(dir_path: Path, node_id: str) -> None:
    if not node_id:
        return
    try:
        (dir_path / NODE_MARKER_NAME).write_text(node_id, encoding="utf-8", newline="\n")
    except OSError as exc:
        logger.warning("planningtree could not write node marker in %s: %s", dir_path, exc)


def _resolve_unique_segment(parent: Path, node: Dict[str, Any]) -> str:
    primary = segment_for_node(node)
    nid = str(node.get("node_id") or "")
    target = parent / primary

    if not target.exists():
        return primary

    existing = _read_node_marker(target)
    if existing == nid:
        return primary
    if existing is None:
        # Pre-marker dirs or external content: keep using `primary` (idempotent).
        return primary

    return _pick_free_segment(parent, primary, nid)


def _pick_free_segment(parent: Path, primary: str, node_id: str) -> str:
    suffix = node_id[:8] if len(node_id) >= 8 else node_id or "x"
    base = f"{primary}_{suffix}"
    candidate = base
    n = 2
    while (parent / candidate).exists():
        candidate = f"{base}_{n}"
        n += 1
    return candidate
