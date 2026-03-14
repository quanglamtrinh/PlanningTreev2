from __future__ import annotations

import logging
import threading
from typing import Any

from backend.ai.codex_client import CodexAppClient
from backend.ai.spec_prompt_builder import (
    build_spec_generation_prompt,
    build_spec_retry_feedback,
    normalize_spec_generation_payload,
    parse_spec_generation_response,
    spec_generation_issues,
)
from backend.errors.app_errors import NodeNotFound, SpecGenerationInvalidResponse, SpecGenerationNotAllowed
from backend.services.agent_operation_service import (
    AgentOperationHandle,
    AgentOperationService,
    clear_last_agent_failure,
    set_last_agent_failure,
)
from backend.services.node_service import NodeService
from backend.services.node_task_fields import load_task_prompt_fields
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)

_GENERATION_RETRY_LIMIT = 1
_SPEC_GENERATION_TIMEOUT_SEC = 300
_GENERATION_STATUSES = {"idle", "generating", "failed"}


class SpecGenerationService:
    def __init__(
        self,
        storage: Storage,
        client: CodexAppClient,
        node_service: NodeService,
        agent_operation_service: AgentOperationService | None = None,
        timeout_sec: int = _SPEC_GENERATION_TIMEOUT_SEC,
    ) -> None:
        self._storage = storage
        self._client = client
        self._node_service = node_service
        self._agent_operation_service = agent_operation_service
        self._timeout_sec = max(10, int(timeout_sec))

    def generate_spec(
        self,
        project_id: str,
        node_id: str,
        *,
        reserve_state: bool = True,
    ) -> dict[str, Any]:
        return self._generate_spec(project_id, node_id, reserve_state=reserve_state)

    def start_generation(self, project_id: str, node_id: str) -> dict[str, Any]:
        self._node_service.reconcile_stale_generations(project_id, node_id)
        if self._agent_operation_service is None:
            return self.generate_spec(project_id, node_id)
        try:
            handle = self._agent_operation_service.start_operation(project_id, node_id, "generate_spec")
        except RuntimeError as exc:
            raise SpecGenerationNotAllowed(str(exc)) from exc
        try:
            with self._storage.project_lock(project_id):
                snapshot, node = self._load_node(project_id, node_id)
                state = self._storage.node_store.load_state(project_id, node_id)
                self._assert_generation_allowed(project_id, node_id, node, state)
                state["spec_generation_status"] = "generating"
                state["spec_generation_started_at"] = iso_now()
                clear_last_agent_failure(state)
                self._storage.node_store.save_state(project_id, node_id, state)
                reserved_state = dict(state)
            self._agent_operation_service.publish_started(
                handle,
                stage="preparing",
                message="Preparing agent draft refresh.",
            )
            threading.Thread(
                target=self._run_background_generation,
                kwargs={
                    "project_id": project_id,
                    "node_id": node_id,
                    "handle": handle,
                },
                daemon=True,
            ).start()
            return {"status": "accepted", "operation": "generate_spec", "state": reserved_state}
        except Exception:
            self._agent_operation_service.finish_operation(handle)
            raise

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
                        state["spec_generation_status"] = "failed"
                        state["spec_generation_started_at"] = ""
                        set_last_agent_failure(
                            state,
                            operation="generate_spec",
                            message="Spec generation was interrupted before completion.",
                        )
                        self._storage.node_store.save_state(project_id, node_id, state)
                        recovered_nodes += 1
                if recovered_nodes:
                    logger.info(
                        "Recovered interrupted spec generation state for project %s (nodes=%s)",
                        project_id,
                        recovered_nodes,
                    )
            except Exception:
                logger.exception("Failed to reconcile interrupted spec generation for project %s", project_id)

    def _run_generation(
        self,
        context: dict[str, Any],
        workspace_root: str | None,
    ) -> dict[str, Any]:
        retry_feedback: str | None = None
        thread_id: str | None = None
        last_issues: list[str] = ["No JSON object found in the model response."]

        for _attempt in range(_GENERATION_RETRY_LIMIT + 1):
            response = self._client.send_prompt_streaming(
                build_spec_generation_prompt(context, retry_feedback),
                thread_id=thread_id,
                timeout_sec=self._timeout_sec,
                cwd=workspace_root,
                writable_roots=[],
            )
            raw_output = response.get("stdout")
            thread_id = response.get("thread_id") if isinstance(response.get("thread_id"), str) else thread_id
            payload = parse_spec_generation_response(str(raw_output or ""))
            issues = spec_generation_issues(payload)
            if not issues and payload is not None:
                return normalize_spec_generation_payload(payload)
            last_issues = issues
            retry_feedback = build_spec_retry_feedback(issues)

        raise SpecGenerationInvalidResponse(last_issues)

    def _generate_spec(
        self,
        project_id: str,
        node_id: str,
        *,
        reserve_state: bool,
    ) -> dict[str, Any]:
        prepared = self._prepare_generation(project_id, node_id, reserve_state=reserve_state)
        try:
            generated_spec = self._run_generation(prepared["context"], prepared["workspace_root"])
            spec = self._node_service.update_spec(project_id, node_id, generated_spec)
        except Exception as exc:
            self._mark_generation_failed(project_id, node_id, error_message=str(exc))
            raise

        with self._storage.project_lock(project_id):
            final_state = self._storage.node_store.load_state(project_id, node_id)
            final_state["spec_generation_status"] = "idle"
            final_state["spec_generation_started_at"] = ""
            clear_last_agent_failure(final_state)
            self._storage.node_store.save_state(project_id, node_id, final_state)
            return {
                "spec": spec,
                "state": final_state,
            }

    def _run_background_generation(
        self,
        *,
        project_id: str,
        node_id: str,
        handle: AgentOperationHandle,
    ) -> None:
        try:
            self._agent_operation_service.publish_progress(
                handle,
                stage="drafting_spec",
                message="Drafting Spec.",
            )
            self._generate_spec(project_id, node_id, reserve_state=False)
            self._agent_operation_service.publish_completed(
                handle,
                stage="completed",
                message="Spec is ready to review.",
            )
        except Exception as exc:
            logger.exception("Background spec generation failed for node %s", node_id)
            self._agent_operation_service.publish_failed(
                handle,
                stage="failed",
                message=str(exc),
            )
        finally:
            self._agent_operation_service.finish_operation(handle)

    def _prepare_generation(
        self,
        project_id: str,
        node_id: str,
        *,
        reserve_state: bool,
    ) -> dict[str, Any]:
        self._node_service.reconcile_stale_generations(project_id, node_id)
        with self._storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            self._assert_generation_allowed(
                project_id,
                node_id,
                node,
                state,
                allow_reserved=not reserve_state,
            )
            context = self._build_generation_context(project_id, snapshot, node)
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if reserve_state:
                state["spec_generation_status"] = "generating"
                state["spec_generation_started_at"] = iso_now()
                clear_last_agent_failure(state)
                self._storage.node_store.save_state(project_id, node_id, state)
            return {"context": context, "workspace_root": workspace_root}

    def _mark_generation_failed(self, project_id: str, node_id: str, *, error_message: str) -> None:
        with self._storage.project_lock(project_id):
            failed_state = self._storage.node_store.load_state(project_id, node_id)
            failed_state["spec_generation_status"] = "failed"
            failed_state["spec_generation_started_at"] = ""
            set_last_agent_failure(
                failed_state,
                operation="generate_spec",
                message=error_message,
            )
            self._storage.node_store.save_state(project_id, node_id, failed_state)

    def _build_generation_context(
        self,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
    ) -> dict[str, Any]:
        node_by_id = self._snapshot_node_index(snapshot)
        task = self._storage.node_store.load_task(project_id, node["node_id"])
        brief = self._storage.node_store.load_brief(project_id, node["node_id"])
        existing_spec = self._storage.node_store.load_spec(project_id, node["node_id"])
        return {
            "project_root_goal": str(snapshot.get("project", {}).get("root_goal") or ""),
            "node_id": str(node.get("node_id") or ""),
            "hierarchical_number": str(node.get("hierarchical_number") or ""),
            "phase": self._current_phase(node, self._storage.node_store.load_state(project_id, node["node_id"])),
            "parent_chain": self._build_parent_chain(project_id, node, node_by_id),
            "task": task,
            "brief": brief,
            "existing_spec": existing_spec,
        }

    def _build_parent_chain(
        self,
        project_id: str,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        chain: list[dict[str, str]] = []
        parent_id = node.get("parent_id")
        visited: set[str] = set()
        while isinstance(parent_id, str) and parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = node_by_id.get(parent_id)
            if parent is None:
                break
            task_fields = load_task_prompt_fields(self._storage.node_store, project_id, parent_id)
            chain.append(
                {
                    "node_id": parent_id,
                    "hierarchical_number": str(parent.get("hierarchical_number") or ""),
                    "title": task_fields["title"],
                    "purpose": task_fields["description"],
                }
            )
            parent_id = parent.get("parent_id")
        chain.reverse()
        return chain

    def _assert_generation_allowed(
        self,
        project_id: str,
        node_id: str,
        node: dict[str, Any],
        state: dict[str, Any],
        *,
        allow_reserved: bool = False,
    ) -> None:
        if self._is_superseded(node) or node.get("status") == "done":
            raise SpecGenerationNotAllowed("Cannot generate a spec for a non-mutable node.")

        current_phase = self._current_phase(node, state)
        if current_phase not in {"spec_review", "ready_for_execution", "blocked_on_spec_question"}:
            raise SpecGenerationNotAllowed(
                f"Cannot generate spec in phase '{current_phase}'. Node must be in 'spec_review', 'blocked_on_spec_question', or 'ready_for_execution'."
            )

        if str(state.get("brief_generation_status") or "").strip().lower() != "ready":
            raise SpecGenerationNotAllowed("Brief must exist before a Spec can be generated.")

        planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
        if planning_state.get("status") == "active":
            raise SpecGenerationNotAllowed("Cannot generate spec while planning is active for this node.")

        if self._normalize_generation_status(state) == "generating" and not allow_reserved:
            raise SpecGenerationNotAllowed("Spec generation is already active for this node.")

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

    def _current_phase(self, node: dict[str, Any], state: dict[str, Any]) -> str:
        phase = str(state.get("phase") or "").strip()
        if phase:
            return phase
        return str(node.get("phase") or "planning")

    def _is_superseded(self, node: dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))

    def _normalize_generation_status(self, state: dict[str, Any]) -> str:
        value = str(state.get("spec_generation_status") or "").strip().lower()
        if value in _GENERATION_STATUSES:
            return value
        return "idle"

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_workspace_root")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None
