from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterator, List

from backend.storage.file_utils import ensure_dir

logger = logging.getLogger(__name__)

PLANNINGTREE_DIR = ".planningtree"
ROOT_SEGMENT = "root"
NODE_MARKER_NAME = ".node-id"
FRAME_FILE_NAME = "frame.md"
SPEC_FILE_NAME = "spec.md"
_LEGACY_NODE_MARKER_NAMES = (".planningtree-node-id",)
_ALL_NODE_MARKER_NAMES = (NODE_MARKER_NAME, *_LEGACY_NODE_MARKER_NAMES)

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
            _ensure_node_files(current)
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


def resolve_node_dir(project_workspace: Path, snapshot: Dict[str, Any], node_id: str) -> Path | None:
    sync_snapshot_tree(project_workspace, snapshot)
    root = project_workspace / PLANNINGTREE_DIR / ROOT_SEGMENT
    if not root.is_dir():
        return None
    node_dir = _scan_node_dirs(root).get(node_id)
    if node_dir is None:
        return None
    _ensure_node_files(node_dir)
    return node_dir


def sync_snapshot_tree(project_workspace: Path, snapshot: Dict[str, Any]) -> None:
    """Synchronize the folder projection under `.planningtree/root` from `tree.json`."""
    try:
        root = ensure_dir(project_workspace / PLANNINGTREE_DIR / ROOT_SEGMENT)
        node_index = _node_index(snapshot)
        if not node_index:
            return

        existing_dirs = _scan_node_dirs(root)
        kept_paths: dict[str, Path] = {}
        for root_id in _root_node_ids(snapshot, node_index):
            _sync_node_subtree(root, root_id, node_index, existing_dirs, kept_paths)

        _remove_stale_node_dirs(root, kept_paths)
        _prune_empty_dirs(root)
    except OSError as exc:
        logger.warning("planningtree sync failed for %s: %s", project_workspace, exc)


def _node_chain_to_root(snapshot: Dict[str, Any], node_id: str) -> List[Dict[str, Any]]:
    node_index = _node_index(snapshot)
    if not node_index:
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


