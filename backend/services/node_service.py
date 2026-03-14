from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional, Set
from uuid import uuid4

from backend.errors.app_errors import (
    CompleteNotAllowed,
    ConfirmationNotAllowed,
    InvalidRequest,
    NodeCreateNotAllowed,
    NodeNotFound,
    NodeUpdateNotAllowed,
)
from backend.services.agent_operation_service import (
    AgentOperationHandle,
    AgentOperationService,
    clear_last_agent_failure,
    set_last_agent_failure,
)
from backend.services.snapshot_view_service import SnapshotViewService
from backend.services.thread_service import ThreadService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, load_json
from backend.storage.node_files import empty_brief, empty_spec
from backend.storage.storage import Storage

if TYPE_CHECKING:
    from backend.services.brief_generation_service import BriefGenerationService
    from backend.services.spec_generation_service import SpecGenerationService

logger = logging.getLogger(__name__)

_GENERATION_STALE_GRACE_SEC = 30


class NodeService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        thread_service: ThreadService | None = None,
        snapshot_view_service: SnapshotViewService | None = None,
        agent_operation_service: AgentOperationService | None = None,
    ) -> None:
        self.storage = storage
        self.tree_service = tree_service
        self._thread_service = thread_service
        self._snapshot_view_service = snapshot_view_service
        self._agent_operation_service = agent_operation_service
        self._brief_generation_service: BriefGenerationService | None = None
        self._spec_generation_service: SpecGenerationService | None = None

    def configure_artifact_services(
        self,
        *,
        brief_generation_service: BriefGenerationService | None = None,
        spec_generation_service: SpecGenerationService | None = None,
    ) -> None:
        self._brief_generation_service = brief_generation_service
        self._spec_generation_service = spec_generation_service

    def set_active_node(self, project_id: str, active_node_id: Optional[str]) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            node_by_id = self.tree_service.node_index(snapshot)
            if active_node_id is not None and active_node_id not in node_by_id:
                raise NodeNotFound(active_node_id)
            if snapshot["tree_state"].get("active_node_id") == active_node_id:
                return self._public_snapshot(project_id, snapshot)
            snapshot["tree_state"]["active_node_id"] = active_node_id
            snapshot = self._persist_snapshot(project_id, snapshot)
        return self._public_snapshot(project_id, snapshot)

    def create_child(self, project_id: str, parent_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            node_by_id = self.tree_service.node_index(snapshot)
            parent = node_by_id.get(parent_id)
            if parent is None:
                raise NodeNotFound(parent_id)
            if self._is_superseded(parent):
                raise NodeCreateNotAllowed("Cannot create a child under a superseded node.")
            if parent.get("status") == "done":
                raise NodeCreateNotAllowed("Cannot create a child under a done node.")

            now = iso_now()
            active_children = self.tree_service.active_child_ids(parent, node_by_id)
            display_order = len(active_children)
            new_node_id = uuid4().hex

            child_status = "ready"
            if active_children:
                child_status = "locked"
            elif parent.get("status") == "locked" or self.tree_service.has_locked_ancestor(parent, node_by_id):
                child_status = "locked"

            if not active_children and parent.get("status") in {"ready", "in_progress"}:
                parent["status"] = "draft"

            parent.setdefault("child_ids", []).append(new_node_id)
            parent_hnum = str(parent.get("hierarchical_number") or "1")
            child_node = {
                "node_id": new_node_id,
                "parent_id": parent_id,
                "child_ids": [],
                "status": child_status,
                "phase": "planning",
                "node_kind": "original",
                "planning_mode": None,
                "depth": int(parent.get("depth", 0)) + 1,
                "display_order": display_order,
                "hierarchical_number": f"{parent_hnum}.{display_order + 1}",
                "split_metadata": None,
                "chat_session_id": None,
                "planning_thread_id": None,
                "execution_thread_id": None,
                "planning_thread_forked_from_node": None,
                "planning_thread_bootstrapped_at": None,
                "created_at": now,
            }
            try:
                self.storage.node_store.create_node_files(
                    project_id,
                    new_node_id,
                    task={"title": "New Node", "purpose": "", "responsibility": ""},
                )
                snapshot["tree_state"]["node_index"][new_node_id] = child_node
                snapshot["tree_state"]["active_node_id"] = new_node_id
                snapshot = self._persist_snapshot(project_id, snapshot)
            except Exception:
                if not self._snapshot_references_node(project_id, new_node_id):
                    self.storage.node_store.delete_node_files(project_id, new_node_id)
                raise
        return self._public_snapshot(project_id, snapshot)

    def get_documents(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )
            return self.storage.node_store.load_all(project_id, node_id)

    def get_task(self, project_id: str, node_id: str) -> Dict[str, str]:
        with self.storage.project_lock(project_id):
            self._load_node(project_id, node_id)
            return self.storage.node_store.load_task(project_id, node_id)

    def get_brief(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )
            return self.storage.node_store.load_brief(project_id, node_id)

    def get_briefing(self, project_id: str, node_id: str) -> Dict[str, Any]:
        return self.get_brief(project_id, node_id)

    def get_spec(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )
            return self.storage.node_store.load_spec(project_id, node_id)

    def get_state(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            return self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )

    def update_task(self, project_id: str, node_id: str, updates: Dict[str, str]) -> Dict[str, str]:
        if not updates:
            raise InvalidRequest("Provide at least one field to update.")

        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            self._assert_document_editable(node, state=state, document="task")
            task = self.storage.node_store.load_task(project_id, node_id)
            next_task = dict(task)
            if "title" in updates:
                cleaned_title = updates["title"].strip()
                if not cleaned_title:
                    raise InvalidRequest("Title cannot be empty.")
                next_task["title"] = cleaned_title
            if "purpose" in updates:
                next_task["purpose"] = updates["purpose"]
            if "responsibility" in updates:
                next_task["responsibility"] = updates["responsibility"]
            if not self._document_changed(task, next_task, ("title", "purpose", "responsibility")):
                return task
            self.storage.node_store.save_task(project_id, node_id, next_task)
            self._reset_node_workflow(project_id, node_id, node)
            self._persist_snapshot(project_id, snapshot)
            return next_task

    def update_briefing(self, project_id: str, node_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        raise NodeUpdateNotAllowed("Brief is locked and system-generated.")

    def update_spec(self, project_id: str, node_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not updates:
            raise InvalidRequest("Provide at least one field to update.")

        keys = (
            "mission",
            "scope",
            "constraints",
            "autonomy",
            "verification",
            "execution_controls",
            "assumptions",
        )
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            self._assert_document_editable(node, state=state, document="spec")
            spec = self.storage.node_store.load_spec(project_id, node_id)
            next_spec = copy.deepcopy(spec)
            for key in keys:
                if key in updates:
                    next_spec[key] = self._merge_section_object(next_spec.get(key), updates[key], section_name=key)
            if not self._document_changed(spec, next_spec, keys):
                return spec
            self.storage.node_store.save_spec(project_id, node_id, next_spec)
            state["spec_initialized"] = True
            state["spec_generated"] = True
            if not int(state.get("initialized_from_brief_version", 0) or 0):
                state["initialized_from_brief_version"] = int(state.get("brief_version", 0) or 0)
            state["spec_content_hash"] = self._content_hash(next_spec)
            if bool(state.get("spec_confirmed")):
                state["spec_confirmed"] = False
                state["spec_status"] = "needs_reconfirm"
                state["phase"] = "spec_review"
            elif str(state.get("phase") or "") == "ready_for_execution":
                state["phase"] = "spec_review"
                state["spec_status"] = "draft"
            if int(state.get("active_plan_version", 0) or 0) > 0:
                state["plan_status"] = "abandoned"
                state["active_plan_version"] = 0
                state["bound_plan_spec_version"] = 0
                state["bound_plan_brief_version"] = 0
                state["bound_plan_input_version"] = 0
                state["bound_turn_id"] = ""
                state["final_plan_item_id"] = ""
                state["structured_result_hash"] = ""
                state["resolved_request_ids"] = []
                state["spec_update_change_summary"] = ""
                state["spec_update_changed_contract_axes"] = []
                state["spec_update_recommended_next_step"] = ""
            self.storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            return next_spec

    def update_node(
        self,
        project_id: str,
        node_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        if title is None and description is None:
            raise InvalidRequest("Provide at least one field to update.")

        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            self._assert_document_editable(node, state=state, document="task")
            task = self.storage.node_store.load_task(project_id, node_id)
            next_task = dict(task)
            if title is not None:
                cleaned = title.strip()
                if not cleaned:
                    raise InvalidRequest("Title cannot be empty.")
                next_task["title"] = cleaned
            if description is not None:
                next_task["purpose"] = description.strip()
            if not self._document_changed(task, next_task, ("title", "purpose", "responsibility")):
                return self._public_snapshot(project_id, snapshot)
            self.storage.node_store.save_task(project_id, node_id, next_task)
            self._reset_node_workflow(project_id, node_id, node)
            snapshot = self._persist_snapshot(project_id, snapshot)
        return self._public_snapshot(project_id, snapshot)

    def confirm_task(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            self._assert_node_editable(node)
            state = self.storage.node_store.load_state(project_id, node_id)
            state = self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )
            current_phase = self._current_phase(node, state)
            retry_brief_pipeline = self._should_retry_brief_pipeline(state, current_phase=current_phase)
            if bool(state.get("task_confirmed")) and current_phase in {
                "awaiting_brief",
                "spec_review",
                "ready_for_execution",
                "executing",
                "blocked_on_spec_question",
                "closed",
            } and not retry_brief_pipeline:
                return state
            if current_phase != "planning" and not retry_brief_pipeline:
                raise ConfirmationNotAllowed("Task can only be confirmed from 'planning' phase.")
            task = self.storage.node_store.load_task(project_id, node_id)
            if not str(task.get("title") or "").strip():
                raise ConfirmationNotAllowed("Task must have a non-empty title.")
            if not str(task.get("purpose") or "").strip():
                raise ConfirmationNotAllowed("Task must have a non-empty purpose.")
            if (
                self._agent_operation_service is None
                or self._brief_generation_service is None
                or self._spec_generation_service is None
            ):
                state["task_confirmed"] = True
                self._set_phase(node=node, state=state, phase="awaiting_brief")
                self.storage.node_store.save_state(project_id, node_id, state)
                self._persist_snapshot(project_id, snapshot)
            else:
                handle = self._start_agent_operation(
                    project_id,
                    node_id,
                    operation="brief_pipeline",
                    not_allowed_message="Another agent operation is already active for this node.",
                )
                reserved_state = copy.deepcopy(state)
                reserved_state["task_confirmed"] = True
                reserved_state["brief_generation_status"] = "generating"
                reserved_state["brief_generation_started_at"] = iso_now()
                clear_last_agent_failure(reserved_state)
                self._set_phase(node=node, state=reserved_state, phase="awaiting_brief")
                self.storage.node_store.save_state(project_id, node_id, reserved_state)
                self._persist_snapshot(project_id, snapshot)
                try:
                    self._agent_operation_service.publish_started(
                        handle,
                        stage="preparing",
                        message="Preparing agent handoff.",
                    )
                    threading.Thread(
                        target=self._run_confirm_task_pipeline,
                        kwargs={
                            "project_id": project_id,
                            "node_id": node_id,
                            "handle": handle,
                        },
                        daemon=True,
                    ).start()
                    return reserved_state
                except Exception:
                    self._agent_operation_service.finish_operation(handle)
                    raise

        return self._initialize_handoff_artifacts(
            project_id,
            node_id,
            predecessor_node_id=None,
            auto_confirm_task=False,
        )

    def _run_confirm_task_pipeline(
        self,
        *,
        project_id: str,
        node_id: str,
        handle: AgentOperationHandle,
    ) -> None:
        try:
            self._agent_operation_service.publish_progress(
                handle,
                stage="generating_brief",
                message="Generating Brief.",
            )
            if self._brief_generation_service is not None:
                self._brief_generation_service.generate_brief(
                    project_id,
                    node_id,
                    predecessor_node_id=None,
                    reserve_state=False,
                )
            else:
                self._fallback_generate_brief(project_id, node_id, predecessor_node_id=None)

            needs_spec = False
            with self.storage.project_lock(project_id):
                snapshot, node = self._load_node(project_id, node_id)
                state = self.storage.node_store.load_state(project_id, node_id)
                needs_spec = not bool(state.get("spec_initialized"))
                if needs_spec:
                    state["spec_generation_status"] = "generating"
                    state["spec_generation_started_at"] = iso_now()
                    clear_last_agent_failure(state)
                    self.storage.node_store.save_state(project_id, node_id, state)
                    self._persist_snapshot(project_id, snapshot)

            if needs_spec:
                self._agent_operation_service.publish_progress(
                    handle,
                    stage="drafting_spec",
                    message="Drafting Spec.",
                )
                if self._spec_generation_service is not None:
                    self._spec_generation_service.generate_spec(
                        project_id,
                        node_id,
                        reserve_state=False,
                    )
                else:
                    self._fallback_initialize_spec(project_id, node_id)

            self._agent_operation_service.publish_completed(
                handle,
                stage="completed",
                message="Spec is ready to review.",
            )
        except Exception as exc:
            logger.exception("Confirm task pipeline failed for node %s", node_id)
            self._agent_operation_service.publish_failed(
                handle,
                stage="failed",
                message=str(exc),
            )
        finally:
            self._agent_operation_service.finish_operation(handle)

    def _start_agent_operation(
        self,
        project_id: str,
        node_id: str,
        *,
        operation: str,
        not_allowed_message: str,
    ) -> AgentOperationHandle:
        if self._agent_operation_service is None:
            raise ConfirmationNotAllowed(not_allowed_message)
        try:
            return self._agent_operation_service.start_operation(project_id, node_id, operation)
        except RuntimeError as exc:
            raise ConfirmationNotAllowed(not_allowed_message) from exc

    def reconcile_stale_generations(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            return self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )

    def confirm_briefing(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            self._assert_node_editable(node)
            state = self.storage.node_store.load_state(project_id, node_id)
            state = self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )
            if str(state.get("brief_generation_status") or "").strip().lower() != "ready":
                raise ConfirmationNotAllowed("Brief does not exist yet for this node.")
            return state

    def confirm_spec(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            self._assert_node_editable(node)
            state = self.storage.node_store.load_state(project_id, node_id)
            state = self._reconcile_stale_generations_locked(
                project_id,
                node_id,
                snapshot=snapshot,
                node=node,
                state=state,
            )
            if bool(state.get("spec_confirmed")) and self._current_phase(node, state) == "ready_for_execution":
                return state
            current_phase = self._current_phase(node, state)
            if current_phase not in {"spec_review", "blocked_on_spec_question"}:
                raise ConfirmationNotAllowed(
                    "Spec can only be confirmed from 'spec_review' or 'blocked_on_spec_question' phase."
                )
            if not bool(state.get("spec_initialized") or state.get("spec_generated")):
                raise ConfirmationNotAllowed("Spec must exist before it can be confirmed.")
            spec = self.storage.node_store.load_spec(project_id, node_id)
            self._validate_spec_confirmable(spec)
            state["spec_confirmed"] = True
            state["active_spec_version"] = int(state.get("active_spec_version", 0) or 0) + 1
            state["spec_status"] = "confirmed"
            state["spec_confirmed_at"] = iso_now()
            state["spec_content_hash"] = self._content_hash(spec)
            if not int(state.get("initialized_from_brief_version", 0) or 0):
                state["initialized_from_brief_version"] = int(state.get("brief_version", 0) or 0)
            state["pending_plan_questions"] = []
            state["pending_spec_questions"] = []
            state["spec_update_change_summary"] = ""
            state["spec_update_changed_contract_axes"] = []
            state["spec_update_recommended_next_step"] = ""
            self._set_phase(node=node, state=state, phase="ready_for_execution")
            self.storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            return state

    def advance_to_executing(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            self._assert_node_editable(node)
            state = self.storage.node_store.load_state(project_id, node_id)
            current_phase = self._current_phase(node, state)
            if current_phase == "executing":
                return state
            if current_phase != "ready_for_execution":
                raise NodeUpdateNotAllowed(
                    f"Cannot start execution in phase '{current_phase}'. "
                    "Node must be in 'ready_for_execution' phase."
                )
            self._set_phase(node=node, state=state, phase="executing")
            state["run_status"] = "executing"
            if node.get("status") == "ready":
                node["status"] = "in_progress"
            self.storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            return state

    def apply_plan_finalized_spec(
        self,
        project_id: str,
        node_id: str,
        spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            self._assert_node_editable(node)
            state = self.storage.node_store.load_state(project_id, node_id)
            current_phase = self._current_phase(node, state)
            if current_phase not in {"ready_for_execution", "executing"}:
                raise NodeUpdateNotAllowed(
                    f"Cannot finalize plan spec in phase '{current_phase}'."
                )
            self._validate_spec_confirmable(spec)
            self.storage.node_store.save_spec(project_id, node_id, spec)
            state["spec_initialized"] = True
            state["spec_generated"] = True
            state["spec_generation_status"] = "idle"
            state["spec_confirmed"] = True
            state["active_spec_version"] = int(state.get("active_spec_version", 0) or 0) + 1
            state["spec_status"] = "confirmed"
            state["spec_confirmed_at"] = iso_now()
            state["spec_content_hash"] = self._content_hash(spec)
            if not int(state.get("initialized_from_brief_version", 0) or 0):
                state["initialized_from_brief_version"] = int(state.get("brief_version", 0) or 0)
            state["pending_plan_questions"] = []
            state["pending_spec_questions"] = []
            state["spec_update_change_summary"] = ""
            state["spec_update_changed_contract_axes"] = []
            state["spec_update_recommended_next_step"] = ""
            self.storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            return state

    def complete_node(self, project_id: str, node_id: str) -> Dict[str, Any]:
        fork_intent: tuple[str, str, str] | None = None
        handoff_intent: tuple[str, str] | None = None
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            node_by_id = self.tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            if self._is_superseded(node):
                raise CompleteNotAllowed("Cannot complete a superseded node.")
            if node.get("status") not in {"ready", "in_progress"}:
                raise CompleteNotAllowed("Only ready or in_progress leaf nodes can complete.")
            if self.tree_service.has_active_children(node, node_by_id):
                raise CompleteNotAllowed("Only leaf nodes can complete.")
            planning_state = self.storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
            if planning_state.get("status") == "active":
                raise CompleteNotAllowed("Cannot complete a node while planning is active.")
            state = self.storage.node_store.load_state(project_id, node_id)
            current_phase = self._current_phase(node, state)
            if current_phase not in {"ready_for_execution", "executing"}:
                raise CompleteNotAllowed(
                    f"Cannot complete a node in phase '{current_phase}'. "
                    "Node must be in 'ready_for_execution' or 'executing' phase."
                )

            node["status"] = "done"
            self._mark_node_closed(project_id, node_id, node)
            completed_node_ids = [node_id]
            self.storage.thread_store.block_mergeable_ask_packets(
                project_id,
                node_id,
                reason="Node completed",
            )
            self.tree_service.unlock_next_sibling(node, node_by_id)
            completed_node_ids.extend(self._cascade_done(project_id, node.get("parent_id"), node_by_id))
            for completed_node_id in completed_node_ids[1:]:
                self.storage.thread_store.block_mergeable_ask_packets(
                    project_id,
                    completed_node_id,
                    reason="Node completed",
                )
            next_active_node_id = self.tree_service.first_actionable_leaf(snapshot, node_by_id)
            snapshot["tree_state"]["active_node_id"] = next_active_node_id
            snapshot = self._persist_snapshot(project_id, snapshot)
            snapshot_updated_at = str(snapshot.get("updated_at") or "")
            if (
                self._thread_service is not None
                and isinstance(next_active_node_id, str)
                and next_active_node_id
                and next_active_node_id != node_id
            ):
                fork_intent = (node_id, next_active_node_id, snapshot_updated_at)
            if isinstance(next_active_node_id, str) and next_active_node_id and next_active_node_id != node_id:
                handoff_intent = (next_active_node_id, node_id)

        if fork_intent is not None and self._should_fork_planning_thread(project_id, *fork_intent):
            self._thread_service.fork_planning_thread(project_id, fork_intent[0], fork_intent[1])

        if handoff_intent is not None:
            self._initialize_handoff_artifacts(
                project_id,
                handoff_intent[0],
                predecessor_node_id=handoff_intent[1],
                auto_confirm_task=True,
            )

        snapshot = self.storage.project_store.load_snapshot(project_id)
        return self._public_snapshot(project_id, snapshot)

    def _initialize_handoff_artifacts(
        self,
        project_id: str,
        node_id: str,
        *,
        predecessor_node_id: str | None,
        auto_confirm_task: bool,
    ) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            if self._is_superseded(node) or node.get("status") == "done":
                return self.storage.node_store.load_state(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            task = self.storage.node_store.load_task(project_id, node_id)
            if not str(task.get("title") or "").strip() or not str(task.get("purpose") or "").strip():
                return state
            if auto_confirm_task and not bool(state.get("task_confirmed")):
                state["task_confirmed"] = True
                self._set_phase(node=node, state=state, phase="awaiting_brief")
                self.storage.node_store.save_state(project_id, node_id, state)
                self._persist_snapshot(project_id, snapshot)
            if self._brief_ready(state) and bool(state.get("spec_initialized")):
                return state

        if not self._brief_ready(self.storage.node_store.load_state(project_id, node_id)):
            if self._brief_generation_service is not None:
                self._brief_generation_service.generate_brief(
                    project_id,
                    node_id,
                    predecessor_node_id=predecessor_node_id,
                )
            else:
                self._fallback_generate_brief(project_id, node_id, predecessor_node_id=predecessor_node_id)

        with self.storage.project_lock(project_id):
            state = self.storage.node_store.load_state(project_id, node_id)
            needs_spec = not bool(state.get("spec_initialized"))

        if needs_spec:
            if self._spec_generation_service is not None:
                self._spec_generation_service.generate_spec(project_id, node_id)
            else:
                self._fallback_initialize_spec(project_id, node_id)

        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            if self._current_phase(node, state) == "awaiting_brief" and self._brief_ready(state):
                self._set_phase(node=node, state=state, phase="spec_review")
                self.storage.node_store.save_state(project_id, node_id, state)
                self._persist_snapshot(project_id, snapshot)
            return state

    def _fallback_generate_brief(
        self,
        project_id: str,
        node_id: str,
        *,
        predecessor_node_id: str | None,
    ) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            if self._brief_ready(state):
                return state
            task = self.storage.node_store.load_task(project_id, node_id)
            brief = {
                "node_snapshot": {
                    "node_summary": str(task.get("title") or "").strip(),
                    "why_this_node_exists_now": str(task.get("purpose") or "").strip(),
                    "current_focus": str(
                        task.get("responsibility") or task.get("purpose") or ""
                    ).strip(),
                },
                "active_inherited_context": self._fallback_inherited_context(project_id, node),
                "accepted_upstream_facts": self._fallback_upstream_facts(project_id, predecessor_node_id),
                "runtime_state": {
                    "status": str(node.get("status") or "ready"),
                    "completed_so_far": [],
                    "current_blockers": [],
                    "next_best_action": "Review and confirm the agent-recommended Spec draft.",
                },
                "pending_escalations": {
                    "open_risks": [],
                    "pending_user_decisions": [],
                    "fallback_direction_if_unanswered": (
                        "Stay within confirmed constraints and reopen Spec on conflict."
                    ),
                },
            }
            self.storage.node_store.save_brief(project_id, node_id, brief)
            state["brief_generation_status"] = "ready"
            state["brief_generation_started_at"] = ""
            state["brief_version"] = max(1, int(state.get("brief_version", 0) or 0) + 1)
            state["brief_created_at"] = iso_now()
            state["brief_created_from_predecessor_node_id"] = predecessor_node_id or ""
            state["brief_generated_by"] = "system_fallback"
            state["brief_source_hash"] = self._content_hash(brief)
            state["brief_source_refs"] = self._fallback_brief_source_refs(node_id, predecessor_node_id)
            state["brief_late_upstream_policy"] = "ignore"
            state["briefing_confirmed"] = True
            self._set_phase(node=node, state=state, phase="spec_review")
            self.storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            return state

    def _fallback_initialize_spec(self, project_id: str, node_id: str) -> Dict[str, Any]:
        with self.storage.project_lock(project_id):
            snapshot, node = self._load_node(project_id, node_id)
            state = self.storage.node_store.load_state(project_id, node_id)
            task = self.storage.node_store.load_task(project_id, node_id)
            goal = str(task.get("title") or "").strip()
            success_outcome = str(task.get("purpose") or "").strip()
            must_do = str(task.get("responsibility") or success_outcome).strip()
            spec = {
                "mission": {
                    "goal": goal,
                    "success_outcome": success_outcome,
                    "implementation_level": "working",
                },
                "scope": {
                    "must_do": [must_do or "Deliver the node outcome defined in Mission."],
                    "must_not_do": ["Do not expand beyond this node's task boundary."],
                    "deferred_work": [],
                },
                "constraints": {
                    "hard_constraints": ["Honor the confirmed task and inherited constraints in Brief."],
                    "change_budget": "Keep changes scoped to the current node.",
                    "touch_boundaries": [
                        "Stay within the current project workspace unless explicitly required."
                    ],
                    "external_dependencies": [],
                },
                "autonomy": {
                    "allowed_decisions": [
                        "Local implementation choices consistent with Mission and Constraints."
                    ],
                    "requires_confirmation": [
                        "Any scope expansion or conflicting requirement."
                    ],
                    "default_policy_when_unclear": "ask_user",
                },
                "verification": {
                    "acceptance_checks": [
                        f"Output matches the requested outcome: {success_outcome or goal}"
                    ],
                    "definition_of_done": (
                        "The node deliverable is complete and evidence is captured."
                    ),
                    "evidence_expected": [
                        "A concise execution summary and any relevant verification artifacts."
                    ],
                },
                "execution_controls": {
                    "quality_profile": "standard",
                    "tooling_limits": ["Stay within the project workspace."],
                    "output_expectation": "concise progress updates",
                    "conflict_policy": "reopen_spec",
                    "missing_decision_policy": "reopen_spec",
                },
                "assumptions": {
                    "assumptions_in_force": [
                        f"Brief v{int(state.get('brief_version', 0) or 0)} is the locked handoff context."
                    ]
                },
            }
            self.storage.node_store.save_spec(project_id, node_id, spec)
            state["spec_initialized"] = True
            state["spec_generated"] = True
            state["spec_generation_status"] = "idle"
            state["spec_generation_started_at"] = ""
            state["spec_status"] = "draft"
            state["initialized_from_brief_version"] = int(state.get("brief_version", 0) or 0)
            state["spec_content_hash"] = self._content_hash(spec)
            self._set_phase(node=node, state=state, phase="spec_review")
            self.storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            return state

    def _fallback_inherited_context(self, project_id: str, node: Dict[str, Any]) -> Dict[str, Any]:
        section = {
            "active_goals_from_parent": [],
            "active_constraints_from_parent": [],
            "active_decisions_in_force": [],
        }
        parent_id = node.get("parent_id")
        if not isinstance(parent_id, str) or not parent_id:
            return section
        parent_state = self.storage.node_store.load_state(project_id, parent_id)
        parent_spec = self.storage.node_store.load_spec(project_id, parent_id)
        parent_task = self.storage.node_store.load_task(project_id, parent_id)
        if bool(parent_state.get("spec_confirmed")):
            goal = str(parent_task.get("purpose") or parent_task.get("title") or "").strip()
            if goal:
                section["active_goals_from_parent"] = [goal]
            section["active_constraints_from_parent"] = self._string_list(
                parent_spec.get("constraints", {}).get("hard_constraints")
            )
            section["active_decisions_in_force"] = self._string_list(
                parent_spec.get("scope", {}).get("must_do")
            )
        return section

    def _fallback_upstream_facts(self, project_id: str, predecessor_node_id: str | None) -> Dict[str, Any]:
        section = {
            "accepted_outputs": [],
            "available_artifacts": [],
            "confirmed_dependencies": [],
        }
        if predecessor_node_id:
            predecessor_task = self.storage.node_store.load_task(project_id, predecessor_node_id)
            section["accepted_outputs"] = [
                f"Previous node {str(predecessor_task.get('title') or predecessor_node_id).strip()} has completed."
            ]
            section["available_artifacts"] = [
                "Refer to completed upstream work and workspace outputs from the predecessor node."
            ]
        return section

    def _fallback_brief_source_refs(self, node_id: str, predecessor_node_id: str | None) -> list[str]:
        refs = [f"task:{node_id}"]
        if predecessor_node_id:
            refs.append(f"predecessor:{predecessor_node_id}")
        return refs

    def _validate_spec_confirmable(self, spec: Dict[str, Any]) -> None:
        mission = spec.get("mission", {}) if isinstance(spec.get("mission"), dict) else {}
        scope = spec.get("scope", {}) if isinstance(spec.get("scope"), dict) else {}
        verification = (
            spec.get("verification", {}) if isinstance(spec.get("verification"), dict) else {}
        )
        autonomy = spec.get("autonomy", {}) if isinstance(spec.get("autonomy"), dict) else {}
        if not str(mission.get("goal") or "").strip() or not str(
            mission.get("success_outcome") or ""
        ).strip():
            raise ConfirmationNotAllowed("Mission.goal and Mission.success_outcome are required before confirming Spec.")
        if not self._string_list(scope.get("must_do")) and not self._string_list(
            verification.get("acceptance_checks")
        ):
            raise ConfirmationNotAllowed(
                "Spec must include at least one of Scope.must_do or Verification.acceptance_checks."
            )
        if not str(autonomy.get("default_policy_when_unclear") or "").strip():
            raise ConfirmationNotAllowed(
                "Autonomy.default_policy_when_unclear is required before confirming Spec."
            )

    def _reset_node_workflow(self, project_id: str, node_id: str, node: Dict[str, Any]) -> None:
        state = self.storage.node_store.load_state(project_id, node_id)
        state.update(
            {
                "phase": "planning",
                "task_confirmed": False,
                "briefing_confirmed": False,
                "brief_generation_status": "missing",
                "brief_generation_started_at": "",
                "brief_version": 0,
                "brief_created_at": "",
                "brief_created_from_predecessor_node_id": "",
                "brief_generated_by": "",
                "brief_source_hash": "",
                "brief_source_refs": [],
                "brief_late_upstream_policy": "ignore",
                "spec_initialized": False,
                "spec_generated": False,
                "spec_generation_status": "idle",
                "spec_generation_started_at": "",
                "spec_confirmed": False,
                "active_spec_version": 0,
                "spec_status": "draft",
                "spec_confirmed_at": "",
                "initialized_from_brief_version": 0,
                "spec_content_hash": "",
                "active_plan_version": 0,
                "plan_status": "none",
                "bound_plan_spec_version": 0,
                "bound_plan_brief_version": 0,
                "active_plan_input_version": 0,
                "bound_plan_input_version": 0,
                "bound_turn_id": "",
                "final_plan_item_id": "",
                "structured_result_hash": "",
                "resolved_request_ids": [],
                "spec_update_change_summary": "",
                "spec_update_changed_contract_axes": [],
                "spec_update_recommended_next_step": "",
                "run_status": "idle",
                "pending_plan_questions": [],
                "pending_spec_questions": [],
                "execution_thread_id": "",
            }
        )
        self.storage.node_store.save_brief(project_id, node_id, empty_brief())
        self.storage.node_store.save_spec(project_id, node_id, empty_spec())
        self.storage.node_store.save_plan(project_id, node_id, {"content": ""})
        self.storage.node_store.save_state(project_id, node_id, state)
        node["execution_thread_id"] = None
        node["phase"] = "planning"

    def _reconcile_stale_generations_locked(
        self,
        project_id: str,
        node_id: str,
        *,
        snapshot: Dict[str, Any],
        node: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        state_changed = False
        snapshot_changed = False

        if self._should_fail_stale_generation(
            project_id,
            node_id,
            state,
            status_key="brief_generation_status",
            started_at_key="brief_generation_started_at",
            timeout_sec=self._brief_generation_timeout_sec(),
        ):
            state["brief_generation_status"] = "failed"
            state["brief_generation_started_at"] = ""
            state["phase"] = "awaiting_brief"
            set_last_agent_failure(
                state,
                operation="brief_pipeline",
                message="Brief generation was interrupted before completion.",
            )
            state_changed = True
            if self._current_phase(node, state) != "awaiting_brief" or node.get("phase") != "awaiting_brief":
                node["phase"] = "awaiting_brief"
                snapshot_changed = True

        if self._should_fail_stale_generation(
            project_id,
            node_id,
            state,
            status_key="spec_generation_status",
            started_at_key="spec_generation_started_at",
            timeout_sec=self._spec_generation_timeout_sec(),
        ):
            state["spec_generation_status"] = "failed"
            state["spec_generation_started_at"] = ""
            set_last_agent_failure(
                state,
                operation="generate_spec",
                message="Spec generation was interrupted before completion.",
            )
            state_changed = True

        if state_changed:
            self.storage.node_store.save_state(project_id, node_id, state)
        if snapshot_changed:
            self._persist_snapshot(project_id, snapshot)
        return state

    def _should_fail_stale_generation(
        self,
        project_id: str,
        node_id: str,
        state: Dict[str, Any],
        *,
        status_key: str,
        started_at_key: str,
        timeout_sec: int,
    ) -> bool:
        if str(state.get(status_key) or "").strip().lower() != "generating":
            return False

        active_operation = (
            self._agent_operation_service.is_active(project_id, node_id)
            if self._agent_operation_service is not None
            else False
        )
        started_at = self._generation_started_at(project_id, node_id, state, started_at_key)
        if started_at is None:
            return not active_operation

        deadline = started_at + timedelta(seconds=max(10, int(timeout_sec)) + _GENERATION_STALE_GRACE_SEC)
        return datetime.now(timezone.utc) >= deadline or not active_operation

    def _generation_started_at(
        self,
        project_id: str,
        node_id: str,
        state: Dict[str, Any],
        started_at_key: str,
    ) -> datetime | None:
        raw_started_at = str(state.get(started_at_key) or "").strip()
        parsed_started_at = self._parse_iso_datetime(raw_started_at)
        if parsed_started_at is not None:
            return parsed_started_at

        state_path = self.storage.node_store.node_dir(project_id, node_id) / "state.yaml"
        try:
            return datetime.fromtimestamp(state_path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return None

    def _parse_iso_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _brief_generation_timeout_sec(self) -> int:
        return max(10, int(getattr(self._brief_generation_service, "_timeout_sec", 120)))

    def _spec_generation_timeout_sec(self) -> int:
        return max(10, int(getattr(self._spec_generation_service, "_timeout_sec", 120)))

    def _cascade_done(
        self,
        project_id: str,
        parent_id: Optional[str],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> list[str]:
        current_parent_id = parent_id
        visited: Set[str] = set()
        completed_parent_ids: list[str] = []
        while isinstance(current_parent_id, str) and current_parent_id and current_parent_id not in visited:
            visited.add(current_parent_id)
            parent = node_by_id.get(current_parent_id)
            if parent is None or self._is_superseded(parent):
                return completed_parent_ids
            active_children = self.tree_service.active_child_ids(parent, node_by_id)
            if not active_children:
                return completed_parent_ids
            if any(node_by_id[child_id].get("status") != "done" for child_id in active_children):
                return completed_parent_ids
            parent["status"] = "done"
            self._mark_node_closed(project_id, current_parent_id, parent)
            completed_parent_ids.append(current_parent_id)
            self.tree_service.unlock_next_sibling(parent, node_by_id)
            current_parent_id = parent.get("parent_id")
        return completed_parent_ids

    def _persist_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        now = iso_now()
        snapshot["updated_at"] = now
        snapshot.setdefault("project", {})["updated_at"] = now
        self.storage.project_store.save_snapshot(project_id, snapshot)
        self.storage.project_store.touch_meta(project_id, now)
        return snapshot

    def _should_fork_planning_thread(
        self,
        project_id: str,
        source_node_id: str,
        target_node_id: str,
        snapshot_updated_at: str,
    ) -> bool:
        with self.storage.project_lock(project_id):
            snapshot = self.storage.project_store.load_snapshot(project_id)
            if str(snapshot.get("updated_at") or "") != snapshot_updated_at:
                return False
            if snapshot.get("tree_state", {}).get("active_node_id") != target_node_id:
                return False
            node_by_id = self.tree_service.node_index(snapshot)
            source = node_by_id.get(source_node_id)
            target = node_by_id.get(target_node_id)
            if source is None or target is None:
                return False
            if source.get("status") != "done":
                return False
            planning_thread_id = target.get("planning_thread_id")
            if isinstance(planning_thread_id, str) and planning_thread_id.strip():
                return False
            return True

    def _is_superseded(self, node: Dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))

    def _assert_node_editable(self, node: Dict[str, Any]) -> None:
        if self._is_superseded(node):
            raise NodeUpdateNotAllowed("Cannot edit a superseded node.")
        if node.get("status") == "done":
            raise NodeUpdateNotAllowed("Cannot edit a done node.")

    def _assert_document_editable(
        self,
        node: Dict[str, Any],
        *,
        state: Dict[str, Any],
        document: str,
    ) -> None:
        self._assert_node_editable(node)
        current_phase = self._current_phase(node, state)
        if current_phase == "executing":
            raise NodeUpdateNotAllowed(f"Cannot edit {document} while a node is executing.")

    def _load_node(self, project_id: str, node_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        snapshot = self.storage.project_store.load_snapshot(project_id)
        node_by_id = self.tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        return snapshot, node

    def _current_phase(self, node: Dict[str, Any], state: Dict[str, Any] | None = None) -> str:
        if isinstance(state, dict):
            phase = str(state.get("phase") or "").strip()
            if phase:
                return phase
        return str(node.get("phase") or "planning")

    def _set_phase(self, *, node: Dict[str, Any], state: Dict[str, Any], phase: str) -> None:
        node["phase"] = phase
        state["phase"] = phase

    def _document_changed(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        keys: tuple[str, ...],
    ) -> bool:
        return any(before.get(key) != after.get(key) for key in keys)

    def _merge_section_object(
        self,
        current_value: Any,
        incoming_value: Any,
        *,
        section_name: str,
    ) -> Dict[str, Any]:
        if not isinstance(incoming_value, dict):
            raise InvalidRequest(f"{section_name} must be an object.")
        current_section = current_value if isinstance(current_value, dict) else {}
        merged = dict(current_section)
        for key, value in incoming_value.items():
            merged[key] = copy.deepcopy(value)
        return merged

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _mark_node_closed(self, project_id: str, node_id: str, node: Dict[str, Any]) -> None:
        state = self.storage.node_store.load_state(project_id, node_id)
        self._set_phase(node=node, state=state, phase="closed")
        state["run_status"] = "completed"
        self.storage.node_store.save_state(project_id, node_id, state)

    def _snapshot_references_node(self, project_id: str, node_id: str) -> bool:
        tree = load_json(self.storage.project_store.tree_path(project_id))
        if not isinstance(tree, dict):
            return False
        return node_id in self.tree_service.node_index(tree)

    def _brief_ready(self, state: Dict[str, Any]) -> bool:
        return str(state.get("brief_generation_status") or "").strip().lower() == "ready"

    def _should_retry_brief_pipeline(self, state: Dict[str, Any], *, current_phase: str) -> bool:
        if not bool(state.get("task_confirmed")) or current_phase != "awaiting_brief":
            return False
        return str(state.get("brief_generation_status") or "").strip().lower() in {"failed", "missing"}

    def _content_hash(self, payload: Dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()

    def _public_snapshot(self, project_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        if self._snapshot_view_service is None:
            return snapshot
        thread_state = self.storage.thread_store.read_thread_state(project_id)
        return self._snapshot_view_service.to_public_snapshot(project_id, snapshot, thread_state)
