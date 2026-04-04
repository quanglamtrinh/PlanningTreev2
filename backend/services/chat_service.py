from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from backend.ai.ask_thread_config import build_ask_planning_thread_config
from backend.ai.chat_prompt_builder import (
    build_chat_prompt,
    build_child_activation_prompt,
    build_local_review_prompt,
    build_package_review_prompt,
)
from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.part_accumulator import PartAccumulator
from backend.errors.app_errors import (
    ChatBackendUnavailable,
    ChatTurnAlreadyActive,
    InvalidRequest,
    NodeNotFound,
    ThreadReadOnly,
)
from backend.services.execution_gating import audit_writable, package_audit_ready
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

if TYPE_CHECKING:
    from backend.services.review_service import ReviewService

logger = logging.getLogger(__name__)

_STALE_TURN_MESSAGE = "Session interrupted - server restarted before response completed."
_DRAFT_FLUSH_INTERVAL_SEC = 0.5
_TASK_THREAD_ROLES = {"ask_planning", "audit", "execution"}
_REVIEW_THREAD_ROLES = {"audit"}
_VALID_THREAD_ROLES = _TASK_THREAD_ROLES | _REVIEW_THREAD_ROLES


class ChatService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient,
        thread_lineage_service: ThreadLineageService,
        chat_event_broker: ChatEventBroker,
        chat_timeout: int,
        max_message_chars: int = 10000,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client
        self._thread_lineage_service = thread_lineage_service
        self._chat_event_broker = chat_event_broker
        self._chat_timeout = int(chat_timeout)
        self._max_message_chars = max_message_chars
        self._live_turns: set[tuple[str, str, str, str]] = set()
        self._live_turns_lock = threading.Lock()
        self._review_service: ReviewService | None = None

    def get_session(
        self, project_id: str, node_id: str, thread_role: str = "ask_planning"
    ) -> dict[str, Any]:
        thread_role = str(thread_role or "").strip()
        node = self._validate_thread_access(project_id, node_id, thread_role)
        with self._storage.project_lock(project_id):
            session = self._load_session_locked(
                project_id,
                node_id,
                thread_role=thread_role,
            )
        if session.get("active_turn_id"):
            return session
        self._bootstrap_task_session_on_read(project_id, node_id, node, thread_role)
        with self._storage.project_lock(project_id):
            session = self._load_session_locked(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            return session

    def create_message(
        self, project_id: str, node_id: str, content: str, thread_role: str = "ask_planning"
    ) -> dict[str, Any]:
        thread_role = str(thread_role or "").strip()
        self._validate_thread_access(project_id, node_id, thread_role)
        self._check_thread_writable(project_id, node_id, thread_role)
        cleaned = content.strip()
        if not cleaned:
            raise InvalidRequest("Message content is required.")
        if len(cleaned) > self._max_message_chars:
            raise InvalidRequest(
                f"Message content exceeds {self._max_message_chars} character limit."
            )

        turn_id = new_id("turn")
        now = iso_now()
        user_message = {
            "message_id": new_id("msg"),
            "role": "user",
            "content": cleaned,
            "status": "completed",
            "error": None,
            "turn_id": turn_id,
            "created_at": now,
            "updated_at": now,
        }
        assistant_message = {
            "message_id": new_id("msg"),
            "role": "assistant",
            "content": "",
            "status": "pending",
            "error": None,
            "turn_id": turn_id,
            "created_at": now,
            "updated_at": now,
        }

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node = self._require_node_from_snapshot(snapshot, node_id)
            session = self._load_session_locked(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            if session.get("active_turn_id"):
                raise ChatTurnAlreadyActive()
            if thread_role == "audit":
                self._maybe_start_local_review_for_audit_write(project_id, node_id)

            session["messages"].append(user_message)
            session["messages"].append(assistant_message)
            session["active_turn_id"] = turn_id
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role=thread_role
            )

            with self._live_turns_lock:
                self._live_turns.add((project_id, node_id, thread_role, turn_id))

        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "message_created",
                "user_message": user_message,
                "assistant_message": assistant_message,
                "active_turn_id": turn_id,
            },
            thread_role=thread_role,
        )

        threading.Thread(
            target=self._run_background_turn,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "content": cleaned,
                "assistant_message_id": assistant_message["message_id"],
                "thread_role": thread_role,
            },
            daemon=True,
        ).start()

        return {
            "user_message": user_message,
            "assistant_message": assistant_message,
            "active_turn_id": turn_id,
        }

    def _maybe_start_local_review_for_audit_write(
        self,
        project_id: str,
        node_id: str,
    ) -> None:
        exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
        status = str(exec_state.get("status") or "").strip() if isinstance(exec_state, dict) else ""
        if status != "completed":
            return
        if self._review_service is None:
            raise RuntimeError(
                "ChatService review service is not configured for audit-triggered local review."
            )
        self._review_service.start_local_review(project_id, node_id)

    def reset_session(
        self, project_id: str, node_id: str, thread_role: str = "ask_planning"
    ) -> dict[str, Any]:
        thread_role = str(thread_role or "").strip()
        self._validate_thread_access(project_id, node_id, thread_role)
        if thread_role == "audit":
            raise ThreadReadOnly("audit", "Audit history is immutable and cannot be reset.")
        self._check_thread_writable(project_id, node_id, thread_role)
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node = self._require_node_from_snapshot(snapshot, node_id)
            session = self._load_session_locked(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            if session.get("active_turn_id"):
                with self._live_turns_lock:
                    active = (project_id, node_id, thread_role, str(session["active_turn_id"])) in self._live_turns
                if active:
                    raise ChatTurnAlreadyActive()
            return self._storage.chat_state_store.clear_session(
                project_id, node_id, thread_role=thread_role
            )

    def has_live_turns_for_project(self, project_id: str) -> bool:
        with self._live_turns_lock:
            return any(turn[0] == project_id for turn in self._live_turns)

    def register_external_live_turn(
        self, project_id: str, node_id: str, thread_role: str, turn_id: str
    ) -> None:
        with self._live_turns_lock:
            self._live_turns.add((project_id, node_id, thread_role, turn_id))

    def clear_external_live_turn(
        self, project_id: str, node_id: str, thread_role: str, turn_id: str
    ) -> None:
        with self._live_turns_lock:
            self._live_turns.discard((project_id, node_id, thread_role, turn_id))

    def _run_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        content: str,
        assistant_message_id: str,
        thread_role: str = "ask_planning",
    ) -> None:
        thread_id: str | None = None
        draft_lock = threading.Lock()
        accumulator = PartAccumulator()
        last_checkpoint_at = time.monotonic()

        def capture_delta(delta: str) -> None:
            nonlocal last_checkpoint_at
            checkpoint_content: str | None = None
            with draft_lock:
                accumulator.on_delta(delta)
                now = time.monotonic()
                if now - last_checkpoint_at >= _DRAFT_FLUSH_INTERVAL_SEC:
                    checkpoint_content = accumulator.content_projection()
                    last_checkpoint_at = now

            self._handle_delta(project_id, node_id, turn_id, assistant_message_id, delta, thread_role=thread_role)

            if checkpoint_content is not None:
                self._persist_assistant_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=checkpoint_content,
                    status="streaming",
                    error=None,
                    thread_id=thread_id,
                    clear_active_turn=False,
                    parts=accumulator.snapshot_parts(),
                    items=accumulator.snapshot_items(),
                    thread_role=thread_role,
                )

        def capture_tool_call(tool_name: str, arguments: dict) -> None:
            with draft_lock:
                item_id = accumulator.on_tool_call(tool_name, arguments)
                part_index = len(accumulator.parts) - 1
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_tool_call",
                    "message_id": assistant_message_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "part_index": part_index,
                    "item_id": item_id,
                    "item_type": "tool_call",
                    "phase": "started",
                },
                thread_role=thread_role,
            )

        def capture_thread_status(payload: dict) -> None:
            with draft_lock:
                accumulator.on_thread_status(payload)
            status = payload.get("status", {})
            status_type = status.get("type", "unknown") if isinstance(status, dict) else "unknown"
            from backend.ai.part_accumulator import _status_label
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_status",
                    "message_id": assistant_message_id,
                    "status_type": status_type,
                    "label": _status_label(status_type),
                    "item_id": "thread_status",
                    "item_type": "thread_status",
                    "phase": "delta",
                },
                thread_role=thread_role,
            )

        try:
            with self._storage.project_lock(project_id):
                session = self._storage.chat_state_store.read_session(
                    project_id, node_id, thread_role=thread_role
                )
                snapshot = self._storage.project_store.load_snapshot(project_id)

            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            existing_thread_id = session.get("thread_id")

            thread_id = self._ensure_chat_thread(
                project_id,
                node_id,
                thread_role,
                existing_thread_id,
                workspace_root,
            )
            self._persist_thread_id(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                thread_id=thread_id,
                thread_role=thread_role,
            )

            prompt, boundary_prompt_kind = self._build_prompt_for_turn(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                thread_role=thread_role,
                snapshot=snapshot,
                node=node,
                node_by_id=node_by_id,
                user_content=content,
            )
            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                on_delta=capture_delta,
                on_tool_call=capture_tool_call,
                on_thread_status=capture_thread_status,
            )

            with draft_lock:
                accumulator.finalize()
                final_parts = accumulator.snapshot_parts()
                final_items = accumulator.snapshot_items()
                streamed_content = accumulator.content_projection()
            stdout = str(result.get("stdout", "") or "")
            final_content = stdout or streamed_content
            persisted = self._persist_assistant_message(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=final_content,
                status="completed",
                error=None,
                thread_id=thread_id,
                clear_active_turn=False,
                parts=final_parts,
                items=final_items,
                thread_role=thread_role,
            )

            if persisted:
                if boundary_prompt_kind == "local_review" and thread_role == "audit":
                    try:
                        self._mark_local_review_prompt_consumed(project_id, node_id)
                    except Exception:
                        logger.debug("Failed to consume local review prompt marker", exc_info=True)
                elif boundary_prompt_kind == "package_review" and thread_role == "audit":
                    try:
                        self._mark_package_review_prompt_consumed(project_id, node_id)
                    except Exception:
                        logger.debug("Failed to consume package review prompt marker", exc_info=True)
                self._clear_active_turn(
                    project_id,
                    node_id,
                    turn_id,
                    thread_role=thread_role,
                )
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_completed",
                        "message_id": assistant_message_id,
                        "content": final_content,
                        "thread_id": thread_id,
                    },
                    thread_role=thread_role,
                )
        except Exception as exc:
            logger.debug(
                "Chat turn failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            try:
                with draft_lock:
                    accumulator.finalize()
                    error_parts = accumulator.snapshot_parts()
                    streamed_content = accumulator.content_projection()
                persisted = self._persist_assistant_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=streamed_content,
                    status="error",
                    error=str(exc),
                    thread_id=thread_id,
                    clear_active_turn=True,
                    parts=error_parts,
                    items=accumulator.snapshot_items(),
                    thread_role=thread_role,
                )
            except Exception:
                persisted = False
                logger.debug("Failed to persist chat error state", exc_info=True)

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_error",
                        "message_id": assistant_message_id,
                        "error": str(exc),
                    },
                    thread_role=thread_role,
                )
        finally:
            with self._live_turns_lock:
                self._live_turns.discard((project_id, node_id, thread_role, turn_id))

    def _handle_delta(
        self,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        delta: str,
        *,
        thread_role: str = "ask_planning",
    ) -> None:
        del turn_id
        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "assistant_delta",
                "message_id": assistant_message_id,
                "delta": delta,
                "item_id": "assistant_text",
                "item_type": "assistant_text",
                "phase": "delta",
            },
            thread_role=thread_role,
        )

    def _ensure_chat_thread(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        existing_thread_id: Any,
        workspace_root: str | None,
    ) -> str:
        del existing_thread_id
        if thread_role == "ask_planning":
            return self._ensure_ask_planning_thread(project_id, node_id, workspace_root)
        if thread_role == "audit":
            return self._ensure_audit_thread(project_id, node_id, workspace_root)
        raise ValueError(f"Unsupported interactive thread role: {thread_role!r}")

    def _bootstrap_task_session_on_read(
        self,
        project_id: str,
        node_id: str,
        node: dict[str, Any],
        thread_role: str,
    ) -> None:
        if str(node.get("node_kind") or "").strip() == "review":
            return
        if thread_role not in {"ask_planning", "audit"}:
            return

        workspace_root = self._workspace_root_for_project(project_id)
        if thread_role == "ask_planning":
            self._ensure_ask_planning_thread(project_id, node_id, workspace_root)
            return
        self._ensure_audit_thread(project_id, node_id, workspace_root)

    def _ensure_ask_planning_thread(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> str:
        base_instructions, dynamic_tools = build_ask_planning_thread_config()
        try:
            session = self._thread_lineage_service.ensure_forked_thread(
                project_id,
                node_id,
                "ask_planning",
                source_node_id=node_id,
                source_role="audit",
                fork_reason="ask_bootstrap",
                workspace_root=workspace_root,
                base_instructions=base_instructions,
                dynamic_tools=dynamic_tools,
            )
        except CodexTransportError as exc:
            raise ChatBackendUnavailable(str(exc)) from exc
        thread_id = str(session.get("thread_id") or "").strip()
        if not thread_id:
            raise ChatBackendUnavailable("Ask thread bootstrap did not return a thread id.")
        return thread_id

    def _ensure_audit_thread(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> str:
        try:
            session = self._thread_lineage_service.resume_or_rebuild_session(
                project_id,
                node_id,
                "audit",
                workspace_root,
            )
        except CodexTransportError as exc:
            raise ChatBackendUnavailable(str(exc)) from exc
        thread_id = str(session.get("thread_id") or "").strip()
        if not thread_id:
            raise ChatBackendUnavailable("Audit thread bootstrap did not return a thread id.")
        return thread_id

    def _workspace_root_for_project(self, project_id: str) -> str | None:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        return self._workspace_root_from_snapshot(snapshot)

    def _build_prompt_for_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        thread_role: str,
        snapshot: dict[str, Any],
        node: dict[str, Any] | None,
        node_by_id: dict[str, dict[str, Any]],
        user_content: str,
    ) -> tuple[str, str | None]:
        if thread_role == "audit":
            if self._package_review_prompt_is_open(project_id, node_id, node):
                return build_package_review_prompt(
                    self._storage,
                    project_id,
                    node_id,
                    user_content,
                ), "package_review"
            if self._local_review_prompt_is_open(project_id, node_id):
                return build_local_review_prompt(self._storage, project_id, node_id, user_content), "local_review"
        if thread_role == "ask_planning":
            child_activation_prompt = self._build_child_activation_prompt_if_needed(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                node=node,
                node_by_id=node_by_id,
                user_content=user_content,
            )
            if child_activation_prompt is not None:
                return child_activation_prompt, "child_activation"
        return build_chat_prompt(snapshot, node, node_by_id, user_content), None

    def _local_review_prompt_is_open(self, project_id: str, node_id: str) -> bool:
        exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
        if not isinstance(exec_state, dict):
            return False
        status = str(exec_state.get("status") or "").strip()
        started_at = str(exec_state.get("local_review_started_at") or "").strip()
        consumed_at = str(exec_state.get("local_review_prompt_consumed_at") or "").strip()
        return status == "review_pending" and bool(started_at) and not consumed_at

    def _mark_local_review_prompt_consumed(self, project_id: str, node_id: str) -> None:
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if not isinstance(exec_state, dict):
                return
            if not str(exec_state.get("local_review_started_at") or "").strip():
                return
            if str(exec_state.get("local_review_prompt_consumed_at") or "").strip():
                return
            exec_state["local_review_prompt_consumed_at"] = iso_now()
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

    def _package_review_prompt_is_open(
        self,
        project_id: str,
        node_id: str,
        node: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(node, dict):
            return False
        review_node_id = str(node.get("review_node_id") or "").strip()
        if not review_node_id:
            return False
        review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
        if not isinstance(review_state, dict):
            return False
        if not package_audit_ready(self._storage, project_id, node, review_state):
            return False
        rollup = review_state.get("rollup", {})
        if not isinstance(rollup, dict):
            return False
        started_at = str(rollup.get("package_review_started_at") or "").strip()
        consumed_at = str(rollup.get("package_review_prompt_consumed_at") or "").strip()
        return rollup.get("status") == "accepted" and bool(started_at) and not consumed_at

    def _mark_package_review_prompt_consumed(self, project_id: str, node_id: str) -> None:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node = self._require_node_from_snapshot(snapshot, node_id)
            review_node_id = str(node.get("review_node_id") or "").strip()
            if not review_node_id:
                return
            self._storage.review_state_store.mark_package_review_prompt_consumed(
                project_id,
                review_node_id,
            )

    def _build_child_activation_prompt_if_needed(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        node: dict[str, Any] | None,
        node_by_id: dict[str, dict[str, Any]],
        user_content: str,
    ) -> str | None:
        if not isinstance(node, dict):
            return None
        parent_id = str(node.get("parent_id") or "").strip()
        if not parent_id:
            return None
        parent = node_by_id.get(parent_id)
        if not isinstance(parent, dict):
            return None
        review_node_id = str(parent.get("review_node_id") or "").strip()
        if not review_node_id:
            return None
        session = self._storage.chat_state_store.read_session(
            project_id,
            node_id,
            thread_role="ask_planning",
        )
        if self._ask_session_has_prior_successful_assistant_turn(session, turn_id):
            return None
        return build_child_activation_prompt(
            self._storage,
            project_id,
            node_id,
            review_node_id,
            user_content,
        )

    def _ask_session_has_prior_successful_assistant_turn(
        self,
        session: dict[str, Any],
        current_turn_id: str,
    ) -> bool:
        for message in session.get("messages", []):
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "").strip() != "assistant":
                continue
            if str(message.get("turn_id") or "").strip() == current_turn_id:
                continue
            if str(message.get("status") or "").strip() != "completed":
                continue
            return True
        return False

    def _check_thread_writable(self, project_id: str, node_id: str, thread_role: str) -> None:
        """Enforce read-only rules per thread-state-model.md."""
        if thread_role == "audit":
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id, {})
            if str(node.get("node_kind") or "").strip() == "review":
                raise ThreadReadOnly("audit", "Review audit is automated.")
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            review_state = None
            review_node_id = node.get("review_node_id")
            if review_node_id:
                review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
            if audit_writable(self._storage, project_id, node, exec_state, review_state):
                return
            raise ThreadReadOnly("audit", "Audit is not yet writable for this node.")

    def _validate_node_exists(self, project_id: str, node_id: str) -> dict[str, Any]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        return self._require_node_from_snapshot(snapshot, node_id)

    def _validate_thread_access(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
    ) -> dict[str, Any]:
        normalized_role = str(thread_role or "").strip()
        if normalized_role not in _VALID_THREAD_ROLES:
            allowed = ", ".join(sorted(_VALID_THREAD_ROLES))
            raise InvalidRequest(
                f"Invalid thread_role {normalized_role!r}. Must be one of: {allowed}."
            )

        node = self._validate_node_exists(project_id, node_id)
        node_kind = str(node.get("node_kind") or "").strip()
        allowed_roles = _REVIEW_THREAD_ROLES if node_kind == "review" else _TASK_THREAD_ROLES
        if normalized_role not in allowed_roles:
            allowed = ", ".join(sorted(allowed_roles))
            raise InvalidRequest(
                f"Thread role {normalized_role!r} is not valid for node_kind {node_kind!r}. "
                f"Allowed roles: {allowed}."
            )
        return node

    def _require_node_from_snapshot(
        self,
        snapshot: dict[str, Any],
        node_id: str,
    ) -> dict[str, Any]:
        node_by_id = self._tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        return node

    def _load_session_locked(
        self,
        project_id: str,
        node_id: str,
        *,
        thread_role: str,
    ) -> dict[str, Any]:
        session = self._storage.chat_state_store.read_session(
            project_id,
            node_id,
            thread_role=thread_role,
        )
        changed = False
        if self._recover_stale_turn(project_id, node_id, session, thread_role=thread_role):
            changed = True
        if changed:
            session = self._storage.chat_state_store.write_session(
                project_id,
                node_id,
                session,
                thread_role=thread_role,
            )
        return session

    def _persist_thread_id(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        thread_id: str,
        thread_role: str = "ask_planning",
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role=thread_role
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            if self._find_message(session, assistant_message_id) is None:
                return False
            session["thread_id"] = thread_id
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role=thread_role
            )
            return True

    def _persist_assistant_message(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        content: str,
        status: str,
        error: str | None,
        thread_id: str | None,
        clear_active_turn: bool,
        parts: list[dict] | None = None,
        items: list[dict[str, Any]] | None = None,
        thread_role: str = "ask_planning",
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role=thread_role
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return False

            message["content"] = content
            message["status"] = status
            message["error"] = error
            message["updated_at"] = iso_now()
            if parts is not None:
                message["parts"] = parts
            if items is not None:
                message["items"] = items

            if thread_id is not None:
                session["thread_id"] = thread_id
            if clear_active_turn:
                session["active_turn_id"] = None

            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role=thread_role
            )
            return True

    def _clear_active_turn(
        self,
        project_id: str,
        node_id: str,
        turn_id: str,
        *,
        thread_role: str = "ask_planning",
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role=thread_role
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            session["active_turn_id"] = None
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role=thread_role
            )
            return True

    def _find_message(
        self,
        session: dict[str, Any],
        assistant_message_id: str,
    ) -> dict[str, Any] | None:
        for message in reversed(session.get("messages", [])):
            if message.get("message_id") == assistant_message_id:
                return message
        return None

    def _recover_stale_turn(
        self, project_id: str, node_id: str, session: dict[str, Any],
        *, thread_role: str = "ask_planning",
    ) -> bool:
        active_turn_id = session.get("active_turn_id")
        if not active_turn_id:
            return False
        with self._live_turns_lock:
            if (project_id, node_id, thread_role, str(active_turn_id)) in self._live_turns:
                return False

        for message in reversed(session.get("messages", [])):
            if message.get("role") != "assistant":
                continue
            if message.get("status") not in ("pending", "streaming"):
                continue
            message["status"] = "error"
            message["error"] = _STALE_TURN_MESSAGE
            message["updated_at"] = iso_now()
            break

        session["active_turn_id"] = None
        return True

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_path")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _is_missing_thread_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message