def _node_index(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    tree_state = snapshot.get("tree_state", {})
    if not isinstance(tree_state, dict):
        return {}
    node_index = tree_state.get("node_index", {})
    if not isinstance(node_index, dict):
        return {}
    return {node_id: node for node_id, node in node_index.items() if isinstance(node, dict)}


def _root_node_ids(snapshot: Dict[str, Any], node_index: Dict[str, Dict[str, Any]]) -> List[str]:
    tree_state = snapshot.get("tree_state", {})
    if not isinstance(tree_state, dict):
        return []
    primary_root_id = str(tree_state.get("root_node_id") or "").strip()
    ordered_ids: List[str] = []
    if primary_root_id and primary_root_id in node_index:
        ordered_ids.append(primary_root_id)

    secondary_roots = sorted(
        (
            node_id
            for node_id, node in node_index.items()
            if node_id != primary_root_id and not _has_valid_parent(node, node_index)
        ),
        key=lambda node_id: (
            int(node_index[node_id].get("depth", 0) or 0),
            int(node_index[node_id].get("display_order", 0) or 0),
            str(node_index[node_id].get("title") or ""),
        ),
    )
    ordered_ids.extend(secondary_roots)
    return ordered_ids


def _has_valid_parent(node: Dict[str, Any], node_index: Dict[str, Dict[str, Any]]) -> bool:
    parent_id = node.get("parent_id")
    return isinstance(parent_id, str) and parent_id in node_index


def _scan_node_dirs(root: Path) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for marker in _iter_node_markers(root):
        if not marker.is_file():
            continue
        node_id = _read_node_marker(marker.parent)
        if not node_id or node_id in mapping:
            continue
        mapping[node_id] = marker.parent
    return mapping


def _sync_node_subtree(
    parent_dir: Path,
    node_id: str,
    node_index: Dict[str, Dict[str, Any]],
    existing_dirs: Dict[str, Path],
    kept_paths: Dict[str, Path],
) -> None:
    if node_id in kept_paths:
        return
    node = node_index.get(node_id)
    if node is None:
        return

    current_dir = existing_dirs.get(node_id)
    segment = _resolve_unique_segment(parent_dir, node)
    desired_dir = parent_dir / segment

    if current_dir is None:
        ensure_dir(desired_dir)
        existing_dirs[node_id] = desired_dir
    else:
        if current_dir != desired_dir:
            ensure_dir(parent_dir)
            if desired_dir.exists():
                desired_dir = parent_dir / _pick_free_segment(parent_dir, segment_for_node(node), node_id)
            current_dir.rename(desired_dir)
            _rebase_existing_dirs(existing_dirs, current_dir, desired_dir)
        else:
            ensure_dir(desired_dir)

    _write_node_marker(desired_dir, node_id)
    _ensure_node_files(desired_dir)
    kept_paths[node_id] = desired_dir

    for child_id in _ordered_child_ids(node, node_index):
        _sync_node_subtree(desired_dir, child_id, node_index, existing_dirs, kept_paths)


def _ordered_child_ids(node: Dict[str, Any], node_index: Dict[str, Dict[str, Any]]) -> List[str]:
    child_ids = node.get("child_ids")
    if not isinstance(child_ids, list):
        return []
    ordered: List[str] = []
    for child_id in child_ids:
        if isinstance(child_id, str) and child_id in node_index:
            ordered.append(child_id)
    return ordered


def _rebase_existing_dirs(existing_dirs: Dict[str, Path], old_base: Path, new_base: Path) -> None:
    for node_id, current_path in list(existing_dirs.items()):
        if current_path == old_base:
            existing_dirs[node_id] = new_base
            continue
        try:
            relative = current_path.relative_to(old_base)
        except ValueError:
            continue
        existing_dirs[node_id] = new_base / relative


def _remove_stale_node_dirs(root: Path, kept_paths: Dict[str, Path]) -> None:
    keep_set = {path.resolve() for path in kept_paths.values()}
    stale_dirs: List[Path] = []
    for marker in _iter_node_markers(root):
        if not marker.is_file():
            continue
        node_dir = marker.parent.resolve()
        if node_dir not in keep_set:
            stale_dirs.append(node_dir)

    for stale_dir in sorted(stale_dirs, key=lambda path: len(path.parts), reverse=True):
        if not stale_dir.exists():
            continue
        shutil.rmtree(stale_dir, ignore_errors=True)


def _prune_empty_dirs(root: Path) -> None:
    for current in sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        if current == root:
            continue
        try:
            next(current.iterdir())
        except StopIteration:
            current.rmdir()
        except OSError:
            continue


FRAME_META_FILE_NAME = "frame.meta.json"
SPEC_META_FILE_NAME = "spec.meta.json"


def _ensure_node_files(node_dir: Path) -> None:
    for filename in (FRAME_FILE_NAME, SPEC_FILE_NAME):
        path = node_dir / filename
        if not path.exists():
            path.touch()
    meta_path = node_dir / FRAME_META_FILE_NAME
    if not meta_path.exists():
        import json
        meta_path.write_text(
            json.dumps({"revision": 0, "confirmed_revision": 0, "confirmed_at": None}, indent=2) + "\n",
            encoding="utf-8",
        )
    spec_meta_path = node_dir / SPEC_META_FILE_NAME
    if not spec_meta_path.exists():
        import json
        spec_meta_path.write_text(
            json.dumps({"source_frame_revision": 0, "confirmed_at": None}, indent=2) + "\n",
            encoding="utf-8",
        )


def _iter_node_markers(root: Path) -> Iterator[Path]:
    seen_paths: set[Path] = set()
    for marker_name in _ALL_NODE_MARKER_NAMES:
        for marker in root.rglob(marker_name):
            resolved = marker.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            yield marker


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
    for marker_name in _ALL_NODE_MARKER_NAMES:
        marker = dir_path / marker_name
        if not marker.is_file():
            continue
        try:
            return marker.read_text(encoding="utf-8").strip() or None
        except OSError:
            continue
    return None


def _write_node_marker(dir_path: Path, node_id: str) -> None:
    if not node_id:
        return
    try:
        (dir_path / NODE_MARKER_NAME).write_text(node_id, encoding="utf-8", newline="\n")
        for legacy_name in _LEGACY_NODE_MARKER_NAMES:
            (dir_path / legacy_name).unlink(missing_ok=True)
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
