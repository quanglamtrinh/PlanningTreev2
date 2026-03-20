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
)
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)

_STALE_TURN_MESSAGE = "Session interrupted - server restarted before response completed."
_DRAFT_FLUSH_INTERVAL_SEC = 0.5


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
        self._live_turns: set[tuple[str, str, str]] = set()
        self._live_turns_lock = threading.Lock()

    def get_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        self._validate_node_exists(project_id, node_id)
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(project_id, node_id)
            if self._recover_stale_turn(project_id, node_id, session):
                session = self._storage.chat_state_store.write_session(project_id, node_id, session)
            return session

    def create_message(self, project_id: str, node_id: str, content: str) -> dict[str, Any]:
        self._validate_node_exists(project_id, node_id)
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
            session = self._storage.chat_state_store.read_session(project_id, node_id)
            self._recover_stale_turn(project_id, node_id, session)
            if session.get("active_turn_id"):
                raise ChatTurnAlreadyActive()

            session["messages"].append(user_message)
            session["messages"].append(assistant_message)
            session["active_turn_id"] = turn_id
            self._storage.chat_state_store.write_session(project_id, node_id, session)

            with self._live_turns_lock:
                self._live_turns.add((project_id, node_id, turn_id))

        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "message_created",
                "user_message": user_message,
                "assistant_message": assistant_message,
                "active_turn_id": turn_id,
            },
        )

        threading.Thread(
            target=self._run_background_turn,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "content": cleaned,
                "assistant_message_id": assistant_message["message_id"],
            },
            daemon=True,
        ).start()

        return {
            "user_message": user_message,
            "assistant_message": assistant_message,
            "active_turn_id": turn_id,
        }

    def reset_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        self._validate_node_exists(project_id, node_id)
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(project_id, node_id)
            if session.get("active_turn_id"):
                with self._live_turns_lock:
                    active = any(
                        live_turn
                        for live_turn in self._live_turns
                        if live_turn[0] == project_id and live_turn[1] == node_id
                    )
                if active:
                    raise ChatTurnAlreadyActive()
            return self._storage.chat_state_store.clear_session(project_id, node_id)

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

            self._handle_delta(project_id, node_id, turn_id, assistant_message_id, delta)

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
            )

        try:
            with self._storage.project_lock(project_id):
                session = self._storage.chat_state_store.read_session(project_id, node_id)
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
                )
        finally:
            with self._live_turns_lock:
                self._live_turns.discard((project_id, node_id, turn_id))

    def _handle_delta(
        self,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        delta: str,
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

    def _validate_node_exists(self, project_id: str, node_id: str) -> dict[str, Any]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        node_by_id = self._tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        return node

    def _persist_thread_id(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        thread_id: str,
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(project_id, node_id)
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            if self._find_message(session, assistant_message_id) is None:
                return False
            session["thread_id"] = thread_id
            self._storage.chat_state_store.write_session(project_id, node_id, session)
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
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(project_id, node_id)
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

            self._storage.chat_state_store.write_session(project_id, node_id, session)
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

    def _recover_stale_turn(self, project_id: str, node_id: str, session: dict[str, Any]) -> bool:
        active_turn_id = session.get("active_turn_id")
        if not active_turn_id:
            return False
        with self._live_turns_lock:
            if (project_id, node_id, str(active_turn_id)) in self._live_turns:
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
        workspace_root = project.get("project_workspace_root")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _is_missing_thread_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message
