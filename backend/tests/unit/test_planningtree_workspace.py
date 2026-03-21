from __future__ import annotations

from pathlib import Path

from backend.services import planningtree_workspace


def test_bootstrap_creates_dot_planningtree_root(tmp_path: Path) -> None:
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    root = tmp_path / ".planningtree" / "root"
    assert root.is_dir()


def test_bootstrap_skips_when_dot_planningtree_exists(tmp_path: Path) -> None:
    marker = tmp_path / ".planningtree"
    marker.mkdir(parents=True)
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    assert not (tmp_path / ".planningtree" / "root").exists()


def test_ensure_node_path_creates_nested_folders(tmp_path: Path) -> None:
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    root_id = "rootid01"
    child_id = "childid01"
    snapshot = {
        "project": {"project_workspace_root": str(tmp_path)},
        "tree_state": {
            "root_node_id": root_id,
            "node_index": {
                root_id: {
                    "node_id": root_id,
                    "parent_id": None,
                    "child_ids": [child_id],
                    "title": "Chair website",
                    "hierarchical_number": "1",
                },
                child_id: {
                    "node_id": child_id,
                    "parent_id": root_id,
                    "child_ids": [],
                    "title": "Set site scope",
                    "hierarchical_number": "1.1",
                },
            },
        },
    }
    planningtree_workspace.ensure_node_path(tmp_path, snapshot, child_id)
    base = tmp_path / ".planningtree" / "root"
    assert (base / "1 Chair website" / "1.1 Set site scope").is_dir()


def test_marker_mismatch_uses_disambiguated_segment(tmp_path: Path) -> None:
    """If `primary` exists but is owned by another node id, pick a suffixed segment."""
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    parent_id = "p"
    a_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    snapshot = {
        "project": {"project_workspace_root": str(tmp_path)},
        "tree_state": {
            "root_node_id": parent_id,
            "node_index": {
                parent_id: {
                    "node_id": parent_id,
                    "parent_id": None,
                    "child_ids": [a_id],
                    "title": "Root",
                    "hierarchical_number": "1",
                },
                a_id: {
                    "node_id": a_id,
                    "parent_id": parent_id,
                    "child_ids": [],
                    "title": "Task",
                    "hierarchical_number": "1.1",
                },
            },
        },
    }
    wrong = tmp_path / ".planningtree" / "root" / "1 Root" / "1.1 Task"
    wrong.mkdir(parents=True)
    (wrong / planningtree_workspace.NODE_MARKER_NAME).write_text("othernodeothernode", encoding="utf-8")

    planningtree_workspace.ensure_node_path(tmp_path, snapshot, a_id)
    alt = tmp_path / ".planningtree" / "root" / "1 Root" / "1.1 Task_aaaaaaaa"
    assert alt.is_dir()
    assert (alt / planningtree_workspace.NODE_MARKER_NAME).read_text(encoding="utf-8").strip() == a_id


def test_clear_root_children_removes_entries(tmp_path: Path) -> None:
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    root = tmp_path / ".planningtree" / "root"
    (root / "keepme").mkdir(parents=True)
    (root / "nested" / "x").mkdir(parents=True)
    planningtree_workspace.clear_root_children(tmp_path)
    assert list(root.iterdir()) == []
