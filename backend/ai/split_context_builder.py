from __future__ import annotations

from typing import Any


def build_split_context(
    snapshot: dict[str, Any],
    node: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    parent_chain = _build_parent_chain_prompts(node, node_by_id)
    parent_chain_depth = len(parent_chain)
    parent_chain_truncated = parent_chain_depth > 6
    if parent_chain_truncated:
        parent_chain = [parent_chain[0], *parent_chain[-5:]]

    return {
        "root_prompt": str(snapshot.get("project", {}).get("root_goal", "")),
        "current_node_prompt": _format_node_prompt(node),
        "node_id": str(node.get("node_id", "")),
        "tree_depth": int(node.get("depth", 0) or 0),
        "parent_chain_prompts": parent_chain,
        "parent_chain_depth": parent_chain_depth,
        "parent_chain_truncated": parent_chain_truncated,
        "prior_node_summaries_compact": _build_prior_node_summaries_compact(node, node_by_id),
        "existing_children_count": len(_active_child_ids(node, node_by_id)),
    }


def _is_superseded(node: dict[str, Any]) -> bool:
    return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))


def _build_parent_chain_prompts(
    node: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    prompts: list[str] = []
    parent_id = node.get("parent_id")
    visited: set[str] = set()
    while isinstance(parent_id, str) and parent_id and parent_id not in visited:
        visited.add(parent_id)
        parent = node_by_id.get(parent_id)
        if parent is None:
            break
        prompts.append(_format_node_prompt(parent))
        parent_id = parent.get("parent_id")
    prompts.reverse()
    return prompts


def _build_prior_node_summaries_compact(
    node: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    parent_id = node.get("parent_id")
    if not isinstance(parent_id, str) or not parent_id:
        return []

    parent = node_by_id.get(parent_id)
    if parent is None:
        return []

    sibling_summaries: list[dict[str, Any]] = []
    for sibling_id in parent.get("child_ids", []):
        if not isinstance(sibling_id, str) or sibling_id == node.get("node_id"):
            continue
        sibling = node_by_id.get(sibling_id)
        if sibling is None or _is_superseded(sibling) or sibling.get("status") != "done":
            continue
        sibling_summaries.append(
            {
                "node_id": str(sibling.get("node_id", "")),
                "title": str(sibling.get("title", "")),
                "description": str(sibling.get("description", "")),
                "display_order": int(sibling.get("display_order", 0) or 0),
            }
        )

    sibling_summaries.sort(key=lambda item: item["display_order"])
    sibling_summaries = sibling_summaries[-5:]
    return [
        {
            "node_id": item["node_id"],
            "title": item["title"],
            "description": item["description"],
        }
        for item in sibling_summaries
    ]


def _format_node_prompt(node: dict[str, Any]) -> str:
    title = str(node.get("title", "")).strip()
    description = str(node.get("description", "")).strip()
    if title and description:
        return f"{title}: {description}"
    return title or description


def _active_child_ids(
    node: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    active_children: list[str] = []
    for child_id in node.get("child_ids", []):
        if not isinstance(child_id, str):
            continue
        child = node_by_id.get(child_id)
        if child is None or _is_superseded(child):
            continue
        active_children.append(child_id)
    return active_children
