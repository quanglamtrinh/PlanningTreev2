from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from backend.ai.codex_client import CodexAppClient
from backend.ai.execute_prompt_builder import (
    build_execute_prompt,
    build_execute_retry_feedback,
    execute_issues,
    normalize_execute_payload,
    parse_execute_response,
)
from backend.ai.plan_prompt_builder import (
    build_plan_turn_prompt,
    build_plan_turn_retry_feedback,
    normalize_plan_turn_payload,
    parse_plan_turn_response,
    plan_turn_issues,
    plan_turn_output_schema,
)
from backend.errors.app_errors import (
    ChatTurnAlreadyActive,
    NodeNotFound,
    NodeUpdateNotAllowed,
    PlanExecuteInvalidResponse,
    PlanExecuteNotAllowed,
    PlanInputResolutionNotAllowed,
)
from backend.services.agent_operation_service import (
    AgentOperationHandle,
    AgentOperationService,
    clear_last_agent_failure,
    set_last_agent_failure,
)
from backend.services.node_service import NodeService
from backend.services.node_task_fields import load_task_prompt_fields
from backend.services.thread_service import ThreadService
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker, PlanningEventBroker

STALE_TURN_ERROR = "Session interrupted - the server restarted before this response completed."

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        storage: Storage,
        codex_client: CodexAppClient,
        event_broker: ChatEventBroker,
        thread_service: ThreadService | None = None,
        node_service: NodeService | None = None,
        agent_operation_service: AgentOperationService | None = None,
        planning_event_broker: PlanningEventBroker | None = None,
    ) -> None:
        self._storage = storage
        self._client = codex_client
        self._event_broker = event_broker
        self._planning_event_broker = planning_event_broker
        self._thread_service = thread_service
        self._node_service = node_service
        self._agent_operation_service = agent_operation_service
        self._live_turns_lock = threading.Lock()
        self._live_turns: set[tuple[str, str, str]] = set()

    def _publish_plan_lifecycle_event(self, project_id: str, node_id: str, event: dict[str, Any]) -> None:
        self._event_broker.publish(project_id, node_id, event)
        if self._planning_event_broker is not None:
            self._planning_event_broker.publish(project_id, node_id, event)

    def reconcile_interrupted_turns(self) -> None:
        for project_id in self._storage.project_store.list_project_ids():
            try:
                with self._storage.project_lock(project_id):
                    snapshot = self._storage.project_store.load_snapshot(project_id)
                    workspace_root = self._workspace_root_from_snapshot(snapshot)
                    if not workspace_root:
                        continue
                    thread_state = self._storage.thread_store.read_thread_state(project_id)
                    chat_state = self._storage.chat_store.read_chat_state(project_id)
                    node_ids = {
                        str(node_id)
                        for node_id in list(thread_state.keys()) + list(chat_state.keys())
                    }
                    for node_id in node_ids:
                        raw_session = self._select_raw_execution_session(
                            thread_state=thread_state,
                            chat_state=chat_state,
                            node_id=node_id,
                        )
                        session = self._normalize_session(
                            project_id=project_id,
                            node_id=node_id,
                            session=raw_session,
                            default_config=self._default_config(workspace_root),
                        )
                        session, recovered = self._recover_stale_turn(session)
                        if recovered or raw_session != session:
                            self._write_session_state(project_id, node_id, session)
                        if recovered and session.get("mode") == "plan":
                            state = self._storage.node_store.load_state(project_id, node_id)
                            if str(state.get("plan_status") or "") in {"generating", "waiting_on_input"}:
                                state["plan_status"] = "none"
                            state["run_status"] = "idle"
                            set_last_agent_failure(
                                state,
                                operation="plan",
                                message=STALE_TURN_ERROR,
                            )
                            self._storage.node_store.save_state(project_id, node_id, state)
            except Exception:
                logger.exception("Failed to reconcile interrupted chat turns for project %s", project_id)

    def get_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            _, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            session, changed = self._reconcile_plan_runtime_requests(session)
            if changed:
                self._write_session_state(project_id, node_id, session)
            return {"session": self._public_session(session)}

    def start_plan(self, project_id: str, node_id: str) -> dict[str, Any]:
        if self._node_service is None:
            raise PlanExecuteNotAllowed("Node service is required for planning.")

        handle = self._start_agent_operation(project_id, node_id, operation="plan")
        background_started = False
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            current_phase = str(state.get("phase") or node.get("phase") or "planning")
            if current_phase != "ready_for_execution":
                self._finish_agent_operation(handle)
                raise PlanExecuteNotAllowed(
                    f"Cannot start planning in phase '{current_phase}'. Node must be 'ready_for_execution'."
                )
            if not bool(state.get("spec_confirmed")):
                self._finish_agent_operation(handle)
                raise PlanExecuteNotAllowed("Spec must be confirmed before planning can start.")
            if str(state.get("brief_generation_status") or "").strip().lower() != "ready":
                self._finish_agent_operation(handle)
                raise PlanExecuteNotAllowed("Brief must exist before planning can start.")
            if str(state.get("plan_status") or "") == "waiting_on_input":
                self._finish_agent_operation(handle)
                raise PlanExecuteNotAllowed("The planner is already waiting on a native input request.")

        try:
            with self._storage.project_lock(project_id):
                snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
                state = self._storage.node_store.load_state(project_id, node_id)
                session = self._load_execution_session(
                    project_id=project_id,
                    node_id=node_id,
                    node=node,
                    workspace_root=workspace_root,
                )
                if session["active_turn_id"]:
                    raise ChatTurnAlreadyActive()

                state["plan_status"] = "generating"
                state["run_status"] = "planning"
                state["pending_plan_questions"] = []
                state["pending_spec_questions"] = []
                state["spec_update_change_summary"] = ""
                state["spec_update_changed_contract_axes"] = []
                state["spec_update_recommended_next_step"] = ""
                clear_last_agent_failure(state)
                session["mode"] = "plan"
                session["plan_message_start_index"] = len(session["messages"])
                session["pending_input_request"] = None
                session["runtime_request_registry"] = []
                session["runtime_thread_status"] = None
                self._storage.node_store.save_state(project_id, node_id, state)
                self._persist_snapshot(project_id, snapshot)

                created_at = iso_now()
                turn_id = new_id("chatturn")
                planner_request = (
                    "Create the execution plan for this node. "
                    "Ask the user any blocking questions before finalizing the plan."
                )
                user_message = {
                    "message_id": new_id("msg"),
                    "role": "user",
                    "content": planner_request,
                    "status": "completed",
                    "created_at": created_at,
                    "updated_at": created_at,
                    "error": None,
                }
                assistant_message = {
                    "message_id": new_id("msg"),
                    "role": "assistant",
                    "content": "",
                    "status": "pending",
                    "created_at": created_at,
                    "updated_at": created_at,
                    "error": None,
                }
                session["messages"].extend([user_message, assistant_message])
                session["active_turn_id"] = turn_id
                session["active_assistant_message_id"] = assistant_message["message_id"]
                session["status"] = "active"
                event = self._persist_session_event(
                    project_id,
                    node_id,
                    session,
                    {
                        "type": "message_created",
                        "active_turn_id": turn_id,
                        "user_message": copy.deepcopy(user_message),
                        "assistant_message": copy.deepcopy(assistant_message),
                    },
                )

            self._event_broker.publish(project_id, node_id, event)
            self._mark_live_turn(project_id, node_id, turn_id)
            if handle is not None and self._agent_operation_service is not None:
                self._agent_operation_service.publish_started(
                    handle,
                    stage="thinking",
                    message="Planner is thinking.",
                )
            self._start_background_plan_turn(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message["message_id"],
                user_message=planner_request,
                prior_plan_status="none",
                handle=handle,
            )
            background_started = True
            return {
                "status": "accepted",
                "user_message_id": user_message["message_id"],
                "assistant_message_id": assistant_message["message_id"],
            }
        except Exception:
            if not background_started:
                self._finish_agent_operation(handle)
            raise

    def resolve_plan_input(
        self,
        project_id: str,
        node_id: str,
        request_id: str,
        *,
        thread_id: str | None,
        turn_id: str | None,
        answers: dict[str, Any],
    ) -> dict[str, Any]:
        request_key = str(request_id or "").strip()
        if not request_key:
            raise ValueError("request_id is required")

        with self._storage.project_lock(project_id):
            _, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("mode") != "plan":
                raise PlanInputResolutionNotAllowed("Planner input can only be resolved during a plan session.")
            request = self._find_runtime_request(session.get("runtime_request_registry", []), request_key)
            if request is None:
                return {
                    "status": "already_resolved_or_stale",
                    "session": self._public_session(session),
                }
            expected_thread_id = str(request.get("thread_id") or "").strip()
            expected_turn_id = str(request.get("turn_id") or "").strip()
            if thread_id and str(thread_id).strip() != expected_thread_id:
                raise PlanInputResolutionNotAllowed("thread_id does not match the pending planner request.")
            if turn_id and str(turn_id).strip() != expected_turn_id:
                raise PlanInputResolutionNotAllowed("turn_id does not match the pending planner request.")
            if str(request.get("status") or "") != "pending":
                return {
                    "status": "already_resolved_or_stale",
                    "session": self._public_session(session),
                }

        runtime_record = self._client.resolve_runtime_request_user_input(request_key, answers=answers)
        if runtime_record is None:
            with self._storage.project_lock(project_id):
                _, node, workspace_root = self._load_node_context(project_id, node_id)
                session = self._load_execution_session(
                    project_id=project_id,
                    node_id=node_id,
                    node=node,
                    workspace_root=workspace_root,
                )
                session["runtime_request_registry"] = self._mark_runtime_request_status(
                    session.get("runtime_request_registry", []),
                    request_id=request_key,
                    status="stale",
                    resolved_at=iso_now(),
                    answer_payload=None,
                )
                if (
                    isinstance(session.get("pending_input_request"), dict)
                    and str(session["pending_input_request"].get("request_id") or "") == request_key
                ):
                    session["pending_input_request"] = None
                event = self._persist_session_event(
                    project_id,
                    node_id,
                    session,
                    {
                        "type": "plan_input_resolved",
                        "request_id": request_key,
                        "status": "stale",
                        "resolved_at": iso_now(),
                        "user_message": None,
                    },
                )
            self._publish_plan_lifecycle_event(project_id, node_id, event)
            return {
                "status": "already_resolved_or_stale",
                "session": self.get_session(project_id, node_id)["session"],
            }

        if runtime_record.status != "resolved":
            return {
                "status": "already_resolved_or_stale",
                "session": self.get_session(project_id, node_id)["session"],
            }

        with self._storage.project_lock(project_id):
            _, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            request = self._find_runtime_request(session.get("runtime_request_registry", []), request_key)
            if request is None:
                return {
                    "status": "already_resolved_or_stale",
                    "session": self._public_session(session),
                }
            user_message = self._make_runtime_request_user_message(request, {"answers": answers})
            session["runtime_request_registry"] = self._mark_runtime_request_status(
                session.get("runtime_request_registry", []),
                request_id=request_key,
                status="resolved",
                resolved_at=str(runtime_record.resolved_at or iso_now()),
                answer_payload={"answers": answers},
            )
            if (
                isinstance(session.get("pending_input_request"), dict)
                and str(session["pending_input_request"].get("request_id") or "") == request_key
            ):
                session["pending_input_request"] = None
            active_assistant_message_id = str(session.get("active_assistant_message_id") or "").strip()
            if active_assistant_message_id:
                self._insert_message_before_active_assistant(
                    session,
                    active_assistant_message_id,
                    user_message,
                )
                assistant_message = self._find_message(session, active_assistant_message_id)
                if assistant_message is not None:
                    assistant_message["content"] = "Planner is thinking..."
                    assistant_message["status"] = "streaming"
                    assistant_message["updated_at"] = iso_now()
            else:
                session["messages"].append(copy.deepcopy(user_message))
            state["active_plan_input_version"] = int(state.get("active_plan_input_version", 0) or 0) + 1
            state["plan_status"] = "generating"
            state["run_status"] = "planning"
            self._storage.node_store.save_state(project_id, node_id, state)
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "plan_input_resolved",
                    "request_id": request_key,
                    "status": "resolved",
                    "resolved_at": str(runtime_record.resolved_at or iso_now()),
                    "user_message": copy.deepcopy(user_message),
                },
            )
        self._publish_plan_lifecycle_event(project_id, node_id, event)
        return {
            "status": "resolved",
            "session": self.get_session(project_id, node_id)["session"],
        }

    def execute(self, project_id: str, node_id: str) -> dict[str, Any]:
        if self._node_service is None:
            raise PlanExecuteNotAllowed("Node service is required for execution.")

        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            current_phase = str(state.get("phase") or node.get("phase") or "planning")
            if current_phase != "ready_for_execution":
                raise PlanExecuteNotAllowed(
                    f"Cannot execute in phase '{current_phase}'. Node must be 'ready_for_execution'."
                )
            if not bool(state.get("spec_confirmed")):
                raise PlanExecuteNotAllowed("Spec must be confirmed before execution can start.")
            if str(state.get("brief_generation_status") or "").strip().lower() != "ready":
                raise PlanExecuteNotAllowed("Brief must exist before execution can start.")
            if str(state.get("plan_status") or "") != "ready":
                raise PlanExecuteNotAllowed("Create a ready plan before execution.")
            if int(state.get("bound_plan_spec_version", 0) or 0) != int(state.get("active_spec_version", 0) or 0):
                raise PlanExecuteNotAllowed("The current plan is stale. Re-run Plan before execution.")
            if int(state.get("bound_plan_brief_version", 0) or 0) != int(state.get("brief_version", 0) or 0):
                raise PlanExecuteNotAllowed("The current plan is not bound to the active Brief.")
            if str(state.get("plan_status") or "") == "waiting_on_input":
                raise PlanExecuteNotAllowed("Resolve the pending planner input before execution.")

        self._node_service.advance_to_executing(project_id, node_id)
        self._ensure_execution_thread(project_id, node_id)

        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session["active_turn_id"]:
                raise ChatTurnAlreadyActive()

            session["mode"] = "execute"
            state["run_status"] = "executing"
            self._storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)

            created_at = iso_now()
            turn_id = new_id("chatturn")
            user_message = {
                "message_id": new_id("msg"),
                "role": "user",
                "content": "Execute the current plan for this node using the active Task, Brief, confirmed Spec, and bound Plan.",
                "status": "completed",
                "created_at": created_at,
                "updated_at": created_at,
                "error": None,
            }
            assistant_message = {
                "message_id": new_id("msg"),
                "role": "assistant",
                "content": "",
                "status": "pending",
                "created_at": created_at,
                "updated_at": created_at,
                "error": None,
            }
            session["messages"].extend([user_message, assistant_message])
            session["active_turn_id"] = turn_id
            session["active_assistant_message_id"] = assistant_message["message_id"]
            session["status"] = "active"
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "message_created",
                    "active_turn_id": turn_id,
                    "user_message": copy.deepcopy(user_message),
                    "assistant_message": copy.deepcopy(assistant_message),
                },
            )

        self._event_broker.publish(project_id, node_id, event)
        self._mark_live_turn(project_id, node_id, turn_id)

        try:
            result = self._run_execute_turn(project_id, node_id)
        except Exception as exc:
            self._mark_turn_failed(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message["message_id"],
                error_message=str(exc),
            )
            self._restore_plan_ready_state(project_id, node_id, run_status="failed")
            raise
        else:
            self._commit_execute_result(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message["message_id"],
                result=result,
            )
            return {
                "status": result["status"],
                "session": self.get_session(project_id, node_id)["session"],
                "state": self._storage.node_store.load_state(project_id, node_id),
                "plan": self._storage.node_store.load_plan(project_id, node_id),
            }
        finally:
            self._clear_live_turn(project_id, node_id, turn_id)

    def plan_and_execute(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            _, node, _ = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            if str(state.get("plan_status") or "") != "ready":
                raise PlanExecuteNotAllowed("Combined plan-and-execute is deprecated. Click Plan before Execute.")
        return self.execute(project_id, node_id)

    def create_message(self, project_id: str, node_id: str, content: Any) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise ValueError("content is required")

        handle: AgentOperationHandle | None = None
        background_started = False
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            current_phase = str(state.get("phase") or node.get("phase") or "planning")
            if session.get("mode") == "plan":
                if current_phase != "ready_for_execution":
                    raise NodeUpdateNotAllowed(
                        f"Cannot send planner recovery input in phase '{current_phase}'."
                    )
                if session.get("pending_input_request"):
                    raise NodeUpdateNotAllowed(
                        "Use the planner input modal to answer the current native request."
                    )
                if str(state.get("plan_status") or "") not in {"waiting_on_input", "generating"}:
                    raise NodeUpdateNotAllowed("Click Plan before replying to the planner.")
                handle = self._start_agent_operation(project_id, node_id, operation="plan")
            elif current_phase != "executing":
                raise NodeUpdateNotAllowed(
                    f"Cannot send execution messages in phase '{current_phase}'. Start execution first."
                )

        if session.get("mode") != "plan":
            self._ensure_execution_thread(project_id, node_id)

        try:
            with self._storage.project_lock(project_id):
                snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
                state = self._storage.node_store.load_state(project_id, node_id)
                session = self._load_execution_session(
                    project_id=project_id,
                    node_id=node_id,
                    node=node,
                    workspace_root=workspace_root,
                )
                if session["active_turn_id"]:
                    raise ChatTurnAlreadyActive()

                prior_plan_status = str(state.get("plan_status") or "none")
                if session.get("mode") == "plan":
                    state["plan_status"] = "generating"
                    state["run_status"] = "planning"
                    clear_last_agent_failure(state)
                    session["pending_input_request"] = None
                    self._storage.node_store.save_state(project_id, node_id, state)
                    self._persist_snapshot(project_id, snapshot)
                else:
                    prior_plan_status = "none"

                created_at = iso_now()
                turn_id = new_id("chatturn")
                user_message = {
                    "message_id": new_id("msg"),
                    "role": "user",
                    "content": text,
                    "status": "completed",
                    "created_at": created_at,
                    "updated_at": created_at,
                    "error": None,
                }
                assistant_message = {
                    "message_id": new_id("msg"),
                    "role": "assistant",
                    "content": "",
                    "status": "pending",
                    "created_at": created_at,
                    "updated_at": created_at,
                    "error": None,
                }
                session["messages"].extend([user_message, assistant_message])
                session["active_turn_id"] = turn_id
                session["active_assistant_message_id"] = assistant_message["message_id"]
                session["status"] = "active"
                event = self._persist_session_event(
                    project_id,
                    node_id,
                    session,
                    {
                        "type": "message_created",
                        "active_turn_id": turn_id,
                        "user_message": copy.deepcopy(user_message),
                        "assistant_message": copy.deepcopy(assistant_message),
                    },
                )

            self._event_broker.publish(project_id, node_id, event)
            self._mark_live_turn(project_id, node_id, turn_id)
            if session.get("mode") == "plan":
                if handle is not None and self._agent_operation_service is not None:
                    self._agent_operation_service.publish_started(
                        handle,
                        stage="thinking",
                        message="Planner is thinking.",
                    )
                self._start_background_plan_turn(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message["message_id"],
                    user_message=text,
                    prior_plan_status="waiting_on_input"
                    if prior_plan_status == "waiting_on_input"
                    else prior_plan_status,
                    handle=handle,
                )
                background_started = True
                return {
                    "status": "accepted",
                    "user_message_id": user_message["message_id"],
                    "assistant_message_id": assistant_message["message_id"],
                }
        except Exception:
            if not background_started:
                self._finish_agent_operation(handle)
            raise

        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if node.get("status") == "ready":
                node["status"] = "in_progress"
                self._persist_snapshot(project_id, snapshot)

            prompt = self._build_prompt(
                project_id=project_id,
                snapshot=snapshot,
                node=node,
                workspace_root=workspace_root,
                config=session["config"],
                user_message=text,
            )
            thread_id = session.get("thread_id")
            config = copy.deepcopy(session["config"])

        self._start_background_turn(
            project_id=project_id,
            node_id=node_id,
            turn_id=turn_id,
            assistant_message_id=assistant_message["message_id"],
            prompt=prompt,
            thread_id=thread_id,
            config=config,
        )
        return {
            "status": "accepted",
            "user_message_id": user_message["message_id"],
            "assistant_message_id": assistant_message["message_id"],
        }

    def reset_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            _, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session["active_turn_id"]:
                raise ChatTurnAlreadyActive()
            if isinstance(node.get("execution_thread_id"), str) and node.get("execution_thread_id", "").strip():
                session["thread_id"] = node["execution_thread_id"]
            session["active_turn_id"] = None
            session["active_assistant_message_id"] = None
            session["status"] = "idle"
            session["mode"] = "idle"
            session["plan_message_start_index"] = 0
            session["pending_input_request"] = None
            session["runtime_request_registry"] = []
            session["runtime_thread_status"] = None
            session["messages"] = []
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "session_reset",
                    "session": copy.deepcopy(session),
                },
            )

        response = {"session": self._public_session(session)}
        self._event_broker.publish(project_id, node_id, event)
        return response

    def _ensure_execution_thread(self, project_id: str, node_id: str) -> None:
        if self._thread_service is None:
            return
        self._thread_service.create_execution_thread(project_id, node_id)

    def _run_plan_turn(self, project_id: str, node_id: str, user_message: str) -> dict[str, Any]:
        retry_feedback: str | None = None
        last_issues: list[str] = ["No JSON object found in the model response."]

        for _attempt in range(2):
            with self._storage.project_lock(project_id):
                snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
                state = self._storage.node_store.load_state(project_id, node_id)
                session = self._load_execution_session(
                    project_id=project_id,
                    node_id=node_id,
                    node=node,
                    workspace_root=workspace_root,
                )
                thread_id = session.get("thread_id")
                if not isinstance(thread_id, str) or not thread_id.strip():
                    raise PlanExecuteNotAllowed("Execution thread is not available for planning.")
                prompt = build_plan_turn_prompt(
                    self._build_plan_turn_context(project_id, snapshot, node, state, session),
                    user_message=user_message,
                    retry_feedback=retry_feedback,
                )
            response = self._client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=int(session.get("config", {}).get("timeout_sec", 120)),
                cwd=str(session.get("config", {}).get("cwd") or workspace_root or ""),
                writable_roots=[],
            )
            payload = parse_plan_turn_response(str(response.get("stdout") or ""))
            issues = plan_turn_issues(payload)
            if not issues and payload is not None:
                return normalize_plan_turn_payload(payload)
            last_issues = issues
            retry_feedback = build_plan_turn_retry_feedback(issues)

        raise PlanExecuteInvalidResponse(last_issues)

    def _run_execute_turn(self, project_id: str, node_id: str) -> dict[str, str]:
        retry_feedback: str | None = None
        last_issues: list[str] = ["No JSON object found in the model response."]

        for _attempt in range(2):
            with self._storage.project_lock(project_id):
                snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
                state = self._storage.node_store.load_state(project_id, node_id)
                session = self._load_execution_session(
                    project_id=project_id,
                    node_id=node_id,
                    node=node,
                    workspace_root=workspace_root,
                )
                thread_id = session.get("thread_id")
                if not isinstance(thread_id, str) or not thread_id.strip():
                    raise PlanExecuteNotAllowed("Execution thread is not available for this node.")
                prompt = build_execute_prompt(
                    self._build_execute_context(project_id, snapshot, node, state, session),
                    retry_feedback,
                )
            response = self._client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=int(session.get("config", {}).get("timeout_sec", 120)),
                cwd=str(session.get("config", {}).get("cwd") or workspace_root or ""),
                writable_roots=list(session.get("config", {}).get("writable_roots", [])),
            )
            payload = parse_execute_response(str(response.get("stdout") or ""))
            issues = execute_issues(payload)
            if not issues and payload is not None:
                return normalize_execute_payload(payload)
            last_issues = issues
            retry_feedback = build_execute_retry_feedback(issues)

        raise PlanExecuteInvalidResponse(last_issues)

    def _start_background_plan_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        user_message: str,
        prior_plan_status: str,
        handle: AgentOperationHandle | None,
    ) -> None:
        threading.Thread(
            target=self._run_background_plan_turn,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message_id,
                "user_message": user_message,
                "prior_plan_status": prior_plan_status,
                "handle": handle,
            },
            daemon=True,
        ).start()

    def _run_background_plan_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        user_message: str,
        prior_plan_status: str,
        handle: AgentOperationHandle | None,
    ) -> None:
        try:
            self._ensure_execution_thread(project_id, node_id)
            result = self._run_plan_turn_streaming(
                project_id=project_id,
                node_id=node_id,
                user_message=user_message,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                handle=handle,
            )
        except Exception as exc:
            self._mark_turn_failed(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                error_message=str(exc),
            )
            self._restore_plan_ready_state(
                project_id,
                node_id,
                plan_status="ready" if prior_plan_status == "ready" else "none",
                run_status="failed",
                failure_operation="plan",
                failure_message=str(exc),
            )
            if handle is not None and self._agent_operation_service is not None:
                self._agent_operation_service.publish_failed(
                    handle,
                    stage="failed",
                    message=str(exc),
                )
        else:
            try:
                self._commit_plan_turn_result(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    result=result,
                )
            except Exception as exc:
                self._mark_turn_failed(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    error_message=str(exc),
                )
                self._restore_plan_ready_state(
                    project_id,
                    node_id,
                    plan_status="ready" if prior_plan_status == "ready" else "none",
                    run_status="failed",
                    failure_operation="plan",
                    failure_message=str(exc),
                )
                if handle is not None and self._agent_operation_service is not None:
                    self._agent_operation_service.publish_failed(
                        handle,
                        stage="failed",
                        message=str(exc),
                    )
            else:
                if handle is not None and self._agent_operation_service is not None:
                    if result["structured_result"]["kind"] == "requires_spec_update":
                        self._agent_operation_service.publish_progress(
                            handle,
                            stage="requires_spec_update",
                            message="Planner found a contract change that needs Spec review.",
                        )
                    else:
                        self._agent_operation_service.publish_completed(
                            handle,
                            stage="completed",
                            message="Plan is ready.",
                        )
        finally:
            self._finish_agent_operation(handle)
            self._clear_live_turn(project_id, node_id, turn_id)

    def _run_plan_turn_streaming(
        self,
        *,
        project_id: str,
        node_id: str,
        user_message: str,
        turn_id: str,
        assistant_message_id: str,
        handle: AgentOperationHandle | None,
    ) -> dict[str, Any]:
        retry_feedback: str | None = None
        last_issues: list[str] = ["No JSON object found in the model response."]

        for attempt in range(2):
            with self._storage.project_lock(project_id):
                snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
                state = self._storage.node_store.load_state(project_id, node_id)
                session = self._load_execution_session(
                    project_id=project_id,
                    node_id=node_id,
                    node=node,
                    workspace_root=workspace_root,
                )
                thread_id = session.get("thread_id")
                if not isinstance(thread_id, str) or not thread_id.strip():
                    raise PlanExecuteNotAllowed("Execution thread is not available for planning.")
                config = copy.deepcopy(session.get("config", {}))
                prompt = build_plan_turn_prompt(
                    self._build_plan_turn_context(project_id, snapshot, node, state, session),
                    user_message=user_message,
                    retry_feedback=retry_feedback,
                )
            response = self._client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=int(config.get("timeout_sec", 120)),
                cwd=str(config.get("cwd") or workspace_root or ""),
                writable_roots=[],
                on_request_user_input=lambda payload: self._handle_plan_input_requested(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    payload=payload,
                    handle=handle,
                ),
                on_request_resolved=lambda payload: self._handle_plan_runtime_request_resolved(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    payload=payload,
                ),
                on_thread_status=lambda payload: self._handle_plan_runtime_status_changed(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    payload=payload,
                ),
                output_schema=plan_turn_output_schema(),
            )
            raw_output = str(response.get("stdout") or "")
            payload = parse_plan_turn_response(raw_output)
            issues = plan_turn_issues(payload)
            if not issues and payload is not None:
                return {
                    "structured_result": normalize_plan_turn_payload(payload),
                    "bound_turn_id": str(response.get("turn_id") or turn_id),
                    "turn_status": str(response.get("turn_status") or ""),
                    "final_plan_item": copy.deepcopy(response.get("final_plan_item")),
                    "runtime_request_ids": list(response.get("runtime_request_ids") or []),
                }
            last_issues = issues
            retry_feedback = build_plan_turn_retry_feedback(issues)

        raise PlanExecuteInvalidResponse(last_issues)

    def _handle_plan_input_requested(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        payload: dict[str, Any],
        handle: AgentOperationHandle | None,
    ) -> None:
        request_record = self._normalize_runtime_request_payload(
            payload,
            node_id=node_id,
        )
        if request_record is None:
            return
        audit_message = self._make_runtime_request_assistant_message(request_record)
        with self._storage.project_lock(project_id):
            _, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            session["runtime_request_registry"] = self._upsert_runtime_request_registry(
                session.get("runtime_request_registry", []),
                request_record,
            )
            session["pending_input_request"] = copy.deepcopy(request_record)
            state["plan_status"] = "waiting_on_input"
            state["run_status"] = "planning"
            self._insert_message_before_active_assistant(
                session,
                assistant_message_id,
                audit_message,
            )
            wait_message = self._find_message(session, assistant_message_id)
            if wait_message is not None:
                wait_message["content"] = "Waiting for your answer..."
                wait_message["status"] = "streaming"
                wait_message["updated_at"] = iso_now()
            self._storage.node_store.save_state(project_id, node_id, state)
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "plan_input_requested",
                    "request": copy.deepcopy(request_record),
                    "assistant_message": copy.deepcopy(audit_message),
                    "waiting_message_id": assistant_message_id,
                },
            )
        self._event_broker.publish(project_id, node_id, event)
        if handle is not None and self._agent_operation_service is not None:
            self._agent_operation_service.publish_progress(
                handle,
                stage="waiting_on_input",
                message="Planner is waiting on your answer.",
            )

    def _handle_plan_runtime_request_resolved(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        payload: dict[str, Any],
    ) -> None:
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return
        with self._storage.project_lock(project_id):
            _, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            registry = self._mark_runtime_request_status(
                session.get("runtime_request_registry", []),
                request_id=request_id,
                status=str(payload.get("status") or "stale"),
                resolved_at=str(payload.get("resolved_at") or iso_now()),
                answer_payload=None,
            )
            session["runtime_request_registry"] = registry
            pending_request = session.get("pending_input_request")
            if (
                isinstance(pending_request, dict)
                and str(pending_request.get("request_id") or "") == request_id
                and str(payload.get("status") or "") == "stale"
            ):
                session["pending_input_request"] = None
                state["plan_status"] = "none"
                state["run_status"] = "idle"
            self._storage.node_store.save_state(project_id, node_id, state)
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "plan_input_resolved",
                    "request_id": request_id,
                    "status": str(payload.get("status") or "stale"),
                    "resolved_at": str(payload.get("resolved_at") or iso_now()),
                    "user_message": None,
                },
            )
        self._event_broker.publish(project_id, node_id, event)

    def _handle_plan_runtime_status_changed(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        payload: dict[str, Any],
    ) -> None:
        status = payload.get("status")
        if not isinstance(status, dict):
            return
        with self._storage.project_lock(project_id):
            _, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            session["runtime_thread_status"] = copy.deepcopy(status)
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "plan_runtime_status_changed",
                    "thread_status": copy.deepcopy(status),
                },
            )
        self._event_broker.publish(project_id, node_id, event)

    def _build_plan_turn_context(
        self,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        state: dict[str, Any],
        session: dict[str, Any],
    ) -> dict[str, Any]:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            project = {}
        return {
            "project_name": str(project.get("name") or ""),
            "project_root_goal": str(project.get("root_goal") or ""),
            "node_id": str(node.get("node_id") or ""),
            "node_hierarchical_number": str(node.get("hierarchical_number") or ""),
            "task": self._storage.node_store.load_task(project_id, str(node.get("node_id") or "")),
            "brief": self._storage.node_store.load_brief(project_id, str(node.get("node_id") or "")),
            "spec": self._storage.node_store.load_spec(project_id, str(node.get("node_id") or "")),
            "brief_version": int(state.get("brief_version", 0) or 0),
            "spec_version": int(state.get("active_spec_version", 0) or 0),
            "plan_input_version": int(state.get("active_plan_input_version", 0) or 0),
            "plan_status": str(state.get("plan_status") or "none"),
            "run_status": str(state.get("run_status") or "idle"),
            "pending_input_request": copy.deepcopy(session.get("pending_input_request")),
            "chat_config": {
                "access_mode": session.get("config", {}).get("access_mode"),
                "cwd": session.get("config", {}).get("cwd"),
                "writable_roots": session.get("config", {}).get("writable_roots", []),
                "timeout_sec": session.get("config", {}).get("timeout_sec"),
            },
        }

    def _build_execute_context(
        self,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        state: dict[str, Any],
        session: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._build_plan_turn_context(project_id, snapshot, node, state, session)
        context["plan"] = self._storage.node_store.load_plan(project_id, str(node.get("node_id") or ""))
        return context

    def _normalize_runtime_request_payload(
        self,
        payload: dict[str, Any],
        *,
        node_id: str,
    ) -> dict[str, Any] | None:
        request_id = str(payload.get("request_id") or "").strip()
        thread_id = str(payload.get("thread_id") or "").strip()
        turn_id = str(payload.get("turn_id") or "").strip()
        item_id = str(payload.get("item_id") or "").strip()
        questions_raw = payload.get("questions")
        if not request_id or not thread_id or not turn_id or not item_id or not isinstance(questions_raw, list):
            return None
        questions: list[dict[str, Any]] = []
        for item in questions_raw:
            if not isinstance(item, dict):
                continue
            header = str(item.get("header") or "").strip()
            question = str(item.get("question") or "").strip()
            question_id = str(item.get("id") or "").strip()
            options_raw = item.get("options")
            options: list[dict[str, str]] | None = None
            if isinstance(options_raw, list):
                normalized_options: list[dict[str, str]] = []
                for option in options_raw:
                    if not isinstance(option, dict):
                        continue
                    label = str(option.get("label") or "").strip()
                    description = str(option.get("description") or "").strip()
                    if label:
                        normalized_options.append(
                            {
                                "label": label,
                                "description": description,
                            }
                        )
                options = normalized_options if normalized_options else []
            if not question_id or not header or not question:
                continue
            questions.append(
                {
                    "id": question_id,
                    "header": header,
                    "question": question,
                    "is_other": bool(item.get("isOther")),
                    "is_secret": bool(item.get("isSecret")),
                    "options": options,
                }
            )
        if not questions:
            return None
        return {
            "request_id": request_id,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "node_id": node_id,
            "item_id": item_id,
            "questions": questions,
            "created_at": str(payload.get("created_at") or iso_now()),
            "resolved_at": str(payload.get("resolved_at") or "") or None,
            "status": str(payload.get("status") or "pending"),
            "answer_payload": copy.deepcopy(payload.get("answer_payload")) if payload.get("answer_payload") else None,
        }

    def _make_runtime_request_assistant_message(self, request: dict[str, Any]) -> dict[str, Any]:
        now = iso_now()
        lines = ["Planner needs one short clarification before it can finish the plan.", ""]
        for question in list(request.get("questions") or []):
            if not isinstance(question, dict):
                continue
            lines.append(str(question.get("header") or "").strip())
            lines.append(str(question.get("question") or "").strip())
            options = question.get("options")
            if isinstance(options, list) and options:
                for option in options:
                    if not isinstance(option, dict):
                        continue
                    label = str(option.get("label") or "").strip()
                    description = str(option.get("description") or "").strip()
                    if not label:
                        continue
                    if description:
                        lines.append(f"- {label}: {description}")
                    else:
                        lines.append(f"- {label}")
            lines.append("")
        return {
            "message_id": new_id("msg"),
            "role": "assistant",
            "content": "\n".join(lines).strip(),
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "error": None,
        }

    def _make_runtime_request_user_message(
        self,
        request: dict[str, Any],
        answer_payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = iso_now()
        answer_map = answer_payload.get("answers") if isinstance(answer_payload, dict) else {}
        lines = ["Planner input resolved.", ""]
        for question in list(request.get("questions") or []):
            if not isinstance(question, dict):
                continue
            question_id = str(question.get("id") or "").strip()
            if not question_id:
                continue
            lines.append(str(question.get("header") or "").strip())
            answer_entry = answer_map.get(question_id) if isinstance(answer_map, dict) else None
            answers = answer_entry.get("answers") if isinstance(answer_entry, dict) else None
            if isinstance(answers, list) and answers:
                lines.extend(str(item or "").strip() for item in answers if str(item or "").strip())
            else:
                lines.append("(no answer text)")
            lines.append("")
        return {
            "message_id": new_id("msg"),
            "role": "user",
            "content": "\n".join(lines).strip(),
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "error": None,
        }

    def _upsert_runtime_request_registry(
        self,
        registry: list[dict[str, Any]],
        request: dict[str, Any],
    ) -> list[dict[str, Any]]:
        next_registry: list[dict[str, Any]] = []
        matched = False
        request_id = str(request.get("request_id") or "").strip()
        for item in registry:
            if isinstance(item, dict) and str(item.get("request_id") or "") == request_id:
                next_registry.append(copy.deepcopy(request))
                matched = True
            elif isinstance(item, dict):
                next_registry.append(copy.deepcopy(item))
        if not matched:
            next_registry.append(copy.deepcopy(request))
        return next_registry

    def _mark_runtime_request_status(
        self,
        registry: list[dict[str, Any]],
        *,
        request_id: str,
        status: str,
        resolved_at: str,
        answer_payload: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        next_registry: list[dict[str, Any]] = []
        for item in registry:
            if not isinstance(item, dict):
                continue
            next_item = copy.deepcopy(item)
            if str(next_item.get("request_id") or "") == request_id:
                next_item["status"] = status
                next_item["resolved_at"] = resolved_at
                if answer_payload is not None:
                    next_item["answer_payload"] = copy.deepcopy(answer_payload)
            next_registry.append(next_item)
        return next_registry

    def _find_runtime_request(
        self,
        registry: list[dict[str, Any]],
        request_id: str,
    ) -> dict[str, Any] | None:
        for item in registry:
            if isinstance(item, dict) and str(item.get("request_id") or "") == request_id:
                return copy.deepcopy(item)
        return None

    def _insert_message_before_active_assistant(
        self,
        session: dict[str, Any],
        assistant_message_id: str,
        message: dict[str, Any],
    ) -> None:
        messages = session.get("messages", [])
        if not isinstance(messages, list):
            messages = []
            session["messages"] = messages
        insert_at = len(messages)
        for index, existing in enumerate(messages):
            if isinstance(existing, dict) and str(existing.get("message_id") or "") == assistant_message_id:
                insert_at = index
                break
        messages.insert(insert_at, copy.deepcopy(message))

    def _render_plan_completion_message(self, structured_result: dict[str, Any]) -> str:
        kind = str(structured_result.get("kind") or "").strip()
        if kind == "requires_spec_update":
            change_summary = str(structured_result.get("change_summary") or "").strip()
            next_step = str(structured_result.get("recommended_next_step") or "").strip()
            if change_summary and next_step:
                return f"{change_summary}\n\nNext step: {next_step}"
            return change_summary or next_step
        return str(structured_result.get("assistant_summary") or "").strip()

    def _structured_result_hash(self, structured_result: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(structured_result, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _resolved_request_ids_for_turn(self, session: dict[str, Any], turn_id: str) -> list[str]:
        resolved_ids: list[str] = []
        for item in list(session.get("runtime_request_registry", [])):
            if not isinstance(item, dict):
                continue
            if str(item.get("turn_id") or "") != turn_id:
                continue
            if str(item.get("status") or "") != "resolved":
                continue
            request_id = str(item.get("request_id") or "").strip()
            if request_id and request_id not in resolved_ids:
                resolved_ids.append(request_id)
        return resolved_ids

    def _commit_plan_turn_result(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        result: dict[str, Any],
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return

            structured_result = dict(result.get("structured_result") or {})
            kind = str(structured_result.get("kind") or "").strip()
            assistant_summary = self._render_plan_completion_message(structured_result)
            message["content"] = assistant_summary
            clear_last_agent_failure(state)
            final_plan_item = result.get("final_plan_item")
            bound_turn_id = str(result.get("bound_turn_id") or turn_id)
            if kind == "plan_ready":
                if not isinstance(final_plan_item, dict):
                    raise PlanExecuteInvalidResponse(
                        ["plan_ready requires a completed final plan item from item/completed."]
                    )
                final_plan_turn_id = str(final_plan_item.get("turn_id") or "")
                final_plan_text = str(final_plan_item.get("text") or "").strip()
                final_plan_item_id = str(final_plan_item.get("id") or "").strip()
                if final_plan_turn_id != bound_turn_id:
                    raise PlanExecuteInvalidResponse(
                        ["final_plan_item.turn_id must match the bound turn id before binding."]
                    )
                if not final_plan_text or not final_plan_item_id:
                    raise PlanExecuteInvalidResponse(
                        ["plan_ready requires a non-empty final plan item id and text."]
                    )
                self._storage.node_store.save_plan(
                    project_id,
                    node_id,
                    {"content": final_plan_text},
                )
                state["active_plan_version"] = int(state.get("active_plan_version", 0) or 0) + 1
                state["bound_plan_spec_version"] = int(state.get("active_spec_version", 0) or 0)
                state["bound_plan_brief_version"] = int(state.get("brief_version", 0) or 0)
                state["bound_plan_input_version"] = int(state.get("active_plan_input_version", 0) or 0)
                state["bound_turn_id"] = bound_turn_id
                state["final_plan_item_id"] = final_plan_item_id
                state["structured_result_hash"] = self._structured_result_hash(structured_result)
                state["resolved_request_ids"] = self._resolved_request_ids_for_turn(session, bound_turn_id)
                state["plan_status"] = "ready"
                state["run_status"] = "idle"
                state["spec_update_change_summary"] = ""
                state["spec_update_changed_contract_axes"] = []
                state["spec_update_recommended_next_step"] = ""
                self._set_node_phase(node, state, "ready_for_execution")
            elif kind == "requires_spec_update":
                self._storage.node_store.save_plan(project_id, node_id, {"content": ""})
                state["active_plan_version"] = 0
                state["bound_plan_spec_version"] = 0
                state["bound_plan_brief_version"] = 0
                state["bound_plan_input_version"] = 0
                state["bound_turn_id"] = ""
                state["final_plan_item_id"] = ""
                state["structured_result_hash"] = ""
                state["resolved_request_ids"] = []
                state["plan_status"] = "none"
                state["run_status"] = "idle"
                state["spec_update_change_summary"] = str(structured_result.get("change_summary") or "").strip()
                state["spec_update_changed_contract_axes"] = list(
                    structured_result.get("changed_contract_axes") or []
                )
                state["spec_update_recommended_next_step"] = str(
                    structured_result.get("recommended_next_step") or ""
                ).strip()
                self._set_node_phase(node, state, "blocked_on_spec_question")
            else:
                raise PlanExecuteInvalidResponse(["Planner returned an unknown final kind."])

            message["status"] = "completed"
            message["error"] = None
            message["updated_at"] = iso_now()
            session["active_turn_id"] = None
            session["active_assistant_message_id"] = None
            session["status"] = "idle"
            session["pending_input_request"] = None
            self._storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "assistant_completed",
                    "message_id": assistant_message_id,
                    "content": str(message["content"]),
                    "updated_at": str(message["updated_at"]),
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _commit_execute_result(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        result: dict[str, str],
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return

            summary = str(result.get("assistant_summary") or "").strip()
            message["content"] = summary
            if result["status"] == "failed":
                state["plan_status"] = "abandoned"
                state["run_status"] = "failed"
                self._set_node_phase(node, state, "ready_for_execution")
            else:
                state["plan_status"] = "completed"
                state["run_status"] = "completed"
                self._set_node_phase(node, state, "executing")

            message["status"] = "completed"
            message["error"] = None
            message["updated_at"] = iso_now()
            session["active_turn_id"] = None
            session["status"] = "idle"
            self._storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "assistant_completed",
                    "message_id": assistant_message_id,
                    "content": str(message["content"]),
                    "updated_at": str(message["updated_at"]),
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _restore_plan_ready_state(
        self,
        project_id: str,
        node_id: str,
        *,
        run_status: str = "idle",
        plan_status: str | None = None,
        failure_operation: str | None = None,
        failure_message: str | None = None,
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_node_context(project_id, node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            if str(state.get("phase") or "") == "executing":
                self._set_node_phase(node, state, "ready_for_execution")
            state["run_status"] = run_status
            if plan_status is not None:
                state["plan_status"] = plan_status
            if failure_operation and failure_message:
                set_last_agent_failure(
                    state,
                    operation=failure_operation,
                    message=failure_message,
                )
            self._storage.node_store.save_state(project_id, node_id, state)
            self._persist_snapshot(project_id, snapshot)

    def _set_node_phase(self, node: dict[str, Any], state: dict[str, Any], phase: str) -> None:
        node["phase"] = phase
        state["phase"] = phase

    def _start_agent_operation(
        self,
        project_id: str,
        node_id: str,
        *,
        operation: str,
    ) -> AgentOperationHandle | None:
        if self._agent_operation_service is None:
            return None
        try:
            return self._agent_operation_service.start_operation(project_id, node_id, operation)
        except RuntimeError as exc:
            raise PlanExecuteNotAllowed(str(exc)) from exc

    def _finish_agent_operation(self, handle: AgentOperationHandle | None) -> None:
        if handle is not None and self._agent_operation_service is not None:
            self._agent_operation_service.finish_operation(handle)

    def _start_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        prompt: str,
        thread_id: str | None,
        config: dict[str, Any],
    ) -> None:
        threading.Thread(
            target=self._run_background_turn,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message_id,
                "prompt": prompt,
                "thread_id": thread_id,
                "config": config,
            },
            daemon=True,
        ).start()

    def _run_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        prompt: str,
        thread_id: str | None,
        config: dict[str, Any],
    ) -> None:
        writable_roots = (
            list(config.get("writable_roots", [])) if config.get("access_mode") == "project_write" else []
        )
        try:
            response = self._client.send_prompt_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=int(config.get("timeout_sec", 120)),
                cwd=str(config.get("cwd") or ""),
                writable_roots=writable_roots,
                on_delta=lambda delta: self._append_assistant_delta(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    delta=delta,
                ),
            )
        except Exception as exc:
            self._mark_turn_failed(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                error_message=str(exc),
            )
        else:
            self._mark_turn_completed(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=str(response.get("stdout", "")),
                thread_id=response.get("thread_id"),
            )
        finally:
            self._clear_live_turn(project_id, node_id, turn_id)

    def _append_assistant_delta(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        delta: str,
    ) -> None:
        if not delta:
            return
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return
            next_content = f"{message.get('content', '')}{delta}"
        self._set_assistant_stream_content(
            project_id=project_id,
            node_id=node_id,
            turn_id=turn_id,
            assistant_message_id=assistant_message_id,
            content=next_content,
            delta=delta,
        )

    def _set_assistant_stream_content(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        content: str,
        delta: str,
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return
            message["content"] = content
            message["status"] = "streaming"
            message["updated_at"] = iso_now()
            content = str(message["content"])
            updated_at = str(message["updated_at"])
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "assistant_delta",
                    "message_id": assistant_message_id,
                    "delta": delta,
                    "content": content,
                    "updated_at": updated_at,
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _mark_turn_completed(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        content: str,
        thread_id: Any,
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return
            final_content = content or str(message.get("content", ""))
            message["content"] = final_content
            message["status"] = "completed"
            message["error"] = None
            message["updated_at"] = iso_now()
            session["active_turn_id"] = None
            session["active_assistant_message_id"] = None
            session["status"] = "idle"
            if isinstance(thread_id, str) and thread_id.strip():
                session["thread_id"] = thread_id.strip()
                if not isinstance(node.get("execution_thread_id"), str) or not node.get("execution_thread_id", "").strip():
                    self._sync_node_state_cache(
                        project_id,
                        node_id,
                        node,
                        execution_thread_id=thread_id.strip(),
                    )
                    self._persist_snapshot(project_id, snapshot)
            updated_at = str(message["updated_at"])
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "assistant_completed",
                    "message_id": assistant_message_id,
                    "content": final_content,
                    "updated_at": updated_at,
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _mark_turn_failed(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        error_message: str,
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            session = self._load_execution_session(
                project_id=project_id,
                node_id=node_id,
                node=node,
                workspace_root=workspace_root,
            )
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return
            message["status"] = "error"
            message["error"] = error_message
            message["updated_at"] = iso_now()
            session["active_turn_id"] = None
            session["active_assistant_message_id"] = None
            session["status"] = "idle"
            content = str(message.get("content", ""))
            updated_at = str(message["updated_at"])
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "assistant_error",
                    "message_id": assistant_message_id,
                    "content": content,
                    "updated_at": updated_at,
                    "error": error_message,
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _select_raw_execution_session(
        self,
        *,
        thread_state: dict[str, Any],
        chat_state: dict[str, Any],
        node_id: str,
    ) -> Any:
        raw_thread_state = thread_state.get(node_id)
        if isinstance(raw_thread_state, dict):
            execution = raw_thread_state.get("execution")
            if self._has_execution_data(execution):
                return execution
        return chat_state.get(node_id)

    def _has_execution_data(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        return any(
            payload.get(key)
            for key in ("thread_id", "active_turn_id", "config", "messages")
        )

    def _load_execution_session(
        self,
        *,
        project_id: str,
        node_id: str,
        node: dict[str, Any],
        workspace_root: str,
    ) -> dict[str, Any]:
        thread_state = self._storage.thread_store.read_thread_state(project_id)
        chat_state = self._storage.chat_store.read_chat_state(project_id)
        raw_session = self._select_raw_execution_session(
            thread_state=thread_state,
            chat_state=chat_state,
            node_id=node_id,
        )
        session = self._normalize_session(
            project_id=project_id,
            node_id=node_id,
            session=raw_session,
            default_config=self._default_config(workspace_root),
        )
        node_thread_id = node.get("execution_thread_id")
        if isinstance(node_thread_id, str) and node_thread_id.strip() and not session.get("thread_id"):
            session["thread_id"] = node_thread_id.strip()
        session, recovered = self._recover_stale_turn(session)
        if raw_session is None or recovered or raw_session != session:
            self._write_session_state(project_id, node_id, session)
        return session

    def _public_session(self, session: dict[str, Any]) -> dict[str, Any]:
        public_session = copy.deepcopy(session)
        public_session.pop("thread_id", None)
        public_session.pop("plan_message_start_index", None)
        return public_session

    def _default_config(self, workspace_root: str) -> dict[str, Any]:
        return {
            "access_mode": "project_write",
            "cwd": workspace_root,
            "writable_roots": [workspace_root],
            "timeout_sec": 120,
        }

    def _normalize_session(
        self,
        *,
        project_id: str,
        node_id: str,
        session: Any,
        default_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = session if isinstance(session, dict) else {}
        if default_config is None:
            config = self._normalize_recovered_config(payload.get("config"))
        else:
            try:
                config = self._normalize_config(
                    payload.get("config", {}),
                    workspace_root=default_config["cwd"],
                    fallback=default_config,
                )
            except ValueError:
                config = copy.deepcopy(default_config)

        messages = [
            self._normalize_message(item)
            for item in payload.get("messages", [])
            if isinstance(item, dict)
        ]
        thread_id = payload.get("thread_id")
        active_turn_id = payload.get("active_turn_id")
        event_seq = payload.get("event_seq", 0)
        try:
            normalized_event_seq = max(0, int(event_seq))
        except (TypeError, ValueError):
            normalized_event_seq = 0
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"active", "idle"}:
            status = "active" if active_turn_id else "idle"
        mode = str(payload.get("mode") or "").strip().lower()
        if mode not in {"plan", "execute"}:
            mode = "idle"
        try:
            plan_message_start_index = max(0, int(payload.get("plan_message_start_index", 0) or 0))
        except (TypeError, ValueError):
            plan_message_start_index = 0
        runtime_thread_status = copy.deepcopy(payload.get("runtime_thread_status"))
        runtime_request_registry = [
            self._normalize_runtime_request_session_item(item)
            for item in payload.get("runtime_request_registry", [])
            if isinstance(item, dict)
        ]
        pending_input_request = payload.get("pending_input_request")
        normalized_pending_input_request = (
            self._normalize_runtime_request_session_item(pending_input_request)
            if isinstance(pending_input_request, dict)
            else None
        )
        active_assistant_message_id = payload.get("active_assistant_message_id")
        return {
            "project_id": project_id,
            "node_id": node_id,
            "thread_id": thread_id if isinstance(thread_id, str) and thread_id.strip() else None,
            "active_turn_id": (
                active_turn_id if isinstance(active_turn_id, str) and active_turn_id.strip() else None
            ),
            "event_seq": normalized_event_seq,
            "status": status,
            "mode": mode,
            "plan_message_start_index": plan_message_start_index,
            "active_assistant_message_id": (
                active_assistant_message_id
                if isinstance(active_assistant_message_id, str) and active_assistant_message_id.strip()
                else None
            ),
            "config": config,
            "messages": messages,
            "runtime_thread_status": runtime_thread_status if isinstance(runtime_thread_status, dict) else None,
            "runtime_request_registry": runtime_request_registry,
            "pending_input_request": normalized_pending_input_request,
        }

    def _recover_stale_turn(self, session: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        active_turn_id = session.get("active_turn_id")
        if not active_turn_id:
            return session, False
        turn_key = (
            str(session.get("project_id") or ""),
            str(session.get("node_id") or ""),
            str(active_turn_id),
        )
        if self._is_live_turn(turn_key):
            return session, False
        session["active_turn_id"] = None
        session["active_assistant_message_id"] = None
        session["status"] = "idle"
        if isinstance(session.get("pending_input_request"), dict):
            request_id = str(session["pending_input_request"].get("request_id") or "").strip()
            session["pending_input_request"] = None
            session["runtime_request_registry"] = self._mark_runtime_request_status(
                session.get("runtime_request_registry", []),
                request_id=request_id,
                status="stale",
                resolved_at=iso_now(),
                answer_payload=None,
            )
        updated_at = iso_now()
        for message in reversed(session.get("messages", [])):
            if (
                isinstance(message, dict)
                and message.get("role") == "assistant"
                and message.get("status") in {"pending", "streaming"}
            ):
                message["status"] = "error"
                message["error"] = STALE_TURN_ERROR
                message["updated_at"] = updated_at
                break
        return session, True

    def _reconcile_plan_runtime_requests(self, session: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        pending_request = session.get("pending_input_request")
        if not isinstance(pending_request, dict):
            return session, False
        thread_id = str(pending_request.get("thread_id") or "").strip()
        turn_id = str(pending_request.get("turn_id") or "").strip()
        request_id = str(pending_request.get("request_id") or "").strip()
        if not thread_id or not turn_id or not request_id:
            session["pending_input_request"] = None
            return session, True

        try:
            loaded_response = self._client.list_loaded_threads(timeout_sec=10, limit=200)
            loaded_threads = {
                str(item).strip()
                for item in list(loaded_response.get("data", []))
                if isinstance(item, str) and item.strip()
            }
        except Exception:
            return session, False

        if thread_id in loaded_threads:
            return session, False

        thread_status: dict[str, Any] | None = None
        try:
            read_response = self._client.read_thread(thread_id, include_turns=False, timeout_sec=10)
            thread = read_response.get("thread", {})
            if isinstance(thread, dict):
                status = thread.get("status")
                thread_status = copy.deepcopy(status) if isinstance(status, dict) else None
        except Exception:
            thread_status = None

        session["runtime_thread_status"] = thread_status
        session["pending_input_request"] = None
        session["runtime_request_registry"] = self._mark_runtime_request_status(
            session.get("runtime_request_registry", []),
            request_id=request_id,
            status="stale",
            resolved_at=iso_now(),
            answer_payload=None,
        )
        return session, True

    def _normalize_recovered_config(self, payload: Any) -> dict[str, Any]:
        raw = payload if isinstance(payload, dict) else {}
        cwd_raw = raw.get("cwd")
        cwd = str(cwd_raw).strip() if isinstance(cwd_raw, str) and cwd_raw.strip() else str(Path.home())
        writable_roots = [
            str(item).strip()
            for item in raw.get("writable_roots", [])
            if isinstance(item, str) and str(item).strip()
        ]
        try:
            timeout_sec = max(10, min(600, int(raw.get("timeout_sec", 120))))
        except (TypeError, ValueError):
            timeout_sec = 120
        access_mode = "project_write" if raw.get("access_mode") == "project_write" else "read_only"
        if access_mode == "project_write" and cwd not in writable_roots:
            writable_roots.insert(0, cwd)
        if access_mode == "read_only":
            writable_roots = []
        return {
            "access_mode": access_mode,
            "cwd": cwd,
            "writable_roots": writable_roots,
            "timeout_sec": timeout_sec,
        }

    def _normalize_message(self, message: dict[str, Any]) -> dict[str, Any]:
        created_at = str(message.get("created_at") or iso_now())
        updated_at = str(message.get("updated_at") or created_at)
        error = message.get("error")
        return {
            "message_id": str(message.get("message_id") or new_id("msg")),
            "role": "assistant" if str(message.get("role")) == "assistant" else "user",
            "content": str(message.get("content") or ""),
            "status": self._normalize_message_status(message.get("status")),
            "created_at": created_at,
            "updated_at": updated_at,
            "error": str(error) if error is not None and str(error).strip() else None,
        }

    def _normalize_runtime_request_session_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._normalize_runtime_request_payload(payload, node_id=str(payload.get("node_id") or ""))
        if request is None:
            return {
                "request_id": str(payload.get("request_id") or new_id("req")),
                "thread_id": str(payload.get("thread_id") or ""),
                "turn_id": str(payload.get("turn_id") or ""),
                "node_id": str(payload.get("node_id") or ""),
                "item_id": str(payload.get("item_id") or ""),
                "questions": [],
                "created_at": str(payload.get("created_at") or iso_now()),
                "resolved_at": str(payload.get("resolved_at") or "") or None,
                "status": str(payload.get("status") or "stale"),
                "answer_payload": copy.deepcopy(payload.get("answer_payload"))
                if payload.get("answer_payload")
                else None,
            }
        return request

    def _normalize_message_status(self, raw_status: Any) -> str:
        status = str(raw_status or "").strip().lower()
        if status in {"pending", "streaming", "completed", "error"}:
            return status
        return "completed"

    def _normalize_config(
        self,
        payload: Any,
        *,
        workspace_root: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        raw = payload if isinstance(payload, dict) else {}
        access_mode = raw.get("access_mode", fallback.get("access_mode"))
        if access_mode not in {"project_write", "read_only"}:
            raise ValueError("access_mode must be 'project_write' or 'read_only'")

        cwd = self._resolve_config_path(
            raw.get("cwd", fallback.get("cwd")),
            workspace_root=workspace_root,
            field_name="cwd",
        )

        raw_writable_roots = raw.get("writable_roots", fallback.get("writable_roots", []))
        if raw_writable_roots is None:
            raw_writable_roots = []
        if not isinstance(raw_writable_roots, list):
            raise ValueError("writable_roots must be a list of directory paths")
        writable_roots: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(raw_writable_roots):
            resolved = self._resolve_config_path(
                item,
                workspace_root=workspace_root,
                field_name=f"writable_roots[{index}]",
            )
            if resolved in seen:
                continue
            seen.add(resolved)
            writable_roots.append(resolved)
        if access_mode == "project_write":
            if not writable_roots:
                writable_roots = [cwd]
            elif cwd not in seen:
                writable_roots.insert(0, cwd)
        else:
            writable_roots = []

        timeout_raw = raw.get("timeout_sec", fallback.get("timeout_sec", 120))
        try:
            timeout_sec = int(timeout_raw)
        except (TypeError, ValueError):
            raise ValueError("timeout_sec must be an integer") from None
        timeout_sec = max(10, min(600, timeout_sec))

        return {
            "access_mode": access_mode,
            "cwd": cwd,
            "writable_roots": writable_roots,
            "timeout_sec": timeout_sec,
        }

    def _resolve_config_path(
        self,
        raw_value: Any,
        *,
        workspace_root: str,
        field_name: str,
    ) -> str:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"{field_name} is required")
        workspace_path = Path(workspace_root).expanduser().resolve()
        candidate = Path(raw_value.strip()).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_path / candidate
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"{field_name} could not be resolved: {exc}") from exc
        if not resolved.exists():
            raise ValueError(f"{field_name} does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"{field_name} is not a directory: {resolved}")
        try:
            resolved.relative_to(workspace_path)
        except ValueError as exc:
            raise ValueError(f"{field_name} must stay under project workspace_root") from exc
        return str(resolved)

    def _build_prompt(
        self,
        *,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        workspace_root: str,
        config: dict[str, Any],
        user_message: str,
    ) -> str:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            project = {}
        fields = load_task_prompt_fields(
            self._storage.node_store,
            project_id,
            str(node.get("node_id") or ""),
        )
        hidden_context = {
            "project_name": str(project.get("name") or ""),
            "project_root_goal": str(project.get("root_goal") or ""),
            "workspace_root": workspace_root,
            "node_id": str(node.get("node_id") or ""),
            "node_title": fields["title"],
            "node_description": fields["description"],
            "node_hierarchical_number": str(node.get("hierarchical_number") or ""),
            "brief": self._storage.node_store.load_brief(project_id, str(node.get("node_id") or "")),
            "spec": self._storage.node_store.load_spec(project_id, str(node.get("node_id") or "")),
            "chat_config": {
                "access_mode": config.get("access_mode"),
                "cwd": config.get("cwd"),
                "writable_roots": config.get("writable_roots", []),
                "timeout_sec": config.get("timeout_sec"),
            },
        }
        return (
            "You are the PlanningTree node execution assistant.\n"
            "Work only from the current node context and workspace settings below.\n"
            "Use the Spec as the governing contract. Use the Brief only as locked context.\n"
            "Do not mention hidden metadata unless the user asks for it.\n\n"
            "Hidden context:\n"
            f"{json.dumps(hidden_context, ensure_ascii=True, indent=2)}\n\n"
            "User message:\n"
            f"{user_message}"
        )

    def _load_node_context(
        self,
        project_id: str,
        node_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        node = self._node_from_snapshot(snapshot, node_id)
        if node is None:
            raise NodeNotFound(node_id)
        workspace_root = self._workspace_root_from_snapshot(snapshot)
        if not workspace_root:
            raise ValueError("project workspace_root is required for chat")
        return snapshot, node, workspace_root

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_workspace_root")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return None
        return workspace_root.strip()

    def _persist_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        now = iso_now()
        snapshot["updated_at"] = now
        snapshot.setdefault("project", {})["updated_at"] = now
        self._storage.project_store.save_snapshot(project_id, snapshot)
        self._storage.project_store.touch_meta(project_id, now)
        return snapshot

    def _node_from_snapshot(self, snapshot: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        tree_state = snapshot.get("tree_state", {})
        if not isinstance(tree_state, dict):
            return None
        node_index = tree_state.get("node_index")
        if isinstance(node_index, dict):
            node = node_index.get(node_id)
            if isinstance(node, dict):
                return node
        registry = tree_state.get("node_registry", [])
        if not isinstance(registry, list):
            return None
        return next(
            (
                item
                for item in registry
                if isinstance(item, dict) and str(item.get("node_id")) == node_id
            ),
            None,
        )

    def _sync_node_state_cache(
        self,
        project_id: str,
        node_id: str,
        node: dict[str, Any],
        *,
        execution_thread_id: str | None = None,
    ) -> None:
        state = self._storage.node_store.load_state(project_id, node_id)
        node["execution_thread_id"] = execution_thread_id if execution_thread_id else None
        state["execution_thread_id"] = execution_thread_id or ""
        self._storage.node_store.save_state(project_id, node_id, state)

    def _persist_session_event(
        self,
        project_id: str,
        node_id: str,
        session: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event_seq = self._advance_event_seq(session)
        self._write_session_state(project_id, node_id, session)
        event = {"event_seq": event_seq, **payload}
        if payload.get("type") == "session_reset":
            event["session"] = self._public_session(session)
        event.pop("thread_id", None)
        return event

    def _write_session_state(self, project_id: str, node_id: str, session: dict[str, Any]) -> None:
        self._storage.thread_store.write_execution_session(project_id, node_id, session)
        chat_state = self._storage.chat_store.read_chat_state(project_id)
        chat_state[node_id] = copy.deepcopy(session)
        self._storage.chat_store.write_chat_state(project_id, chat_state)

    def _advance_event_seq(self, session: dict[str, Any]) -> int:
        try:
            current = int(session.get("event_seq", 0))
        except (TypeError, ValueError):
            current = 0
        next_event_seq = max(0, current) + 1
        session["event_seq"] = next_event_seq
        return next_event_seq

    def _find_message(self, session: dict[str, Any], message_id: str) -> dict[str, Any] | None:
        for item in session.get("messages", []):
            if isinstance(item, dict) and str(item.get("message_id")) == message_id:
                return item
        return None

    def _mark_live_turn(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_turns_lock:
            self._live_turns.add((project_id, node_id, turn_id))

    def _clear_live_turn(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_turns_lock:
            self._live_turns.discard((project_id, node_id, turn_id))

    def _is_live_turn(self, turn_key: tuple[str, str, str]) -> bool:
        with self._live_turns_lock:
            return turn_key in self._live_turns
