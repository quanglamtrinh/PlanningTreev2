from __future__ import annotations

from typing import Any


def derive_review_sibling_manifest(
    snapshot: dict[str, Any],
    parent_node: dict[str, Any],
    review_node: dict[str, Any],
    review_state: dict[str, Any],
) -> list[dict[str, Any]]:
    del review_node

    tree_state = snapshot.get("tree_state", {})
    node_index = tree_state.get("node_index", {}) if isinstance(tree_state, dict) else {}
    if not isinstance(node_index, dict):
        return []

    materialized_by_index: dict[int, dict[str, Any]] = {}
    raw_siblings_by_index: dict[int, dict[str, Any]] = {}
    checkpoint_by_source_node_id: dict[str, dict[str, Any]] = {}

    raw_child_ids = parent_node.get("child_ids", [])
    if isinstance(raw_child_ids, list):
        materialized_children: list[dict[str, Any]] = []
        for child_id in raw_child_ids:
            child = node_index.get(child_id)
            if not isinstance(child, dict):
                continue
            if str(child.get("node_kind") or "").strip() == "review":
                continue
            materialized_children.append(child)
        materialized_children.sort(
            key=lambda child: int(child.get("display_order", 0) or 0)
        )
        for child in materialized_children:
            try:
                index = int(child.get("display_order", 0) or 0) + 1
            except (TypeError, ValueError):
                continue
            if index < 1:
                continue
            materialized_by_index[index] = child

    raw_pending = review_state.get("pending_siblings", [])
    if isinstance(raw_pending, list):
        for sibling in raw_pending:
            if not isinstance(sibling, dict):
                continue
            index = sibling.get("index")
            if not isinstance(index, int) or index < 1:
                continue
            raw_siblings_by_index[index] = sibling

    raw_checkpoints = review_state.get("checkpoints", [])
    if isinstance(raw_checkpoints, list):
        for checkpoint in raw_checkpoints:
            if not isinstance(checkpoint, dict):
                continue
            source_node_id = checkpoint.get("source_node_id")
            if not isinstance(source_node_id, str) or not source_node_id.strip():
                continue
            checkpoint_by_source_node_id[source_node_id.strip()] = checkpoint

    ordered_indices = sorted(set(materialized_by_index) | set(raw_siblings_by_index))
    manifest: list[dict[str, Any]] = []
    for index in ordered_indices:
        child = materialized_by_index.get(index)
        raw_sibling = raw_siblings_by_index.get(index)

        materialized_node_id: str | None = None
        if isinstance(child, dict):
            raw_child_node_id = child.get("node_id")
            if isinstance(raw_child_node_id, str) and raw_child_node_id.strip():
                materialized_node_id = raw_child_node_id.strip()
        if materialized_node_id is None and isinstance(raw_sibling, dict):
            raw_materialized_node_id = raw_sibling.get("materialized_node_id")
            if isinstance(raw_materialized_node_id, str) and raw_materialized_node_id.strip():
                materialized_node_id = raw_materialized_node_id.strip()

        title = ""
        if isinstance(raw_sibling, dict):
            raw_title = raw_sibling.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                title = raw_title.strip()
        if not title and isinstance(child, dict):
            raw_child_title = child.get("title")
            if isinstance(raw_child_title, str) and raw_child_title.strip():
                title = raw_child_title.strip()

        objective: str | None = None
        if isinstance(raw_sibling, dict):
            raw_objective = raw_sibling.get("objective")
            if isinstance(raw_objective, str) and raw_objective.strip():
                objective = raw_objective.strip()
        if objective is None and isinstance(child, dict):
            raw_child_description = child.get("description")
            if isinstance(raw_child_description, str) and raw_child_description.strip():
                objective = raw_child_description.strip()

        checkpoint = (
            checkpoint_by_source_node_id.get(materialized_node_id)
            if materialized_node_id is not None
            else None
        )
        checkpoint_label: str | None = None
        if isinstance(checkpoint, dict):
            raw_label = checkpoint.get("label")
            if isinstance(raw_label, str) and raw_label.strip():
                checkpoint_label = raw_label.strip()

        status: str
        if materialized_node_id is None:
            status = "pending"
        elif checkpoint_label is not None:
            status = "completed"
        else:
            status = "active"

        manifest.append(
            {
                "index": index,
                "title": title,
                "objective": objective,
                "materialized_node_id": materialized_node_id,
                "status": status,
                "checkpoint_label": checkpoint_label,
            }
        )

    return manifest


def to_public_pending_siblings(review_state: dict[str, Any]) -> list[dict[str, Any]]:
    pending = review_state.get("pending_siblings", [])
    public_pending: list[dict[str, Any]] = []
    if isinstance(pending, list):
        for sibling in pending:
            if not isinstance(sibling, dict):
                continue
            public_pending.append(
                {
                    "index": sibling.get("index", 0),
                    "title": sibling.get("title", ""),
                    "materialized_node_id": sibling.get("materialized_node_id"),
                }
            )
    return public_pending
