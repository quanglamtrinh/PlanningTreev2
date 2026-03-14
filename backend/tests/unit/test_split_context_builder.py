from __future__ import annotations

from backend.ai.split_context_builder import build_split_context


def build_node(
    node_id: str,
    *,
    parent_id: str | None,
    title: str,
    description: str,
    depth: int,
    display_order: int,
    status: str = "draft",
    child_ids: list[str] | None = None,
    is_superseded: bool = False,
) -> dict:
    return {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": child_ids or [],
        "title": title,
        "description": description,
        "status": status,
        "planning_mode": None,
        "depth": depth,
        "display_order": display_order,
        "hierarchical_number": "1",
        "split_metadata": None,
        "chat_session_id": None,
        "is_superseded": is_superseded,
        "created_at": "2026-03-08T00:00:00Z",
    }


def test_build_split_context_truncates_parent_chain_and_formats_title_only_nodes() -> None:
    root = build_node("root", parent_id=None, title="Root", description="", depth=0, display_order=0, child_ids=["n1"])
    n1 = build_node("n1", parent_id="root", title="One", description="desc1", depth=1, display_order=0, child_ids=["n2"])
    n2 = build_node("n2", parent_id="n1", title="Two", description="", depth=2, display_order=0, child_ids=["n3"])
    n3 = build_node("n3", parent_id="n2", title="Three", description="desc3", depth=3, display_order=0, child_ids=["n4"])
    n4 = build_node("n4", parent_id="n3", title="Four", description="desc4", depth=4, display_order=0, child_ids=["n5"])
    n5 = build_node("n5", parent_id="n4", title="Five", description="desc5", depth=5, display_order=0, child_ids=["n6"])
    n6 = build_node("n6", parent_id="n5", title="Six", description="desc6", depth=6, display_order=0, child_ids=["target"])
    target = build_node("target", parent_id="n6", title="Target", description="", depth=7, display_order=0)
    snapshot = {
        "project": {"root_goal": "Ship phase 5"},
        "tree_state": {"node_registry": [root, n1, n2, n3, n4, n5, n6, target]},
    }
    node_by_id = {node["node_id"]: node for node in snapshot["tree_state"]["node_registry"]}

    context = build_split_context(snapshot, target, node_by_id)

    assert context["root_prompt"] == "Ship phase 5"
    assert context["current_node_prompt"] == "Target"
    assert context["tree_depth"] == 7
    assert context["parent_chain_depth"] == 7
    assert context["parent_chain_truncated"] is True
    assert context["parent_chain_prompts"] == [
        "Root",
        "Two",
        "Three: desc3",
        "Four: desc4",
        "Five: desc5",
        "Six: desc6",
    ]


def test_build_split_context_includes_recent_done_siblings_only() -> None:
    parent = build_node(
        "parent",
        parent_id=None,
        title="Parent",
        description="",
        depth=0,
        display_order=0,
        child_ids=["done-1", "done-2", "active", "superseded", "done-3", "done-4", "done-5", "done-6"],
    )
    nodes = [
        parent,
        build_node("done-1", parent_id="parent", title="Done 1", description="a", depth=1, display_order=0, status="done"),
        build_node("done-2", parent_id="parent", title="Done 2", description="b", depth=1, display_order=1, status="done"),
        build_node("active", parent_id="parent", title="Active", description="c", depth=1, display_order=2, status="ready"),
        build_node(
            "superseded",
            parent_id="parent",
            title="Old",
            description="d",
            depth=1,
            display_order=3,
            status="done",
            is_superseded=True,
        ),
        build_node("done-3", parent_id="parent", title="Done 3", description="e", depth=1, display_order=4, status="done"),
        build_node("done-4", parent_id="parent", title="Done 4", description="f", depth=1, display_order=5, status="done"),
        build_node("done-5", parent_id="parent", title="Done 5", description="g", depth=1, display_order=6, status="done"),
        build_node("done-6", parent_id="parent", title="Done 6", description="h", depth=1, display_order=7, status="done"),
    ]
    snapshot = {"project": {"root_goal": "Goal"}, "tree_state": {"node_registry": nodes}}
    node_by_id = {node["node_id"]: node for node in nodes}

    context = build_split_context(snapshot, node_by_id["active"], node_by_id)

    assert context["existing_children_count"] == 0
    assert context["prior_node_summaries_compact"] == [
        {"node_id": "done-2", "title": "Done 2", "description": "b"},
        {"node_id": "done-3", "title": "Done 3", "description": "e"},
        {"node_id": "done-4", "title": "Done 4", "description": "f"},
        {"node_id": "done-5", "title": "Done 5", "description": "g"},
        {"node_id": "done-6", "title": "Done 6", "description": "h"},
    ]
