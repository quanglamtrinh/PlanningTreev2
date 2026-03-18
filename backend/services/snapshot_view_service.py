from __future__ import annotations

import copy
from typing import Any

from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY
from backend.services.node_task_fields import enrich_nodes_with_task_fields
from backend.storage.node_store import NodeStore

_CANONICAL_SPLIT_MODES = frozenset(CANONICAL_SPLIT_MODE_REGISTRY.keys())
_CANONICAL_OUTPUT_FAMILIES = frozenset({"flat_subtasks_v1"})


class SnapshotViewService:
    """Converts internal snapshots into public API payloads."""

    def __init__(self, node_store: NodeStore | None = None) -> None:
        self._node_store = node_store

    def to_public_snapshot(
        self,
        project_id: str,
        snapshot: dict[str, Any],
        thread_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        public_snapshot = copy.deepcopy(snapshot)
        tree_state = public_snapshot.get("tree_state", {})
        if not isinstance(tree_state, dict):
            return public_snapshot
        node_index = tree_state.pop("node_index", {})
        if isinstance(node_index, dict):
            registry = list(node_index.values())
        else:
            registry = tree_state.get("node_registry", [])
            if not isinstance(registry, list):
                return public_snapshot
        tree_state["node_registry"] = registry
        if self._node_store is not None:
            node_by_id = {
                str(node.get("node_id")): node
                for node in registry
                if isinstance(node, dict) and isinstance(node.get("node_id"), str)
            }
            enrich_nodes_with_task_fields(self._node_store, project_id, node_by_id)
            for node_id, node in node_by_id.items():
                try:
                    state = self._node_store.load_state(project_id, node_id)
                except Exception:
                    continue
                phase = str(state.get("phase") or "").strip()
                if phase:
                    node["phase"] = phase
        root_node_id = str(tree_state.get("root_node_id") or "")

        thread_state = thread_state or {}
        for raw_node in registry:
            if not isinstance(raw_node, dict):
                continue
            node_id = str(raw_node.get("node_id", ""))
            node_thread_state = thread_state.get(node_id, {}) if isinstance(thread_state, dict) else {}
            planning_state = (
                node_thread_state.get("planning", {}) if isinstance(node_thread_state, dict) else {}
            )
            execution_state = (
                node_thread_state.get("execution", {}) if isinstance(node_thread_state, dict) else {}
            )
            ask_state = (
                node_thread_state.get("ask", {}) if isinstance(node_thread_state, dict) else {}
            )

            raw_node["node_kind"] = self._node_kind(raw_node, root_node_id)
            raw_node["phase"] = str(raw_node.get("phase") or "planning")
            if raw_node.get("planning_mode") not in _CANONICAL_SPLIT_MODES:
                raw_node["planning_mode"] = None
            split_metadata = raw_node.get("split_metadata")
            if isinstance(split_metadata, dict):
                if split_metadata.get("mode") not in _CANONICAL_SPLIT_MODES:
                    split_metadata.pop("mode", None)
                if split_metadata.get("output_family") not in _CANONICAL_OUTPUT_FAMILIES:
                    split_metadata.pop("output_family", None)
            planning_thread_id = raw_node.pop("planning_thread_id", None)
            execution_thread_id = raw_node.pop("execution_thread_id", None)
            raw_node.pop("planning_thread_forked_from_node", None)
            raw_node.pop("planning_thread_bootstrapped_at", None)

            resolved_planning_thread_id = planning_thread_id
            resolved_execution_thread_id = execution_thread_id
            if resolved_planning_thread_id is None and isinstance(planning_state, dict):
                resolved_planning_thread_id = planning_state.get("thread_id")
            if resolved_execution_thread_id is None and isinstance(execution_state, dict):
                resolved_execution_thread_id = execution_state.get("thread_id")

            raw_node["has_planning_thread"] = isinstance(resolved_planning_thread_id, str) and bool(
                resolved_planning_thread_id.strip()
            )
            raw_node["has_execution_thread"] = isinstance(resolved_execution_thread_id, str) and bool(
                resolved_execution_thread_id.strip()
            )
            raw_node["planning_thread_status"] = (
                planning_state.get("status") if isinstance(planning_state, dict) else None
            )
            raw_node["execution_thread_status"] = (
                execution_state.get("status") if isinstance(execution_state, dict) else None
            )
            resolved_ask_thread_id = ask_state.get("thread_id") if isinstance(ask_state, dict) else None
            raw_node["has_ask_thread"] = isinstance(resolved_ask_thread_id, str) and bool(
                resolved_ask_thread_id.strip()
            )
            raw_node["ask_thread_status"] = (
                ask_state.get("status") if isinstance(ask_state, dict) else None
            )
            raw_node["is_superseded"] = raw_node.get("node_kind") == "superseded"

        return public_snapshot

    def _node_kind(self, node: dict[str, Any], root_node_id: str) -> str:
        existing = str(node.get("node_kind") or "").strip()
        if existing in {"root", "original", "superseded"}:
            return existing
        node_id = str(node.get("node_id") or "")
        if node_id and node_id == root_node_id:
            return "root"
        if bool(node.get("is_superseded")):
            return "superseded"
        return "original"
