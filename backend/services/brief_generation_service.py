from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any

from backend.ai.brief_prompt_builder import (
    brief_generation_issues,
    build_brief_generation_prompt,
    build_brief_retry_feedback,
    normalize_brief_generation_payload,
    parse_brief_generation_response,
)
from backend.ai.codex_client import CodexAppClient
from backend.errors.app_errors import (
    BriefGenerationInvalidResponse,
    BriefGenerationNotAllowed,
    NodeNotFound,
)
from backend.services.agent_operation_service import (
    AgentOperationHandle,
    AgentOperationService,
    clear_last_agent_failure,
    set_last_agent_failure,
)
from backend.services.node_task_fields import load_task_prompt_fields
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)

_GENERATION_RETRY_LIMIT = 1
_BRIEF_GENERATION_TIMEOUT_SEC = 120
_GENERATION_STATUSES = {"missing", "generating", "failed", "ready"}


class BriefGenerationService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        client: CodexAppClient,
        agent_operation_service: AgentOperationService | None = None,
        timeout_sec: int = _BRIEF_GENERATION_TIMEOUT_SEC,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._client = client
        self._agent_operation_service = agent_operation_service
        self._spec_generation_service = None
        self._timeout_sec = max(10, int(timeout_sec))

    def configure_spec_generation_service(self, spec_generation_service) -> None:
        self._spec_generation_service = spec_generation_service

    def generate_brief(
        self,
        project_id: str,
        node_id: str,
        *,
        predecessor_node_id: str | None = None,
        reserve_state: bool = True,
    ) -> dict[str, Any]:
        prepared = self._prepare_generation(
            project_id,
            node_id,
            predecessor_node_id=predecessor_node_id,
            reserve_state=reserve_state,
        )
        try:
            brief = self._run_generation(
                prepared["context"],
                prepared["workspace_root"],
            )
        except Exception as exc:
            self._mark_generation_failed(
                project_id,
                node_id,
                error_message=str(exc),
            )
            raise
        return self._commit_generated_brief(
            project_id,
            node_id,
            brief=brief,
            predecessor_node_id=predecessor_node_id,
            source_hash=prepared["source_hash"],
            source_refs=prepared["context"].get("source_refs", []),
        )

    def reconcile_interrupted_generations(self) -> None:
        for project_id in self._storage.project_store.list_project_ids():
            try:
                recovered_nodes = 0
                with self._storage.project_lock(project_id):
                    snapshot = self._storage.project_store.load_snapshot(project_id)
                    node_index = snapshot.get("tree_state", {}).get("node_index", {})
                    if not isinstance(node_index, dict):
                        continue
                    for node_id in node_index:
                        if not isinstance(node_id, str) or not node_id:
                            continue
                        state = self._storage.node_store.load_state(project_id, node_id)
                        if self._normalize_generation_status(state) != "generating":
                            continue
                        state["brief_generation_status"] = "failed"
                        state["brief_generation_started_at"] = ""
                        state["phase"] = "awaiting_brief"
                        set_last_agent_failure(
                            state,
                            operation="brief_pipeline",
                            message="Brief generation was interrupted before completion.",
                        )
                        self._storage.node_store.save_state(project_id, node_id, state)
                        node = node_index.get(node_id)
                        if isinstance(node, dict):
                            node["phase"] = "awaiting_brief"
                        recovered_nodes += 1
                    if recovered_nodes:
                        self._persist_snapshot(project_id, snapshot)
                if recovered_nodes:
                    logger.info(
                        "Recovered interrupted brief generation state for project %s (nodes=%s)",
                        project_id,
                        recovered_nodes,
                    )
            except Exception:
                logger.exception("Failed to reconcile interrupted brief generation for project %s", project_id)

    def _run_generation(self, context: dict[str, Any], workspace_root: str | None) -> dict[str, Any]:
        retry_feedback: str | None = None
        thread_id: str | None = None
        last_issues: list[str] = ["No JSON object found in the model response."]

        for _attempt in range(_GENERATION_RETRY_LIMIT + 1):
            response = self._client.send_prompt_streaming(
                build_brief_generation_prompt(context, retry_feedback),
                thread_id=thread_id,
                timeout_sec=self._timeout_sec,
                cwd=workspace_root,
                writable_roots=[],
            )
            raw_output = response.get("stdout")
            thread_id = response.get("thread_id") if isinstance(response.get("thread_id"), str) else thread_id
            payload = parse_brief_generation_response(str(raw_output or ""))
            issues = brief_generation_issues(payload)
            if not issues and payload is not None:
                return normalize_brief_generation_payload(payload)
            last_issues = issues
            retry_feedback = build_brief_retry_feedback(issues)

        raise BriefGenerationInvalidResponse(last_issues)

    def _prepare_generation(
        self,
        project_id: str,
        node_id: str,
        *,
        predecessor_node_id: str | None,
        reserve_state: bool,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            if reserve_state:
                self._assert_generation_allowed(node, state)
            else:
                if self._normalize_generation_status(state) == "ready" or int(state.get("brief_version", 0) or 0) > 0:
                    raise BriefGenerationNotAllowed("Brief has already been generated for this node.")
            context = self._build_generation_context(
                project_id,
                snapshot,
                node,
                state,
                predecessor_node_id=predecessor_node_id,
            )
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            source_hash = hashlib.sha256(
                json.dumps(context, sort_keys=True, ensure_ascii=True).encode("utf-8")
            ).hexdigest()
            state["brief_generation_status"] = "generating"
            state["brief_generation_started_at"] = iso_now()
            clear_last_agent_failure(state)
            node["phase"] = "awaiting_brief"
            state["phase"] = "awaiting_brief"
            self._storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            return {
                "context": context,
                "workspace_root": workspace_root,
                "source_hash": source_hash,
            }

    def _commit_generated_brief(
        self,
        project_id: str,
        node_id: str,
        *,
        brief: dict[str, Any],
        predecessor_node_id: str | None,
        source_hash: str,
        source_refs: list[str],
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            self._storage.node_store.save_brief(project_id, node_id, brief)
            final_snapshot = self._storage.project_store.load_snapshot(project_id)
            final_node = self._snapshot_node_index(final_snapshot).get(node_id)
            final_state = self._storage.node_store.load_state(project_id, node_id)
            final_state["brief_generation_status"] = "ready"
            final_state["brief_generation_started_at"] = ""
            final_state["brief_version"] = max(1, int(final_state.get("brief_version", 0) or 0) + 1)
            final_state["brief_created_at"] = iso_now()
            final_state["brief_created_from_predecessor_node_id"] = predecessor_node_id or ""
            final_state["brief_generated_by"] = "agent"
            final_state["brief_source_hash"] = source_hash
            final_state["brief_source_refs"] = list(source_refs)
            final_state["brief_late_upstream_policy"] = "ignore"
            final_state["briefing_confirmed"] = True
            clear_last_agent_failure(final_state)
            final_state["phase"] = "spec_review"
            self._storage.node_store.save_state(project_id, node_id, final_state)
            if isinstance(final_node, dict):
                final_node["phase"] = "spec_review"
                self._persist_snapshot(project_id, final_snapshot)
            return {
                "brief": brief,
                "state": final_state,
            }

    def _mark_generation_failed(
        self,
        project_id: str,
        node_id: str,
        *,
        error_message: str,
    ) -> None:
        with self._storage.project_lock(project_id):
            failed_snapshot = self._storage.project_store.load_snapshot(project_id)
            failed_node = self._snapshot_node_index(failed_snapshot).get(node_id)
            failed_state = self._storage.node_store.load_state(project_id, node_id)
            failed_state["brief_generation_status"] = "failed"
            failed_state["brief_generation_started_at"] = ""
            failed_state["phase"] = "awaiting_brief"
            set_last_agent_failure(
                failed_state,
                operation="brief_pipeline",
                message=error_message,
            )
            self._storage.node_store.save_state(project_id, node_id, failed_state)
            if isinstance(failed_node, dict):
                failed_node["phase"] = "awaiting_brief"
                self._persist_snapshot(project_id, failed_snapshot)

    def _build_generation_context(
        self,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        state: dict[str, Any],
        *,
        predecessor_node_id: str | None,
    ) -> dict[str, Any]:
        node_by_id = self._snapshot_node_index(snapshot)
        task = self._storage.node_store.load_task(project_id, str(node.get("node_id") or ""))
        source_refs = [f"task:{node.get('node_id')}"]
        if predecessor_node_id:
            source_refs.append(f"predecessor:{predecessor_node_id}")

        return {
            "project_root_goal": str(snapshot.get("project", {}).get("root_goal") or ""),
            "project_name": str(snapshot.get("project", {}).get("name") or ""),
            "node_id": str(node.get("node_id") or ""),
            "hierarchical_number": str(node.get("hierarchical_number") or ""),
            "task": task,
            "predecessor": self._build_predecessor_summary(project_id, predecessor_node_id, node_by_id),
            "parent_chain": self._build_parent_chain(project_id, node, node_by_id, source_refs),
            "completed_siblings": self._build_completed_siblings(project_id, node, node_by_id, source_refs),
            "accepted_ask_packets": self._build_accepted_packet_context(project_id, node, source_refs),
            "runtime_state": {
                "phase": str(state.get("phase") or node.get("phase") or "planning"),
                "status": str(node.get("status") or ""),
                "completed_so_far": [],
                "current_blockers": [],
                "next_best_action": "Review and confirm the agent-recommended Spec draft.",
            },
            "source_refs": source_refs,
        }

    def _build_predecessor_summary(
        self,
        project_id: str,
        predecessor_node_id: str | None,
        node_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not predecessor_node_id:
            return None
        predecessor = node_by_id.get(predecessor_node_id)
        if predecessor is None:
            return None
        task_fields = load_task_prompt_fields(self._storage.node_store, project_id, predecessor_node_id)
        return {
            "node_id": predecessor_node_id,
            "hierarchical_number": str(predecessor.get("hierarchical_number") or ""),
            "title": task_fields["title"],
            "purpose": task_fields["description"],
            "status": str(predecessor.get("status") or ""),
        }

    def _build_parent_chain(
        self,
        project_id: str,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        source_refs: list[str],
    ) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        parent_id = node.get("parent_id")
        visited: set[str] = set()
        while isinstance(parent_id, str) and parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = node_by_id.get(parent_id)
            if parent is None:
                break
            task_fields = load_task_prompt_fields(self._storage.node_store, project_id, parent_id)
            parent_state = self._storage.node_store.load_state(project_id, parent_id)
            parent_spec = self._storage.node_store.load_spec(project_id, parent_id)
            source_refs.append(f"parent:{parent_id}")
            chain.append(
                {
                    "node_id": parent_id,
                    "hierarchical_number": str(parent.get("hierarchical_number") or ""),
                    "title": task_fields["title"],
                    "purpose": task_fields["description"],
                    "spec_confirmed": bool(parent_state.get("spec_confirmed")),
                    "constraints": parent_spec.get("constraints", ""),
                    "scope": parent_spec.get("scope", ""),
                }
            )
            parent_id = parent.get("parent_id")
        chain.reverse()
        return chain

    def _build_completed_siblings(
        self,
        project_id: str,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        source_refs: list[str],
    ) -> list[dict[str, Any]]:
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str) or not parent_id:
            return []
        parent = node_by_id.get(parent_id)
        if parent is None:
            return []
        siblings: list[dict[str, Any]] = []
        for sibling_id in parent.get("child_ids", []):
            if not isinstance(sibling_id, str) or sibling_id == node.get("node_id"):
                continue
            sibling = node_by_id.get(sibling_id)
            if sibling is None or sibling.get("status") != "done":
                continue
            task_fields = load_task_prompt_fields(self._storage.node_store, project_id, sibling_id)
            source_refs.append(f"sibling:{sibling_id}")
            siblings.append(
                {
                    "node_id": sibling_id,
                    "hierarchical_number": str(sibling.get("hierarchical_number") or ""),
                    "title": task_fields["title"],
                    "purpose": task_fields["description"],
                }
            )
        return siblings

    def _build_accepted_packet_context(
        self,
        project_id: str,
        node: dict[str, Any],
        source_refs: list[str],
    ) -> list[dict[str, Any]]:
        ask_state = self._storage.thread_store.get_ask_state(project_id, str(node.get("node_id") or ""))
        packets = ask_state.get("delta_context_packets", []) if isinstance(ask_state, dict) else []
        accepted: list[dict[str, Any]] = []
        for packet in packets:
            if not isinstance(packet, dict):
                continue
            if packet.get("status") != "merged":
                continue
            source_refs.append(f"packet:{packet.get('packet_id')}")
            accepted.append(
                {
                    "summary": str(packet.get("summary") or ""),
                    "context_text": str(packet.get("context_text") or ""),
                }
            )
        return accepted

    def _assert_generation_allowed(self, node: dict[str, Any], state: dict[str, Any]) -> None:
        if self._is_superseded(node) or node.get("status") == "done":
            raise BriefGenerationNotAllowed("Cannot generate a Brief for a non-mutable node.")
        if self._normalize_generation_status(state) == "generating":
            raise BriefGenerationNotAllowed("Brief generation is already active for this node.")
        if self._normalize_generation_status(state) == "ready" or int(state.get("brief_version", 0) or 0) > 0:
            raise BriefGenerationNotAllowed("Brief has already been generated for this node.")

    def _load_node(self, project_id: str, node_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        node_by_id = self._snapshot_node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        return snapshot, node

    def _snapshot_node_index(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        tree_state = snapshot.get("tree_state", {})
        if not isinstance(tree_state, dict):
            return {}
        node_index = tree_state.get("node_index")
        if not isinstance(node_index, dict):
            return {}
        return {
            node_id: node
            for node_id, node in node_index.items()
            if isinstance(node_id, str) and isinstance(node, dict)
        }

    def _is_superseded(self, node: dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))

    def _normalize_generation_status(self, state: dict[str, Any]) -> str:
        value = str(state.get("brief_generation_status") or "").strip().lower()
        if value in _GENERATION_STATUSES:
            return value
        return "missing"

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_workspace_root")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _persist_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        self._storage.project_store.save_snapshot(project_id, snapshot)
        return snapshot
