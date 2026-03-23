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
        "project": {"project_path": str(tmp_path)},
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
    child_dir = base / "1 Chair website" / "1.1 Set site scope"
    assert child_dir.is_dir()
    assert (child_dir / planningtree_workspace.NODE_MARKER_NAME).read_text(encoding="utf-8").strip() == child_id
    assert (child_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (child_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == ""
    assert (child_dir / planningtree_workspace.FRAME_META_FILE_NAME).is_file()
    assert (child_dir / planningtree_workspace.SPEC_META_FILE_NAME).is_file()


def test_marker_mismatch_uses_disambiguated_segment(tmp_path: Path) -> None:
    """If `primary` exists but is owned by another node id, pick a suffixed segment."""
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    parent_id = "p"
    a_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    snapshot = {
        "project": {"project_path": str(tmp_path)},
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


def test_sync_snapshot_tree_renames_node_folder_and_preserves_files(tmp_path: Path) -> None:
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    root_id = "rootid01"
    child_id = "childid01"
    snapshot = {
        "project": {"project_path": str(tmp_path)},
        "tree_state": {
            "root_node_id": root_id,
            "node_index": {
                root_id: {
                    "node_id": root_id,
                    "parent_id": None,
                    "child_ids": [child_id],
                    "title": "Chair website",
                    "hierarchical_number": "1",
                    "display_order": 0,
                },
                child_id: {
                    "node_id": child_id,
                    "parent_id": root_id,
                    "child_ids": [],
                    "title": "Old title",
                    "hierarchical_number": "1.1",
                    "display_order": 0,
                },
            },
        },
    }

    planningtree_workspace.sync_snapshot_tree(tmp_path, snapshot)
    old_dir = tmp_path / ".planningtree" / "root" / "1 Chair website" / "1.1 Old title"
    (old_dir / planningtree_workspace.FRAME_FILE_NAME).write_text("frame body", encoding="utf-8")
    (old_dir / planningtree_workspace.SPEC_FILE_NAME).write_text("spec body", encoding="utf-8")

    snapshot["tree_state"]["node_index"][child_id]["title"] = "New title"
    planningtree_workspace.sync_snapshot_tree(tmp_path, snapshot)

    new_dir = tmp_path / ".planningtree" / "root" / "1 Chair website" / "1.1 New title"
    assert new_dir.is_dir()
    assert not old_dir.exists()
    assert (new_dir / planningtree_workspace.NODE_MARKER_NAME).read_text(encoding="utf-8").strip() == child_id
    assert (new_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == "frame body"
    assert (new_dir / planningtree_workspace.SPEC_FILE_NAME).read_text(encoding="utf-8") == "spec body"


def test_sync_snapshot_tree_truncates_segments_to_keep_node_files_within_path_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    planningtree_workspace.bootstrap_if_absent(tmp_path)
    monkeypatch.setattr(planningtree_workspace, "_is_windows_path_limited", lambda: True)

    root_id = "rootid01"
    branch_id = "branchid01"
    leaf_id = "leafid01"
    snapshot = {
        "project": {"project_path": str(tmp_path)},
        "tree_state": {
            "root_node_id": root_id,
            "node_index": {
                root_id: {
                    "node_id": root_id,
                    "parent_id": None,
                    "child_ids": [branch_id],
                    "title": "workspace title with several words",
                    "hierarchical_number": "1",
                    "display_order": 0,
                },
                branch_id: {
                    "node_id": branch_id,
                    "parent_id": root_id,
                    "child_ids": [leaf_id],
                    "title": "branch title with enough length to trigger truncation",
                    "hierarchical_number": "1.1",
                    "display_order": 0,
                },
                leaf_id: {
                    "node_id": leaf_id,
                    "parent_id": branch_id,
                    "child_ids": [],
                    "title": "leaf title with enough length to trigger truncation again",
                    "hierarchical_number": "1.1.1",
                    "display_order": 0,
                },
            },
        },
    }

    node_index = snapshot["tree_state"]["node_index"]
    raw_leaf_path = (
        tmp_path
        / ".planningtree"
        / "root"
        / planningtree_workspace.segment_for_node(node_index[root_id])
        / planningtree_workspace.segment_for_node(node_index[branch_id])
        / planningtree_workspace.segment_for_node(node_index[leaf_id])
        / "clarify_gen.json.tmp"
    )
    minimal_leaf_path = (
        tmp_path / ".planningtree" / "root" / "x" / "x" / "x" / "clarify_gen.json.tmp"
    )
    windows_limit = planningtree_workspace._WINDOWS_MAX_PATH
    monkeypatch.setattr(
        planningtree_workspace,
        "_WINDOWS_MAX_PATH",
        min(windows_limit, max(len(str(minimal_leaf_path)), len(str(raw_leaf_path)) - 20)),
    )

    planningtree_workspace.sync_snapshot_tree(tmp_path, snapshot)
    node_dir = planningtree_workspace.resolve_node_dir(tmp_path, snapshot, leaf_id)

    assert node_dir is not None
    assert (node_dir / planningtree_workspace.FRAME_META_FILE_NAME).is_file()
    assert len(str(node_dir / "clarify_gen.json.tmp")) <= planningtree_workspace._WINDOWS_MAX_PATH
    assert node_dir.name != planningtree_workspace.segment_for_node(
        snapshot["tree_state"]["node_index"][leaf_id]
    )
