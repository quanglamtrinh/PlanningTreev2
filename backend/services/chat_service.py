from __future__ import annotations

import logging
import threading
import time
from typing import Any

from backend.ai.chat_prompt_builder import build_chat_prompt
from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.part_accumulator import PartAccumulator
from backend.errors.app_errors import (
    ChatBackendUnavailable,
    ChatTurnAlreadyActive,
    InvalidRequest,
    NodeNotFound,
    ThreadReadOnly,
)
from backend.services.execution_gating import audit_writable
from backend.services.thread_seed_service import ensure_thread_seeded_session
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)

_STALE_TURN_MESSAGE = "Session interrupted - server restarted before response completed."
_DRAFT_FLUSH_INTERVAL_SEC = 0.5
_TASK_THREAD_ROLES = {"ask_planning", "audit", "execution"}
_REVIEW_THREAD_ROLES = {"integration"}
_VALID_THREAD_ROLES = _TASK_THREAD_ROLES | _REVIEW_THREAD_ROLES


class ChatService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient,
        chat_event_broker: ChatEventBroker,
        chat_timeout: int,
        max_message_chars: int = 10000,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client
        self._chat_event_broker = chat_event_broker
        self._chat_timeout = int(chat_timeout)
        self._max_message_chars = max_message_chars
        self._live_turns: set[tuple[str, str, str, str]] = set()
        self._live_turns_lock = threading.Lock()

    def get_session(
        self, project_id: str, node_id: str, thread_role: str = "ask_planning"
    ) -> dict[str, Any]:
        thread_role = str(thread_role or "").strip()
        self._validate_thread_access(project_id, node_id, thread_role)
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node = self._require_node_from_snapshot(snapshot, node_id)
            session = self._load_session_locked(
                project_id,
                node_id,
                thread_role=thread_role,
                snapshot=snapshot,
                node=node,
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
                snapshot=snapshot,
                node=node,
            )
            if session.get("active_turn_id"):
                raise ChatTurnAlreadyActive()

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
                snapshot=snapshot,
                node=node,
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
                    thread_role=thread_role,
                )

        def capture_tool_call(tool_name: str, arguments: dict) -> None:
            with draft_lock:
                accumulator.on_tool_call(tool_name, arguments)
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

            thread_id = self._ensure_chat_thread(existing_thread_id, workspace_root)
            self._persist_thread_id(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                thread_id=thread_id,
                thread_role=thread_role,
            )

            prompt = build_chat_prompt(snapshot, node, node_by_id, content)
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
                clear_active_turn=True,
                parts=final_parts,
                thread_role=thread_role,
            )

            if persisted:
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
            },
            thread_role=thread_role,
        )

    def _ensure_chat_thread(self, existing_thread_id: Any, workspace_root: str | None) -> str:
        if isinstance(existing_thread_id, str) and existing_thread_id.strip():
            try:
                self._codex_client.resume_thread(
                    existing_thread_id,
                    cwd=workspace_root,
                    timeout_sec=15,
                )
                return existing_thread_id.strip()
            except CodexTransportError as exc:
                if not self._is_missing_thread_error(exc):
                    raise ChatBackendUnavailable(str(exc)) from exc

        try:
            response = self._codex_client.start_thread(
                base_instructions=(
                    "You are a helpful assistant for the PlanningTree project planning tool. "
                    "Help the user with their task by providing clear, actionable guidance."
                ),
                dynamic_tools=[],
                cwd=workspace_root,
                timeout_sec=30,
            )
        except CodexTransportError as exc:
            raise ChatBackendUnavailable(str(exc)) from exc

        thread_id = str(response.get("thread_id") or "").strip()
        if not thread_id:
            raise ChatBackendUnavailable("Chat thread start did not return a thread id.")
        return thread_id

    def _check_thread_writable(self, project_id: str, node_id: str, thread_role: str) -> None:
        """Enforce read-only rules per thread-state-model.md."""
        if thread_role == "execution":
            raise ThreadReadOnly("execution", "Execution thread is automated; user cannot send messages.")

        if thread_role == "ask_planning":
            if self._storage.execution_state_store.exists(project_id, node_id):
                raise ThreadReadOnly("ask_planning", "Shaping is frozen after Finish Task.")

        if thread_role == "audit":
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id, {})
            review_state = None
            review_node_id = node.get("review_node_id")
            if review_node_id:
                review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
            if audit_writable(self._storage, project_id, node, exec_state, review_state):
                return
            raise ThreadReadOnly("audit", "Audit is not yet writable for this node.")

        if thread_role == "integration":
            # Integration thread: only Codex writes during rollup review
            raise ThreadReadOnly("integration", "Integration thread is automated.")

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
        snapshot: dict[str, Any],
        node: dict[str, Any],
    ) -> dict[str, Any]:
        session = self._storage.chat_state_store.read_session(
            project_id,
            node_id,
            thread_role=thread_role,
        )
        changed = False
        session, seeded = ensure_thread_seeded_session(
            self._storage,
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            snapshot=snapshot,
            node=node,
            session=session,
        )
        changed = changed or seeded
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

            if thread_id is not None:
                session["thread_id"] = thread_id
            if clear_active_turn:
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
