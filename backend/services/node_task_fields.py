from __future__ import annotations

import logging
from typing import Any, Iterable

from backend.storage.node_store import NodeStore

logger = logging.getLogger(__name__)


def load_task_prompt_fields(node_store: NodeStore, project_id: str, node_id: str) -> dict[str, str]:
    try:
        task = node_store.load_task(project_id, node_id)
    except Exception:
        logger.warning(
            "Failed to load task prompt fields for project %s node %s; using empty fallback.",
            project_id,
            node_id,
            exc_info=True,
        )
        return {"title": "", "description": ""}
    return {"title": str(task.get("title") or ""), "description": str(task.get("purpose") or "")}


def enrich_nodes_with_task_fields(
    node_store: NodeStore,
    project_id: str,
    node_by_id: dict[str, dict[str, Any]],
    node_ids: Iterable[str] | None = None,
) -> None:
    target_ids = node_by_id.keys() if node_ids is None else node_ids
    seen: set[str] = set()
    for raw_node_id in target_ids:
        if not isinstance(raw_node_id, str) or not raw_node_id or raw_node_id in seen:
            continue
        seen.add(raw_node_id)
        node = node_by_id.get(raw_node_id)
        if node is None:
            continue
        if "title" in node and "description" in node:
            continue
        fields = load_task_prompt_fields(node_store, project_id, raw_node_id)
        node.setdefault("title", fields["title"])
        node.setdefault("description", fields["description"])
