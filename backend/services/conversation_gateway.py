from __future__ import annotations

import copy
import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.conversation.contracts import (
    ConversationEventEnvelope,
    ConversationMessage,
    ConversationMessagePart,
    ConversationSnapshot,
    make_conversation_message,
    make_conversation_part,
)
from backend.errors.app_errors import (
    ChatTurnAlreadyActive,
    ConversationPersistenceUnavailable,
    ConversationStreamMismatch,
    NodeNotFound,
    NodeUpdateNotAllowed,
)
from backend.services.ask_service import AskService, make_ask_assistant_text_part_id, make_ask_stream_id
from backend.services.codex_session_manager import CodexSessionManager, ProjectCodexSession, RuntimeThreadState
from backend.services.conversation_context_builder import ConversationContextBuilder
from backend.services.planning_conversation_adapter import (
    build_context_merge_text,
    build_planning_split_summary,
    extract_split_payload,
    make_planning_assistant_message_id,
    make_planning_assistant_text_part_id,
    make_planning_stream_id,
    make_planning_tool_call_part_id,
    make_planning_user_message_id,
)
from backend.services.thread_service import PLANNING_STALE_TURN_ERROR
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.conversation_broker import ConversationEventBroker

logger = logging.getLogger(__name__)

EXECUTION_INTERRUPTED_MESSAGE = "Execution conversation was interrupted before completion."


def make_execution_tool_call_part_id(assistant_message_id: str, index: int) -> str:
    return f"{assistant_message_id}:tool_call:{index}"


def make_execution_plan_block_part_id(assistant_message_id: str, plan_id: str) -> str:
    return f"{assistant_message_id}:plan_block:{plan_id}"


def make_execution_request_message_id(request_id: str) -> str:
    return f"request_message:{request_id}"


def make_execution_request_part_id(request_id: str, part_type: str) -> str:
    return f"{make_execution_request_message_id(request_id)}:{part_type}"


def make_execution_request_response_message_id(request_id: str) -> str:
    return f"request_response:{request_id}"


def make_execution_request_response_part_id(request_id: str) -> str:
    return f"{make_execution_request_response_message_id(request_id)}:user_input_response"


@dataclass
class _LiveConversationState:
    event_seq: int
    assistant_text: str = ""
    tool_call_count: int = 0
    plan_block_text_by_id: dict[str, str] = field(default_factory=dict)
    passive_part_orders: dict[str, int] = field(default_factory=dict)
    next_passive_part_order: int = 1


@dataclass
class _PersistenceTask:
    run: Callable[[], None]
    done_event: threading.Event | None = None
    error_holder: list[BaseException] | None = None


class ConversationGateway:
    def __init__(
        self,
        storage: Storage,
        tree_service,
        thread_service,
        session_manager: CodexSessionManager,
        event_broker: ConversationEventBroker,
        context_builder: ConversationContextBuilder,
        ask_service: AskService | None = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._thread_service = thread_service
        self._session_manager = session_manager
        self._event_broker = event_broker
        self._context_builder = context_builder
        self._ask_service = ask_service
        self._live_state: dict[tuple[str, str], _LiveConversationState] = {}
        self._live_state_lock = threading.Lock()
        self._persistence_queue: queue.Queue[_PersistenceTask | object] = queue.Queue()
        self._persistence_stop = object()
        self._worker_guard = threading.Lock()
        self._worker_stopped = False
        self._worker_thread = threading.Thread(target=self._persistence_worker, daemon=True)
        self._worker_thread.start()

    def get_execution_conversation(self, project_id: str, node_id: str) -> ConversationSnapshot:
        self._load_node_context(project_id, node_id)
        snapshot = self._storage.conversation_store.get_or_create_conversation(
            project_id,
            node_id,
            "execution",
            "execute",
        )
        snapshot = self._recover_orphaned_execution_if_needed(project_id, snapshot)
        return self._enrich_snapshot(project_id, snapshot)

    def prepare_execution_event_stream(
        self,
        project_id: str,
        node_id: str,
        *,
        expected_stream_id: str | None,
    ) -> str:
        snapshot = self.get_execution_conversation(project_id, node_id)
        conversation_id = str(snapshot["record"]["conversation_id"])
        expected = str(expected_stream_id or "").strip() or None
        if expected is None:
            return conversation_id
        session = self._session_manager.get_session(project_id)
        if session is None:
            return conversation_id
        with session.lock:
            current_stream_id = session.active_streams.get(conversation_id)
            if current_stream_id and current_stream_id != expected:
                raise ConversationStreamMismatch()
        return conversation_id

    def get_ask_conversation(self, project_id: str, node_id: str) -> ConversationSnapshot:
        ask_service = self._require_ask_service()
        session = ask_service.get_session_state(project_id, node_id)
        return self._build_ask_conversation_snapshot(session)

    def get_planning_conversation(self, project_id: str, node_id: str) -> ConversationSnapshot:
        _, node, _, _ = self._load_node_context(project_id, node_id)
        planning_state = self._storage.thread_store.get_or_create_planning_conversation_state(project_id, node_id)
        turns = self._thread_service.materialize_inherited_planning_history(project_id, node_id)
        return self._build_planning_conversation_snapshot(
            project_id=project_id,
            node=node,
            planning_state=planning_state,
            turns=turns,
        )

    def prepare_ask_event_stream(
        self,
        project_id: str,
        node_id: str,
        *,
        expected_stream_id: str | None,
    ) -> str:
        snapshot = self.get_ask_conversation(project_id, node_id)
        conversation_id = str(snapshot["record"]["conversation_id"])
        expected = str(expected_stream_id or "").strip() or None
        if expected is None:
            return conversation_id
        active_stream_id = snapshot["record"]["active_stream_id"]
        if active_stream_id is not None and active_stream_id != expected:
            raise ConversationStreamMismatch()
        return conversation_id

    def prepare_planning_event_stream(
        self,
        project_id: str,
        node_id: str,
        *,
        expected_stream_id: str | None,
    ) -> str:
        snapshot = self.get_planning_conversation(project_id, node_id)
        conversation_id = str(snapshot["record"]["conversation_id"])
        expected = str(expected_stream_id or "").strip() or None
        if expected is None:
            return conversation_id
        active_stream_id = snapshot["record"]["active_stream_id"]
        if active_stream_id is not None and active_stream_id != expected:
            raise ConversationStreamMismatch()
        return conversation_id

    def send_ask_message(self, project_id: str, node_id: str, content: Any) -> dict[str, Any]:
        ask_service = self._require_ask_service()
        response = ask_service.create_message(project_id, node_id, content)
        return {
            "status": str(response.get("status") or "accepted"),
            "conversation_id": str(response["conversation_id"]),
            "turn_id": str(response["turn_id"]),
            "stream_id": str(response["stream_id"]),
            "user_message_id": str(response["user_message_id"]),
            "assistant_message_id": str(response["assistant_message_id"]),
            "assistant_text_part_id": str(response["assistant_text_part_id"]),
        }

    def translate_ask_event(
        self,
        event: dict[str, Any],
    ) -> list[ConversationEventEnvelope]:
        event_type = str(event.get("type") or "").strip()
        if event_type not in {
            "ask_message_created",
            "ask_assistant_delta",
            "ask_assistant_completed",
            "ask_assistant_error",
        }:
            return []

        conversation_id = str(event.get("conversation_id") or "").strip()
        turn_id = str(event.get("turn_id") or event.get("active_turn_id") or "").strip()
        stream_id = str(event.get("stream_id") or "").strip() or (make_ask_stream_id(turn_id) if turn_id else "")
        if not conversation_id or not turn_id or not stream_id:
            return []

        try:
            raw_event_seq = max(0, int(event.get("event_seq", 0) or 0))
        except (TypeError, ValueError):
            raw_event_seq = 0
        base_event_seq = raw_event_seq * 3
        created_at = iso_now()

        if event_type == "ask_message_created":
            user_message = event.get("user_message")
            assistant_message = event.get("assistant_message")
            if not isinstance(user_message, dict) or not isinstance(assistant_message, dict):
                return []
            return [
                self._build_message_created_event(
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    event_seq=max(1, base_event_seq - 2),
                    created_at=str(user_message.get("created_at") or created_at),
                    message=self._normalize_ask_message_to_conversation_message(
                        message=user_message,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                    ),
                ),
                self._build_message_created_event(
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    event_seq=max(1, base_event_seq - 1),
                    created_at=str(assistant_message.get("created_at") or created_at),
                    message=self._normalize_ask_message_to_conversation_message(
                        message=assistant_message,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                    ),
                ),
            ]

        assistant_message_id = str(event.get("message_id") or "").strip()
        if not assistant_message_id:
            return []
        assistant_part_id = make_ask_assistant_text_part_id(assistant_message_id)
        updated_at = str(event.get("updated_at") or created_at)

        if event_type == "ask_assistant_delta":
            return [
                self._build_assistant_text_event(
                    event_type="assistant_text_delta",
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    message_id=assistant_message_id,
                    part_id=assistant_part_id,
                    event_seq=max(1, base_event_seq),
                    created_at=updated_at,
                    payload={
                        "part_id": assistant_part_id,
                        "delta": str(event.get("delta") or ""),
                        "status": "streaming",
                    },
                )
            ]

        if event_type == "ask_assistant_completed":
            final_text = str(event.get("content") or "")
            return [
                self._build_assistant_text_event(
                    event_type="assistant_text_final",
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    message_id=assistant_message_id,
                    part_id=assistant_part_id,
                    event_seq=max(1, base_event_seq - 1),
                    created_at=updated_at,
                    payload={
                        "part_id": assistant_part_id,
                        "text": final_text,
                        "status": "completed",
                    },
                ),
                self._build_completion_status_event(
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    message_id=assistant_message_id,
                    event_seq=max(1, base_event_seq),
                    created_at=updated_at,
                    status="completed",
                    error=None,
                ),
            ]

        return [
            self._build_completion_status_event(
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                event_seq=max(1, base_event_seq),
                created_at=updated_at,
                status="error",
                error=str(event.get("error") or "Ask conversation failed."),
            )
        ]

    def translate_planning_event(
        self,
        event: dict[str, Any],
    ) -> list[ConversationEventEnvelope]:
        event_type = str(event.get("type") or "").strip()
        if event_type not in {
            "planning_turn_started",
            "planning_turn_completed",
            "planning_turn_failed",
        }:
            return []

        conversation_id = str(event.get("conversation_id") or "").strip()
        turn_id = str(event.get("turn_id") or "").strip()
        stream_id = str(event.get("stream_id") or "").strip() or (
            make_planning_stream_id(turn_id) if turn_id else ""
        )
        if not conversation_id or not turn_id or not stream_id:
            return []

        created_at = str(event.get("timestamp") or iso_now())
        assistant_message_id = make_planning_assistant_message_id(turn_id)
        assistant_part_id = make_planning_assistant_text_part_id(turn_id)

        if event_type == "planning_turn_started":
            user_content = str(event.get("user_content") or "").strip()
            try:
                user_event_seq = max(1, int(event.get("user_event_seq", 0) or 0))
                assistant_event_seq = max(1, int(event.get("assistant_event_seq", 0) or 0))
            except (TypeError, ValueError):
                return []
            user_message = self._build_planning_user_message(
                conversation_id=conversation_id,
                turn_id=turn_id,
                text=user_content or "Split requested.",
                created_at=created_at,
            )
            assistant_message = self._build_planning_assistant_message(
                conversation_id=conversation_id,
                turn_id=turn_id,
                text="",
                created_at=created_at,
                status="pending",
                error=None,
                tool_calls=None,
            )
            return [
                self._build_message_created_event(
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    event_seq=user_event_seq,
                    created_at=created_at,
                    message=user_message,
                ),
                self._build_message_created_event(
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    event_seq=assistant_event_seq,
                    created_at=created_at,
                    message=assistant_message,
                ),
            ]

        assistant_text = str(event.get("assistant_text") or "").strip()
        try:
            assistant_text_event_seq = max(1, int(event.get("assistant_text_event_seq", 0) or 0))
            completion_event_seq = max(1, int(event.get("completion_event_seq", 0) or 0))
        except (TypeError, ValueError):
            return []

        if event_type == "planning_turn_completed":
            return [
                self._build_assistant_text_event(
                    event_type="assistant_text_final",
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    message_id=assistant_message_id,
                    part_id=assistant_part_id,
                    event_seq=assistant_text_event_seq,
                    created_at=created_at,
                    payload={
                        "part_id": assistant_part_id,
                        "text": assistant_text or "Split completed.",
                        "status": "completed",
                    },
                ),
                self._build_completion_status_event(
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    message_id=assistant_message_id,
                    event_seq=completion_event_seq,
                    created_at=created_at,
                    status="completed",
                    error=None,
                ),
            ]

        error_text = assistant_text or f"Split failed: {event.get('message') or 'Planning failed.'}"
        return [
            self._build_assistant_text_event(
                event_type="assistant_text_final",
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                part_id=assistant_part_id,
                event_seq=assistant_text_event_seq,
                created_at=created_at,
                payload={
                    "part_id": assistant_part_id,
                    "text": error_text,
                    "status": "error",
                },
            ),
            self._build_completion_status_event(
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                event_seq=completion_event_seq,
                created_at=created_at,
                status="error",
                error=error_text,
            ),
        ]

    def flush_persistence(self) -> None:
        self._persistence_queue.join()

    def flush_and_stop(self) -> None:
        with self._worker_guard:
            if self._worker_stopped:
                return
            self._persistence_queue.join()
            self._persistence_queue.put(self._persistence_stop)
            self._worker_thread.join(timeout=5)
            self._worker_stopped = True

    def _load_node_context(
        self,
        project_id: str,
        node_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
        project_snapshot = self._storage.project_store.load_snapshot(project_id)
        node_by_id = self._tree_service.node_index(project_snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        state = self._storage.node_store.load_state(project_id, node_id)
        project = project_snapshot.get("project", {})
        if not isinstance(project, dict):
            raise ValueError("project workspace_root is required for conversation gateway")
        workspace_root = str(project.get("project_workspace_root") or "").strip()
        if not workspace_root:
            raise ValueError("project workspace_root is required for conversation gateway")
        return project_snapshot, node, state, workspace_root

    def _require_ask_service(self) -> AskService:
        if self._ask_service is None:
            raise ValueError("ask conversation support is not configured")
        return self._ask_service

    def _build_ask_conversation_snapshot(
        self,
        session: dict[str, Any],
    ) -> ConversationSnapshot:
        created_at = str(session.get("created_at") or iso_now())
        messages = self._normalize_ask_messages_to_conversation_messages(session)
        latest_assistant_message = next(
            (message for message in reversed(messages) if message["role"] == "assistant"),
            None,
        )
        record_status = "idle"
        if session.get("active_turn_id"):
            record_status = "active"
        elif latest_assistant_message is not None and latest_assistant_message["status"] == "error":
            record_status = "error"
        elif messages:
            record_status = "completed"

        try:
            raw_event_seq = max(0, int(session.get("event_seq", 0) or 0))
        except (TypeError, ValueError):
            raw_event_seq = 0
        normalized_event_seq = raw_event_seq * 3

        return {
            "record": {
                "conversation_id": str(session["conversation_id"]),
                "project_id": str(session["project_id"]),
                "node_id": str(session["node_id"]),
                "thread_type": "ask",
                "app_server_thread_id": str(session.get("thread_id") or "").strip() or None,
                "current_runtime_mode": "ask",
                "status": record_status,
                "active_stream_id": (
                    make_ask_stream_id(str(session["active_turn_id"]))
                    if session.get("active_turn_id")
                    else None
                ),
                "event_seq": normalized_event_seq,
                "created_at": created_at,
                "updated_at": self._ask_snapshot_updated_at(created_at, messages),
            },
            "messages": messages,
        }

    def _build_planning_conversation_snapshot(
        self,
        *,
        project_id: str,
        node: dict[str, Any],
        planning_state: dict[str, Any],
        turns: list[dict[str, Any]],
    ) -> ConversationSnapshot:
        conversation_id = str(planning_state.get("conversation_id") or new_id("convplan"))
        messages = self._normalize_planning_turns_to_conversation_messages(turns, conversation_id)
        active_turn_id = str(planning_state.get("active_turn_id") or "").strip() or None
        pending_user_content = str(planning_state.get("pending_user_content") or "").strip()
        pending_started_at = str(
            planning_state.get("pending_started_at")
            or node.get("created_at")
            or iso_now()
        )

        if active_turn_id and not any(message["turn_id"] == active_turn_id for message in messages):
            pending_messages = self._build_pending_planning_messages(
                conversation_id=conversation_id,
                turn_id=active_turn_id,
                user_content=pending_user_content or "Split requested.",
                created_at=pending_started_at,
            )
            messages.extend(pending_messages)

        latest_assistant_message = next(
            (message for message in reversed(messages) if message["role"] == "assistant"),
            None,
        )
        record_status = "idle"
        if active_turn_id or str(planning_state.get("status") or "").strip().lower() == "active":
            record_status = "active"
        elif latest_assistant_message is not None and latest_assistant_message["status"] == "error":
            record_status = "error"
        elif messages:
            record_status = "completed"

        created_at = str(messages[0]["created_at"] if messages else node.get("created_at") or iso_now())
        updated_at = str(messages[-1]["updated_at"] if messages else created_at)
        try:
            conversation_event_seq = max(0, int(planning_state.get("conversation_event_seq", 0) or 0))
        except (TypeError, ValueError):
            conversation_event_seq = 0

        return {
            "record": {
                "conversation_id": conversation_id,
                "project_id": project_id,
                "node_id": str(node["node_id"]),
                "thread_type": "planning",
                "app_server_thread_id": str(planning_state.get("thread_id") or "").strip() or None,
                "current_runtime_mode": "planning",
                "status": record_status,
                "active_stream_id": make_planning_stream_id(active_turn_id) if active_turn_id else None,
                "event_seq": conversation_event_seq,
                "created_at": created_at,
                "updated_at": updated_at,
            },
            "messages": messages,
        }

    def _normalize_planning_turns_to_conversation_messages(
        self,
        turns: list[dict[str, Any]],
        conversation_id: str,
    ) -> list[ConversationMessage]:
        messages: list[ConversationMessage] = []
        buffered_tool_calls: dict[str, list[dict[str, Any]]] = {}

        for raw_turn in turns:
            if not isinstance(raw_turn, dict):
                continue
            turn_id = str(raw_turn.get("turn_id") or "").strip()
            role = str(raw_turn.get("role") or "").strip()
            if not turn_id or not role:
                continue
            timestamp = str(raw_turn.get("timestamp") or iso_now())

            if role == "tool_call":
                buffered_tool_calls.setdefault(turn_id, []).append(copy.deepcopy(raw_turn))
                continue

            if role == "user":
                content = str(raw_turn.get("content") or "").strip()
                messages.append(
                    self._build_planning_user_message(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        text=content,
                        created_at=timestamp,
                    )
                )
                continue

            if role == "context_merge":
                text = build_context_merge_text(
                    summary=str(raw_turn.get("summary") or "").strip() or None,
                    content=str(raw_turn.get("content") or "").strip() or None,
                )
                messages.append(
                    self._build_planning_assistant_message(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        text=text,
                        created_at=timestamp,
                        status="completed",
                        error=None,
                        tool_calls=None,
                    )
                )
                continue

            if role == "assistant":
                tool_turns = buffered_tool_calls.pop(turn_id, [])
                tool_calls = [self._normalize_planning_tool_call(turn_id, index, tool_turn) for index, tool_turn in enumerate(tool_turns)]
                assistant_text = str(raw_turn.get("content") or "").strip()
                error_text = None
                message_status = "completed"
                if tool_turns:
                    assistant_text = build_planning_split_summary(
                        payload=extract_split_payload(
                            [
                                {
                                    "tool_name": str(tool_turn.get("tool_name") or ""),
                                    "arguments": tool_turn.get("arguments"),
                                }
                                for tool_turn in tool_turns
                            ]
                        ),
                    )
                if assistant_text.startswith("Split failed:") or assistant_text == PLANNING_STALE_TURN_ERROR:
                    message_status = "error"
                    error_text = assistant_text
                messages.append(
                    self._build_planning_assistant_message(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        text=assistant_text,
                        created_at=timestamp,
                        status=message_status,
                        error=error_text,
                        tool_calls=tool_calls,
                    )
                )

        return messages

    def _build_pending_planning_messages(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        user_content: str,
        created_at: str,
    ) -> list[ConversationMessage]:
        return [
            self._build_planning_user_message(
                conversation_id=conversation_id,
                turn_id=turn_id,
                text=user_content,
                created_at=created_at,
            ),
            self._build_planning_assistant_message(
                conversation_id=conversation_id,
                turn_id=turn_id,
                text="",
                created_at=created_at,
                status="pending",
                error=None,
                tool_calls=None,
            ),
        ]

    def _build_planning_user_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        text: str,
        created_at: str,
    ) -> ConversationMessage:
        message = make_conversation_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role="user",
            runtime_mode="planning",
            message_id=make_planning_user_message_id(turn_id),
            status="completed",
            parts=[
                make_conversation_part(
                    part_type="user_text",
                    order=0,
                    status="completed",
                    part_id=f"planning_part:{turn_id}:user_text",
                    payload={"text": text},
                )
            ],
        )
        self._stamp_message_timestamps(message, created_at)
        return message

    def _build_planning_assistant_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        text: str,
        created_at: str,
        status: str,
        error: str | None,
        tool_calls: list[ConversationMessagePart] | None,
    ) -> ConversationMessage:
        parts = [
            make_conversation_part(
                part_type="assistant_text",
                order=0,
                status=status,
                part_id=make_planning_assistant_text_part_id(turn_id),
                payload={"text": text},
            )
        ]
        for tool_call in tool_calls or []:
            parts.append(tool_call)
        message = make_conversation_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role="assistant",
            runtime_mode="planning",
            message_id=make_planning_assistant_message_id(turn_id),
            status=status,
            error=error,
            parts=parts,
        )
        self._stamp_message_timestamps(message, created_at)
        return message

    def _normalize_planning_tool_call(
        self,
        turn_id: str,
        index: int,
        raw_turn: dict[str, Any],
    ) -> ConversationMessagePart:
        part = make_conversation_part(
            part_type="tool_call",
            order=index + 1,
            status="completed",
            part_id=make_planning_tool_call_part_id(turn_id, index),
            item_key=make_planning_tool_call_part_id(turn_id, index),
            payload={
                "part_id": make_planning_tool_call_part_id(turn_id, index),
                "tool_call_id": make_planning_tool_call_part_id(turn_id, index),
                "tool_name": str(raw_turn.get("tool_name") or ""),
                "arguments": copy.deepcopy(raw_turn.get("arguments"))
                if isinstance(raw_turn.get("arguments"), dict)
                else {},
            },
        )
        created_at = str(raw_turn.get("timestamp") or iso_now())
        part["created_at"] = created_at
        part["updated_at"] = created_at
        return part

    def _stamp_message_timestamps(self, message: ConversationMessage, created_at: str) -> None:
        message["created_at"] = created_at
        message["updated_at"] = created_at
        for part in message["parts"]:
            part["created_at"] = created_at
            part["updated_at"] = created_at

    def _normalize_ask_messages_to_conversation_messages(
        self,
        session: dict[str, Any],
    ) -> list[ConversationMessage]:
        normalized_messages: list[ConversationMessage] = []
        latest_user_turn_id: str | None = None
        total_messages = len(session.get("messages", []))

        for index, message in enumerate(session.get("messages", [])):
            if not isinstance(message, dict):
                continue
            explicit_turn_id = str(message.get("turn_id") or "").strip() or None
            role = "assistant" if str(message.get("role") or "") == "assistant" else "user"

            if explicit_turn_id:
                turn_id = explicit_turn_id
            elif role == "user":
                next_message = session["messages"][index + 1] if index + 1 < total_messages else None
                if (
                    session.get("active_turn_id")
                    and isinstance(next_message, dict)
                    and str(next_message.get("role") or "") == "assistant"
                    and index == total_messages - 2
                ):
                    turn_id = str(session["active_turn_id"])
                else:
                    turn_id = f"legacy_ask_turn:{message.get('message_id')}"
            elif latest_user_turn_id:
                turn_id = latest_user_turn_id
            elif session.get("active_turn_id") and index == total_messages - 1:
                turn_id = str(session["active_turn_id"])
            else:
                turn_id = f"legacy_ask_turn:{message.get('message_id')}"

            if role == "user":
                latest_user_turn_id = turn_id
            elif not session.get("active_turn_id"):
                latest_user_turn_id = None

            normalized_messages.append(
                self._normalize_ask_message_to_conversation_message(
                    message=message,
                    conversation_id=str(session["conversation_id"]),
                    turn_id=turn_id,
                )
            )

        return normalized_messages

    def _normalize_ask_message_to_conversation_message(
        self,
        *,
        message: dict[str, Any],
        conversation_id: str,
        turn_id: str,
    ) -> ConversationMessage:
        role = "assistant" if str(message.get("role") or "") == "assistant" else "user"
        message_id = str(message.get("message_id") or new_id("msg"))
        created_at = str(message.get("created_at") or iso_now())
        updated_at = str(message.get("updated_at") or created_at)
        status = self._normalize_ask_message_status(message.get("status"))
        content = str(message.get("content") or "")
        part_type = "assistant_text" if role == "assistant" else "user_text"
        part_id = (
            make_ask_assistant_text_part_id(message_id)
            if role == "assistant"
            else f"ask_part:{message_id}:user_text"
        )
        conversation_message = make_conversation_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role=role,
            runtime_mode="ask",
            message_id=message_id,
            status=status,
            error=str(message.get("error") or "").strip() or None,
            parts=[
                make_conversation_part(
                    part_type=part_type,
                    order=0,
                    status=status,
                    part_id=part_id,
                    payload={"text": content},
                )
            ],
        )
        conversation_message["created_at"] = created_at
        conversation_message["updated_at"] = updated_at
        conversation_message["parts"][0]["created_at"] = created_at
        conversation_message["parts"][0]["updated_at"] = updated_at
        return conversation_message

    def _normalize_ask_message_status(self, raw_status: Any) -> str:
        status = str(raw_status or "").strip().lower()
        if status in {"pending", "streaming", "completed", "error"}:
            return status
        return "completed"

    def _ask_snapshot_updated_at(
        self,
        fallback_created_at: str,
        messages: list[ConversationMessage],
    ) -> str:
        if not messages:
            return fallback_created_at
        return str(messages[-1].get("updated_at") or fallback_created_at)

    def _enrich_snapshot(self, project_id: str, snapshot: ConversationSnapshot) -> ConversationSnapshot:
        enriched = copy.deepcopy(snapshot)
        conversation_id = str(enriched["record"]["conversation_id"])
        session = self._session_manager.get_session(project_id)
        if session is None:
            return enriched
        with session.lock:
            current_stream_id = session.active_streams.get(conversation_id)
            if current_stream_id:
                enriched["record"]["active_stream_id"] = current_stream_id
            live_event_seq = self._peek_live_event_seq_locked(project_id, conversation_id)
            if live_event_seq > int(enriched["record"].get("event_seq", 0) or 0):
                enriched["record"]["event_seq"] = live_event_seq
        return enriched

    def _recover_orphaned_execution_if_needed(
        self,
        project_id: str,
        snapshot: ConversationSnapshot,
    ) -> ConversationSnapshot:
        record = snapshot["record"]
        if record.get("active_stream_id") is None and str(record.get("status") or "") != "active":
            return snapshot

        conversation_id = str(record["conversation_id"])
        session = self._session_manager.get_session(project_id)
        if session is not None:
            with session.lock:
                current_stream_id = session.active_streams.get(conversation_id)
                if current_stream_id:
                    return snapshot
                session.active_turns.pop(conversation_id, None)
                app_server_thread_id = str(record.get("app_server_thread_id") or "").strip() or None
                if app_server_thread_id:
                    existing = session.loaded_runtime_threads.get(app_server_thread_id)
                    if existing is not None:
                        existing.active_turn_id = None
                        existing.status = "idle"
                        existing.last_used_at = iso_now()

        repaired = self._storage.conversation_store.mutate_conversation(
            project_id,
            conversation_id,
            lambda working_snapshot: self._apply_orphaned_execution_recovery_mutation(
                snapshot=working_snapshot,
                error_message=EXECUTION_INTERRUPTED_MESSAGE,
            ),
        )
        with self._live_state_lock:
            self._live_state.pop((project_id, conversation_id), None)
        return repaired

    def send_execution_message(self, project_id: str, node_id: str, content: Any) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise ValueError("content is required")

        project_snapshot, node, state, workspace_root = self._load_node_context(project_id, node_id)
        current_phase = str(state.get("phase") or node.get("phase") or "")
        if current_phase != "executing":
            raise NodeUpdateNotAllowed(
                f"Cannot send execution messages in phase '{current_phase}'. Start execution first."
            )

        conversation = self._storage.conversation_store.get_or_create_conversation(
            project_id,
            node_id,
            "execution",
            "execute",
        )
        record = conversation["record"]
        conversation_id = str(record["conversation_id"])
        app_server_thread_id = str(record.get("app_server_thread_id") or "").strip() or None
        session = self._session_manager.get_or_create_session(project_id, workspace_root)
        request_context = self._context_builder.build_execution_request(
            project_id=project_id,
            snapshot=project_snapshot,
            node=node,
            state=state,
            user_message=text,
        )
        self._assert_persistence_handoff_available()

        turn_id = new_id("turn")
        stream_id = new_id("stream")
        user_part = make_conversation_part(
            part_type="user_text",
            order=0,
            payload={"text": text},
            status="completed",
        )
        user_message = make_conversation_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role="user",
            runtime_mode="execute",
            status="completed",
            parts=[user_part],
        )
        assistant_part = make_conversation_part(
            part_type="assistant_text",
            order=0,
            payload={"text": ""},
            status="pending",
        )
        assistant_message = make_conversation_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role="assistant",
            runtime_mode="execute",
            status="pending",
            parts=[assistant_part],
        )
        created_at = iso_now()
        with session.lock:
            if session.active_streams.get(conversation_id):
                raise ChatTurnAlreadyActive()
            self._claim_ownership_locked(
                session,
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                app_server_thread_id=app_server_thread_id,
            )
            self._ensure_live_state_locked(
                project_id,
                conversation_id,
                durable_event_seq=int(record.get("event_seq", 0) or 0),
                assistant_text="",
            )
            user_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)
            assistant_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)
        send_start_task = self._build_send_start_persistence_task(
            project_id=project_id,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            stream_id=stream_id,
            event_seq=assistant_event_seq,
        )

        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_message_created_event(
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                event_seq=user_event_seq,
                created_at=created_at,
                message=user_message,
            ),
        )
        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_message_created_event(
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                event_seq=assistant_event_seq,
                created_at=created_at,
                message=assistant_message,
            ),
        )
        try:
            self._enqueue_persistence_task(send_start_task)
        except BaseException as exc:  # noqa: BLE001
            logger.exception("Execution send-start persistence handoff failed", exc_info=exc)
            with session.lock:
                self._clear_ownership_locked(
                    session,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    app_server_thread_id=app_server_thread_id,
                )
            try:
                self._repair_interrupted_send_start_state(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    event_seq=assistant_event_seq,
                    error_message=EXECUTION_INTERRUPTED_MESSAGE,
                )
            except BaseException as repair_exc:  # noqa: BLE001
                logger.exception("Execution send-start failure repair did not complete", exc_info=repair_exc)
                raise ConversationPersistenceUnavailable() from repair_exc
            raise ConversationPersistenceUnavailable() from exc

        threading.Thread(
            target=self._run_execution_turn,
            kwargs={
                "project_id": project_id,
                "conversation_id": conversation_id,
                "stream_id": stream_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message["message_id"],
                "assistant_part_id": assistant_part["part_id"],
                "prompt": str(request_context["prompt"]),
                "thread_id": app_server_thread_id,
                "timeout_sec": int(request_context["timeout_sec"]),
                "cwd": str(request_context["cwd"]),
                "writable_roots": list(request_context["writable_roots"]),
            },
            daemon=True,
        ).start()

        return {
            "status": "accepted",
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "stream_id": stream_id,
            "user_message_id": user_message["message_id"],
            "assistant_message_id": assistant_message["message_id"],
            "assistant_text_part_id": assistant_part["part_id"],
        }

    def _run_execution_turn(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        assistant_message_id: str,
        assistant_part_id: str,
        prompt: str,
        thread_id: str | None,
        timeout_sec: int,
        cwd: str,
        writable_roots: list[str],
    ) -> None:
        session = self._session_manager.get_session(project_id)
        if session is None:
            return
        try:
            response = session.client.send_prompt_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=timeout_sec,
                cwd=cwd,
                writable_roots=writable_roots,
                on_delta=lambda delta: self._handle_assistant_delta(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    assistant_part_id=assistant_part_id,
                    delta=delta,
                ),
                on_tool_call=lambda tool_name, arguments: self._handle_tool_call(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    tool_name=tool_name,
                    arguments=arguments,
                ),
                on_plan_delta=lambda delta, item: self._handle_plan_delta(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    delta=delta,
                    item=item,
                ),
                on_request_user_input=lambda payload: self._handle_request_user_input(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    payload=payload,
                ),
                on_request_resolved=lambda payload: self._handle_request_resolved(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    payload=payload,
                ),
            )
        except Exception as exc:
            self._handle_completion_error(
                project_id=project_id,
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                assistant_part_id=assistant_part_id,
                error_message=str(exc),
                app_server_thread_id=thread_id,
            )
            return

        response_thread_id = str(response.get("thread_id") or "").strip() or thread_id
        final_text = str(response.get("stdout") or "")
        self._handle_completion_success(
            project_id=project_id,
            conversation_id=conversation_id,
            stream_id=stream_id,
            turn_id=turn_id,
            assistant_message_id=assistant_message_id,
            assistant_part_id=assistant_part_id,
            final_text=final_text,
            tool_calls=response.get("tool_calls"),
            final_plan_item=response.get("final_plan_item"),
            app_server_thread_id=response_thread_id,
        )

    def _handle_assistant_delta(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        assistant_message_id: str,
        assistant_part_id: str,
        delta: str,
    ) -> None:
        if not delta:
            return
        session = self._session_manager.get_session(project_id)
        if session is None:
            return
        created_at = iso_now()
        with session.lock:
            if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
                return
            live_state = self._ensure_live_state_locked(project_id, conversation_id, durable_event_seq=0)
            live_state.assistant_text = f"{live_state.assistant_text}{delta}"
            full_text = live_state.assistant_text
            event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_assistant_text_event(
                event_type="assistant_text_delta",
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                part_id=assistant_part_id,
                event_seq=event_seq,
                created_at=created_at,
                payload={
                    "part_id": assistant_part_id,
                    "delta": delta,
                    "status": "streaming",
                },
            ),
        )
        self._enqueue_persistence_task(
            self._build_delta_persistence_task(
                project_id=project_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                assistant_part_id=assistant_part_id,
                full_text=full_text,
                updated_at=created_at,
                event_seq=event_seq,
            )
        )

    def _handle_tool_call(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        assistant_message_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        session = self._session_manager.get_session(project_id)
        if session is None:
            return

        created_at = iso_now()
        with session.lock:
            if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
                return
            live_state = self._ensure_live_state_locked(project_id, conversation_id, durable_event_seq=0)
            tool_call_index = live_state.tool_call_count
            live_state.tool_call_count += 1
            part_id = make_execution_tool_call_part_id(assistant_message_id, tool_call_index)
            order = self._resolve_passive_part_order_locked(live_state, f"tool_call:{part_id}")
            event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

        part = self._build_execution_tool_call_part(
            assistant_message_id=assistant_message_id,
            tool_call_index=tool_call_index,
            tool_name=tool_name,
            arguments=arguments,
            created_at=created_at,
            order=order,
        )
        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_passive_part_event(
                event_type="tool_call_start",
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                part=part,
                event_seq=event_seq,
                created_at=created_at,
            ),
        )
        self._enqueue_persistence_task(
            self._build_tool_call_persistence_task(
                project_id=project_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                tool_call_part=part,
                event_seq=event_seq,
            )
        )

    def _handle_plan_delta(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        assistant_message_id: str,
        delta: str,
        item: dict[str, Any],
    ) -> None:
        plan_id = str(item.get("id") or "").strip()
        if not plan_id or not delta:
            return
        session = self._session_manager.get_session(project_id)
        if session is None:
            return

        created_at = iso_now()
        with session.lock:
            if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
                return
            live_state = self._ensure_live_state_locked(project_id, conversation_id, durable_event_seq=0)
            full_text = f"{live_state.plan_block_text_by_id.get(plan_id, '')}{delta}"
            live_state.plan_block_text_by_id[plan_id] = full_text
            order = self._resolve_passive_part_order_locked(live_state, f"plan_block:{plan_id}")
            event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

        part = self._build_execution_plan_block_part(
            assistant_message_id=assistant_message_id,
            plan_id=plan_id,
            text=full_text,
            created_at=created_at,
            order=order,
            thread_id=str(item.get("thread_id") or "").strip() or None,
            turn_id=str(item.get("turn_id") or "").strip() or None,
        )
        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_passive_part_event(
                event_type="plan_block",
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                part=part,
                event_seq=event_seq,
                created_at=created_at,
            ),
        )
        self._enqueue_persistence_task(
            self._build_plan_block_persistence_task(
                project_id=project_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                plan_block_part=part,
                event_seq=event_seq,
            )
        )

    def _handle_request_user_input(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        assistant_message_id: str,
        payload: dict[str, Any],
    ) -> None:
        session = self._session_manager.get_session(project_id)
        if session is None:
            return
        snapshot = self._storage.conversation_store.get_conversation(project_id, conversation_id)
        node_id = str(snapshot["record"]["node_id"]) if snapshot is not None else ""

        request_record = self._normalize_execution_request_payload(
            payload,
            node_id=node_id,
            assistant_message_id=assistant_message_id,
        )
        if request_record is None:
            return
        request_record["stream_id"] = stream_id

        created_at = str(request_record.get("created_at") or iso_now())
        request_message = self._build_execution_user_input_request_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            request=request_record,
            created_at=created_at,
        )
        request_part = request_message["parts"][0]

        with session.lock:
            if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
                return
            request_key = str(request_record["request_id"])
            session.runtime_request_registry[request_key] = copy.deepcopy(request_record)
            event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

        self._storage.conversation_store.mutate_conversation(
            project_id,
            conversation_id,
            lambda snapshot: self._apply_interactive_messages_mutation(
                snapshot=snapshot,
                event_seq=event_seq,
                request_message=request_message,
                response_message=None,
                assistant_message_id=assistant_message_id,
            ),
        )
        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_interactive_message_event(
                event_type="request_user_input",
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message=request_message,
                part=request_part,
                event_seq=event_seq,
                created_at=created_at,
            ),
        )

    def _handle_request_resolved(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        payload: dict[str, Any],
    ) -> None:
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return
        session = self._session_manager.get_session(project_id)
        if session is None:
            return

        with session.lock:
            if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
                return
            existing = session.runtime_request_registry.get(request_id)
            if not isinstance(existing, dict):
                return
            updated_request = copy.deepcopy(existing)
            next_status = str(payload.get("status") or updated_request.get("status") or "stale")
            updated_request["status"] = next_status
            updated_request["resolved_at"] = str(payload.get("resolved_at") or updated_request.get("resolved_at") or iso_now())
            session.runtime_request_registry[request_id] = copy.deepcopy(updated_request)
            event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

        request_message = self._build_execution_user_input_request_message(
            conversation_id=conversation_id,
            turn_id=str(updated_request.get("turn_id") or turn_id),
            request=updated_request,
            created_at=str(updated_request.get("created_at") or iso_now()),
        )
        request_part = request_message["parts"][0]
        request_part["updated_at"] = str(updated_request.get("resolved_at") or iso_now())
        request_message["updated_at"] = request_part["updated_at"]
        request_message["status"] = request_part["status"]

        self._storage.conversation_store.mutate_conversation(
            project_id,
            conversation_id,
            lambda snapshot: self._apply_interactive_messages_mutation(
                snapshot=snapshot,
                event_seq=event_seq,
                request_message=request_message,
                response_message=None,
                assistant_message_id=str(updated_request.get("assistant_message_id") or ""),
            ),
        )
        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_passive_part_event(
                event_type="request_resolved",
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=str(updated_request.get("turn_id") or turn_id),
                message_id=request_message["message_id"],
                part=request_part,
                event_seq=event_seq,
                created_at=request_part["updated_at"],
            ),
        )

    def resolve_execution_request(
        self,
        project_id: str,
        node_id: str,
        request_id: str,
        *,
        request_kind: str,
        decision: str | None,
        answers: dict[str, Any] | None,
        thread_id: str | None,
        turn_id: str | None,
    ) -> dict[str, Any]:
        request_key = str(request_id or "").strip()
        if not request_key:
            raise ValueError("request_id is required")
        kind = str(request_kind or "").strip()
        if kind not in {"approval", "user_input"}:
            raise ValueError("request_kind must be 'approval' or 'user_input'")
        if kind == "approval":
            raise ValueError("Approval request resolution is runtime-blocked while approvalPolicy is never.")

        conversation = self.get_execution_conversation(project_id, node_id)
        conversation_id = str(conversation["record"]["conversation_id"])
        session = self._session_manager.get_session(project_id)
        if session is None:
            return {"status": "already_resolved_or_stale"}

        with session.lock:
            request_record = session.runtime_request_registry.get(request_key)
            if not isinstance(request_record, dict):
                return {"status": "already_resolved_or_stale"}
            expected_thread_id = str(request_record.get("thread_id") or "").strip()
            expected_turn_id = str(request_record.get("turn_id") or "").strip()
            if thread_id and str(thread_id).strip() != expected_thread_id:
                raise ValueError("thread_id does not match the pending runtime request.")
            if turn_id and str(turn_id).strip() != expected_turn_id:
                raise ValueError("turn_id does not match the pending runtime request.")
            if str(request_record.get("status") or "") != "pending":
                return {"status": "already_resolved_or_stale"}

        resolved_record = session.client.resolve_runtime_request_user_input(
            request_key,
            answers=answers or {},
        )

        with session.lock:
            request_record = session.runtime_request_registry.get(request_key)
            if not isinstance(request_record, dict):
                request_record = {}
            next_request = copy.deepcopy(request_record)
            if resolved_record is None:
                next_request["status"] = "stale"
                next_request["resolved_at"] = iso_now()
                answer_payload = None
                route_status = "already_resolved_or_stale"
            else:
                next_request["status"] = str(resolved_record.status or "resolved")
                next_request["resolved_at"] = str(resolved_record.resolved_at or iso_now())
                answer_payload = copy.deepcopy(resolved_record.answer_payload) if resolved_record.answer_payload else {"answers": answers or {}}
                if answer_payload is not None:
                    next_request["answer_payload"] = copy.deepcopy(answer_payload)
                route_status = "resolved" if str(next_request.get("status") or "") == "resolved" else "already_resolved_or_stale"
            session.runtime_request_registry[request_key] = copy.deepcopy(next_request)
            current_stream_id = (
                session.active_streams.get(conversation_id)
                or str(conversation["record"].get("active_stream_id") or "")
                or str(next_request.get("stream_id") or request_record.get("stream_id") or "")
            )
            current_turn_id = session.active_turns.get(conversation_id) or str(next_request.get("turn_id") or "")
            request_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)
            response_event_seq = (
                self._allocate_event_seq_locked(project_id, conversation_id)
                if route_status == "resolved" and answer_payload is not None
                else None
            )
            request_message = self._build_execution_user_input_request_message(
                conversation_id=conversation_id,
                turn_id=str(next_request.get("turn_id") or current_turn_id),
                request=next_request,
                created_at=str(next_request.get("created_at") or iso_now()),
            )
            request_part = request_message["parts"][0]
            request_part["updated_at"] = str(next_request.get("resolved_at") or iso_now())
            request_message["updated_at"] = request_part["updated_at"]
            request_message["status"] = request_part["status"]
            response_message = (
                self._build_execution_user_input_response_message(
                    conversation_id=conversation_id,
                    turn_id=str(next_request.get("turn_id") or current_turn_id),
                    request=next_request,
                    answer_payload=answer_payload or {"answers": {}},
                    created_at=str(next_request.get("resolved_at") or iso_now()),
                )
                if route_status == "resolved" and answer_payload is not None
                else None
            )

            self._storage.conversation_store.mutate_conversation(
                project_id,
                conversation_id,
                lambda snapshot: self._apply_interactive_messages_mutation(
                    snapshot=snapshot,
                    event_seq=max(
                        request_event_seq,
                        response_event_seq if response_event_seq is not None else request_event_seq,
                    ),
                    request_message=request_message,
                    response_message=response_message,
                    assistant_message_id=str(next_request.get("assistant_message_id") or ""),
                ),
            )

            stream_id = current_stream_id or str(conversation["record"].get("active_stream_id") or "")
            if stream_id:
                self._event_broker.publish(
                    project_id,
                    conversation_id,
                    self._build_passive_part_event(
                        event_type="request_resolved",
                        conversation_id=conversation_id,
                        stream_id=stream_id,
                        turn_id=str(next_request.get("turn_id") or current_turn_id),
                        message_id=request_message["message_id"],
                        part=request_part,
                        event_seq=request_event_seq,
                        created_at=request_part["updated_at"],
                    ),
                )
                if response_message is not None and response_event_seq is not None:
                    self._event_broker.publish(
                        project_id,
                        conversation_id,
                        self._build_interactive_message_event(
                            event_type="user_input_resolved",
                            conversation_id=conversation_id,
                            stream_id=stream_id,
                            turn_id=str(next_request.get("turn_id") or current_turn_id),
                            message=response_message,
                            part=response_message["parts"][0],
                            event_seq=response_event_seq,
                            created_at=response_message["updated_at"],
                        ),
                    )

        return {"status": route_status}

    def _handle_completion_success(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        assistant_message_id: str,
        assistant_part_id: str,
        final_text: str,
        tool_calls: Any,
        final_plan_item: Any,
        app_server_thread_id: str | None,
    ) -> None:
        session = self._session_manager.get_session(project_id)
        if session is None:
            return
        created_at = iso_now()
        late_tool_calls: list[tuple[int, int, ConversationMessagePart]] = []
        final_plan_block: tuple[int, ConversationMessagePart] | None = None
        with session.lock:
            if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
                return
            live_state = self._ensure_live_state_locked(project_id, conversation_id, durable_event_seq=0)
            normalized_tool_calls = [
                item
                for item in tool_calls
                if isinstance(item, dict)
            ] if isinstance(tool_calls, list) else []
            if normalized_tool_calls and live_state.tool_call_count < len(normalized_tool_calls):
                for tool_call_index in range(live_state.tool_call_count, len(normalized_tool_calls)):
                    raw_tool_call = normalized_tool_calls[tool_call_index]
                    part = self._build_execution_tool_call_part(
                        assistant_message_id=assistant_message_id,
                        tool_call_index=tool_call_index,
                        tool_name=str(raw_tool_call.get("tool_name") or ""),
                        arguments=copy.deepcopy(raw_tool_call.get("arguments"))
                        if isinstance(raw_tool_call.get("arguments"), dict)
                        else {},
                        created_at=created_at,
                        order=self._resolve_passive_part_order_locked(
                            live_state,
                            f"tool_call:{make_execution_tool_call_part_id(assistant_message_id, tool_call_index)}",
                        ),
                    )
                    event_seq = self._allocate_event_seq_locked(project_id, conversation_id)
                    late_tool_calls.append((tool_call_index, event_seq, part))
                live_state.tool_call_count = len(normalized_tool_calls)
            normalized_final_plan = (
                final_plan_item if isinstance(final_plan_item, dict) else None
            )
            if normalized_final_plan is not None:
                plan_id = str(normalized_final_plan.get("id") or "").strip()
                plan_text = str(normalized_final_plan.get("text") or "")
                if plan_id and plan_text:
                    previous_text = live_state.plan_block_text_by_id.get(plan_id)
                    live_state.plan_block_text_by_id[plan_id] = plan_text
                    if previous_text != plan_text:
                        order = self._resolve_passive_part_order_locked(
                            live_state,
                            f"plan_block:{plan_id}",
                        )
                        event_seq = self._allocate_event_seq_locked(project_id, conversation_id)
                        final_plan_block = (
                            event_seq,
                            self._build_execution_plan_block_part(
                                assistant_message_id=assistant_message_id,
                                plan_id=plan_id,
                                text=plan_text,
                                created_at=created_at,
                                order=order,
                                thread_id=str(normalized_final_plan.get("thread_id") or "").strip() or None,
                                turn_id=str(normalized_final_plan.get("turn_id") or "").strip() or None,
                            ),
                        )
            if final_text:
                live_state.assistant_text = final_text
            full_text = live_state.assistant_text
            final_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)
            completion_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

        for _, event_seq, part in late_tool_calls:
            self._event_broker.publish(
                project_id,
                conversation_id,
                self._build_passive_part_event(
                    event_type="tool_call_finish",
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    message_id=assistant_message_id,
                    part=part,
                    event_seq=event_seq,
                    created_at=created_at,
                ),
            )
            self._enqueue_persistence_task(
                self._build_tool_call_persistence_task(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    assistant_message_id=assistant_message_id,
                    tool_call_part=part,
                    event_seq=event_seq,
                )
            )

        if final_plan_block is not None:
            plan_event_seq, plan_part = final_plan_block
            self._event_broker.publish(
                project_id,
                conversation_id,
                self._build_passive_part_event(
                    event_type="plan_block",
                    conversation_id=conversation_id,
                    stream_id=stream_id,
                    turn_id=turn_id,
                    message_id=assistant_message_id,
                    part=plan_part,
                    event_seq=plan_event_seq,
                    created_at=created_at,
                ),
            )
            self._enqueue_persistence_task(
                self._build_plan_block_persistence_task(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    assistant_message_id=assistant_message_id,
                    plan_block_part=plan_part,
                    event_seq=plan_event_seq,
                )
            )

        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_assistant_text_event(
                event_type="assistant_text_final",
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                part_id=assistant_part_id,
                event_seq=final_event_seq,
                created_at=created_at,
                payload={
                    "part_id": assistant_part_id,
                    "text": full_text,
                    "status": "completed",
                },
            ),
        )
        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_completion_status_event(
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                event_seq=completion_event_seq,
                created_at=created_at,
                status="completed",
                error=None,
            ),
        )

        completion_done = threading.Event()
        error_holder: list[BaseException] = []
        self._enqueue_persistence_task(
            self._build_final_text_persistence_task(
                project_id=project_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                assistant_part_id=assistant_part_id,
                full_text=full_text,
                updated_at=created_at,
                event_seq=final_event_seq,
            )
        )
        self._enqueue_persistence_task(
            self._build_completion_persistence_task(
                project_id=project_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                assistant_part_id=assistant_part_id,
                full_text=full_text,
                updated_at=created_at,
                event_seq=completion_event_seq,
                status="completed",
                error_message=None,
                app_server_thread_id=app_server_thread_id,
                done_event=completion_done,
                error_holder=error_holder,
            )
        )
        completion_done.wait()
        if error_holder:
            logger.exception("Conversation completion persistence failed", exc_info=error_holder[0])
        with session.lock:
            self._clear_ownership_locked(
                session,
                project_id=project_id,
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                app_server_thread_id=app_server_thread_id,
            )

    def _handle_completion_error(
        self,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        assistant_message_id: str,
        assistant_part_id: str,
        error_message: str,
        app_server_thread_id: str | None,
    ) -> None:
        session = self._session_manager.get_session(project_id)
        if session is None:
            return
        created_at = iso_now()
        with session.lock:
            if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
                return
            live_state = self._ensure_live_state_locked(project_id, conversation_id, durable_event_seq=0)
            full_text = live_state.assistant_text
            completion_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

        self._event_broker.publish(
            project_id,
            conversation_id,
            self._build_completion_status_event(
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                message_id=assistant_message_id,
                event_seq=completion_event_seq,
                created_at=created_at,
                status="error",
                error=error_message,
            ),
        )

        completion_done = threading.Event()
        error_holder: list[BaseException] = []
        self._enqueue_persistence_task(
            self._build_completion_persistence_task(
                project_id=project_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                assistant_part_id=assistant_part_id,
                full_text=full_text,
                updated_at=created_at,
                event_seq=completion_event_seq,
                status="error",
                error_message=error_message,
                app_server_thread_id=app_server_thread_id,
                done_event=completion_done,
                error_holder=error_holder,
            )
        )
        completion_done.wait()
        if error_holder:
            logger.exception("Conversation error persistence failed", exc_info=error_holder[0])
        with session.lock:
            self._clear_ownership_locked(
                session,
                project_id=project_id,
                conversation_id=conversation_id,
                stream_id=stream_id,
                turn_id=turn_id,
                app_server_thread_id=app_server_thread_id,
            )

    def _build_message_created_event(
        self,
        *,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        event_seq: int,
        created_at: str,
        message: ConversationMessage,
    ) -> ConversationEventEnvelope:
        return {
            "event_type": "message_created",
            "conversation_id": conversation_id,
            "stream_id": stream_id,
            "turn_id": turn_id,
            "message_id": message["message_id"],
            "event_seq": event_seq,
            "created_at": created_at,
            "payload": {"message": copy.deepcopy(message)},
        }

    def _build_assistant_text_event(
        self,
        *,
        event_type: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        message_id: str,
        part_id: str,
        event_seq: int,
        created_at: str,
        payload: dict[str, Any],
    ) -> ConversationEventEnvelope:
        return {
            "event_type": event_type,
            "conversation_id": conversation_id,
            "stream_id": stream_id,
            "turn_id": turn_id,
            "message_id": message_id,
            "item_id": part_id,
            "event_seq": event_seq,
            "created_at": created_at,
            "payload": copy.deepcopy(payload),
        }

    def _build_passive_part_event(
        self,
        *,
        event_type: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        message_id: str,
        part: ConversationMessagePart,
        event_seq: int,
        created_at: str,
    ) -> ConversationEventEnvelope:
        payload = copy.deepcopy(part["payload"])
        payload["part_id"] = part["part_id"]
        return {
            "event_type": event_type,
            "conversation_id": conversation_id,
            "stream_id": stream_id,
            "turn_id": turn_id,
            "message_id": message_id,
            "item_id": part["part_id"],
            "event_seq": event_seq,
            "created_at": created_at,
            "payload": payload,
        }

    def _build_completion_status_event(
        self,
        *,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        message_id: str,
        event_seq: int,
        created_at: str,
        status: str,
        error: str | None,
    ) -> ConversationEventEnvelope:
        payload: dict[str, Any] = {
            "status": status,
            "finished_at": created_at,
        }
        if error:
            payload["error"] = error
        return {
            "event_type": "completion_status",
            "conversation_id": conversation_id,
            "stream_id": stream_id,
            "turn_id": turn_id,
            "message_id": message_id,
            "event_seq": event_seq,
            "created_at": created_at,
            "payload": payload,
        }

    def _build_interactive_message_event(
        self,
        *,
        event_type: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        message: ConversationMessage,
        part: ConversationMessagePart,
        event_seq: int,
        created_at: str,
    ) -> ConversationEventEnvelope:
        payload = copy.deepcopy(part["payload"])
        payload["part_id"] = part["part_id"]
        payload["message"] = copy.deepcopy(message)
        return {
            "event_type": event_type,
            "conversation_id": conversation_id,
            "stream_id": stream_id,
            "turn_id": turn_id,
            "message_id": message["message_id"],
            "item_id": part["part_id"],
            "event_seq": event_seq,
            "created_at": created_at,
            "payload": payload,
        }

    def _normalize_execution_request_payload(
        self,
        payload: dict[str, Any],
        *,
        node_id: str,
        assistant_message_id: str,
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
            if not question_id or not header or not question:
                continue
            normalized_options: list[dict[str, str]] = []
            for option in list(item.get("options") or []):
                if not isinstance(option, dict):
                    continue
                label = str(option.get("label") or "").strip()
                if not label:
                    continue
                normalized_options.append(
                    {
                        "label": label,
                        "description": str(option.get("description") or "").strip(),
                    }
                )
            questions.append(
                {
                    "id": question_id,
                    "header": header,
                    "question": question,
                    "is_other": bool(item.get("isOther")),
                    "is_secret": bool(item.get("isSecret")),
                    "options": normalized_options,
                }
            )
        if not questions:
            return None

        return {
            "request_id": request_id,
            "request_kind": "user_input",
            "thread_id": thread_id,
            "turn_id": turn_id,
            "stream_id": str(payload.get("stream_id") or "").strip() or None,
            "node_id": node_id,
            "item_id": item_id,
            "assistant_message_id": assistant_message_id,
            "request_message_id": make_execution_request_message_id(request_id),
            "request_part_id": make_execution_request_part_id(request_id, "user_input_request"),
            "response_message_id": make_execution_request_response_message_id(request_id),
            "response_part_id": make_execution_request_response_part_id(request_id),
            "questions": questions,
            "created_at": str(payload.get("created_at") or iso_now()),
            "resolved_at": str(payload.get("resolved_at") or "") or None,
            "status": str(payload.get("status") or "pending"),
            "answer_payload": copy.deepcopy(payload.get("answer_payload")) if payload.get("answer_payload") else None,
        }

    def _interactive_request_status_to_message_status(self, request: dict[str, Any]) -> str:
        status = str(request.get("status") or "pending")
        if status in {"resolved", "approved", "declined"}:
            return "completed"
        if status in {"stale", "cancelled"}:
            return "cancelled"
        if status == "error":
            return "error"
        return "pending"

    def _build_execution_user_input_request_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        request: dict[str, Any],
        created_at: str,
    ) -> ConversationMessage:
        part_status = self._interactive_request_status_to_message_status(request)
        payload: dict[str, Any] = {
            "part_id": str(request["request_part_id"]),
            "request_id": str(request["request_id"]),
            "request_kind": "user_input",
            "title": "Runtime input needed",
            "summary": "One short answer is needed before the current run can continue.",
            "prompt": "Submit a response from the host-owned request surface to resume this turn.",
            "resolution_state": str(request.get("status") or "pending"),
            "thread_id": str(request.get("thread_id") or ""),
            "turn_id": str(request.get("turn_id") or turn_id),
            "item_id": str(request.get("item_id") or ""),
            "questions": copy.deepcopy(request.get("questions") or []),
        }
        resolved_at = str(request.get("resolved_at") or "").strip()
        if resolved_at:
            payload["resolved_at"] = resolved_at
        if request.get("answer_payload"):
            payload["answer_payload"] = copy.deepcopy(request["answer_payload"])
        part = make_conversation_part(
            part_type="user_input_request",
            order=0,
            status=part_status,
            part_id=str(request["request_part_id"]),
            item_key=str(request["request_id"]),
            payload=payload,
        )
        message = make_conversation_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role="assistant",
            runtime_mode="execute",
            message_id=str(request["request_message_id"]),
            status=part_status,
            parts=[part],
        )
        self._stamp_message_timestamps(message, created_at)
        return message

    def _render_execution_request_answer_text(
        self,
        request: dict[str, Any],
        answer_payload: dict[str, Any],
    ) -> str:
        answer_map = answer_payload.get("answers") if isinstance(answer_payload, dict) else {}
        lines = ["Runtime input resolved.", ""]
        for question in list(request.get("questions") or []):
            if not isinstance(question, dict):
                continue
            question_id = str(question.get("id") or "").strip()
            if not question_id:
                continue
            lines.append(str(question.get("header") or question_id).strip())
            answer_entry = answer_map.get(question_id) if isinstance(answer_map, dict) else None
            answers = answer_entry.get("answers") if isinstance(answer_entry, dict) else None
            if isinstance(answers, list) and answers:
                lines.extend(str(item or "").strip() for item in answers if str(item or "").strip())
            else:
                lines.append("(no answer text)")
            lines.append("")
        return "\n".join(lines).strip()

    def _build_execution_user_input_response_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        request: dict[str, Any],
        answer_payload: dict[str, Any],
        created_at: str,
    ) -> ConversationMessage:
        response_text = self._render_execution_request_answer_text(request, answer_payload)
        part = make_conversation_part(
            part_type="user_input_response",
            order=0,
            status="completed",
            part_id=str(request["response_part_id"]),
            item_key=str(request["request_id"]),
            payload={
                "part_id": str(request["response_part_id"]),
                "request_id": str(request["request_id"]),
                "request_kind": "user_input",
                "title": "Input submitted",
                "summary": "The runtime request was answered and the active turn can continue.",
                "text": response_text,
                "content": response_text,
                "resolved_at": created_at,
                "answers": copy.deepcopy(answer_payload.get("answers") if isinstance(answer_payload, dict) else {}),
                "questions": copy.deepcopy(request.get("questions") or []),
            },
        )
        message = make_conversation_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role="user",
            runtime_mode="execute",
            message_id=str(request["response_message_id"]),
            status="completed",
            parts=[part],
        )
        self._stamp_message_timestamps(message, created_at)
        return message

    def _build_execution_tool_call_part(
        self,
        *,
        assistant_message_id: str,
        tool_call_index: int,
        tool_name: str,
        arguments: dict[str, Any],
        created_at: str,
        order: int,
    ) -> ConversationMessagePart:
        part_id = make_execution_tool_call_part_id(assistant_message_id, tool_call_index)
        part = make_conversation_part(
            part_type="tool_call",
            order=order,
            status="completed",
            part_id=part_id,
            item_key=part_id,
            payload={
                "part_id": part_id,
                "tool_call_id": part_id,
                "tool_name": tool_name,
                "arguments": copy.deepcopy(arguments),
            },
        )
        part["created_at"] = created_at
        part["updated_at"] = created_at
        return part

    def _build_execution_plan_block_part(
        self,
        *,
        assistant_message_id: str,
        plan_id: str,
        text: str,
        created_at: str,
        order: int,
        thread_id: str | None,
        turn_id: str | None,
    ) -> ConversationMessagePart:
        part_id = make_execution_plan_block_part_id(assistant_message_id, plan_id)
        payload: dict[str, Any] = {
            "part_id": part_id,
            "plan_id": plan_id,
            "text": text,
            "content": text,
        }
        if thread_id:
            payload["thread_id"] = thread_id
        if turn_id:
            payload["turn_id"] = turn_id
        part = make_conversation_part(
            part_type="plan_block",
            order=order,
            status="completed",
            part_id=part_id,
            item_key=plan_id,
            payload=payload,
        )
        part["created_at"] = created_at
        part["updated_at"] = created_at
        return part

    def _build_tool_call_persistence_task(
        self,
        *,
        project_id: str,
        conversation_id: str,
        assistant_message_id: str,
        tool_call_part: ConversationMessagePart,
        event_seq: int,
    ) -> _PersistenceTask:
        def run() -> None:
            self._storage.conversation_store.mutate_conversation(
                project_id,
                conversation_id,
                lambda snapshot: self._apply_tool_call_mutation(
                    snapshot=snapshot,
                    assistant_message_id=assistant_message_id,
                    tool_call_part=tool_call_part,
                    event_seq=event_seq,
                ),
            )

        return _PersistenceTask(run=run)

    def _build_plan_block_persistence_task(
        self,
        *,
        project_id: str,
        conversation_id: str,
        assistant_message_id: str,
        plan_block_part: ConversationMessagePart,
        event_seq: int,
    ) -> _PersistenceTask:
        def run() -> None:
            self._storage.conversation_store.mutate_conversation(
                project_id,
                conversation_id,
                lambda snapshot: self._apply_plan_block_mutation(
                    snapshot=snapshot,
                    assistant_message_id=assistant_message_id,
                    plan_block_part=plan_block_part,
                    event_seq=event_seq,
                ),
            )

        return _PersistenceTask(run=run)

    def _apply_tool_call_mutation(
        self,
        *,
        snapshot: ConversationSnapshot,
        assistant_message_id: str,
        tool_call_part: ConversationMessagePart,
        event_seq: int,
    ) -> None:
        message = self._find_message(snapshot["messages"], assistant_message_id)
        if message is None:
            raise KeyError(f"Unknown assistant message_id: {assistant_message_id}")
        self._upsert_part_in_message(message["parts"], tool_call_part)
        message["updated_at"] = tool_call_part["updated_at"]
        snapshot["record"]["current_runtime_mode"] = "execute"
        snapshot["record"]["event_seq"] = max(int(snapshot["record"].get("event_seq", 0) or 0), event_seq)

    def _apply_plan_block_mutation(
        self,
        *,
        snapshot: ConversationSnapshot,
        assistant_message_id: str,
        plan_block_part: ConversationMessagePart,
        event_seq: int,
    ) -> None:
        message = self._find_message(snapshot["messages"], assistant_message_id)
        if message is None:
            raise KeyError(f"Unknown assistant message_id: {assistant_message_id}")
        self._upsert_part_in_message(message["parts"], plan_block_part)
        message["updated_at"] = plan_block_part["updated_at"]
        snapshot["record"]["current_runtime_mode"] = "execute"
        snapshot["record"]["event_seq"] = max(int(snapshot["record"].get("event_seq", 0) or 0), event_seq)

    def _apply_interactive_messages_mutation(
        self,
        *,
        snapshot: ConversationSnapshot,
        event_seq: int,
        request_message: ConversationMessage,
        response_message: ConversationMessage | None,
        assistant_message_id: str,
    ) -> None:
        before_message_id = assistant_message_id or None
        self._upsert_message_before_target(snapshot["messages"], request_message, before_message_id)
        if response_message is not None:
            self._upsert_message_before_target(snapshot["messages"], response_message, before_message_id)
        snapshot["record"]["current_runtime_mode"] = "execute"
        snapshot["record"]["status"] = "active"
        snapshot["record"]["event_seq"] = max(int(snapshot["record"].get("event_seq", 0) or 0), event_seq)
        snapshot["record"]["updated_at"] = (
            response_message["updated_at"] if response_message is not None else request_message["updated_at"]
        )

    def _apply_send_start_mutation(
        self,
        *,
        snapshot: ConversationSnapshot,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
        stream_id: str,
        event_seq: int,
    ) -> None:
        snapshot["messages"].append(copy.deepcopy(user_message))
        snapshot["messages"].append(copy.deepcopy(assistant_message))
        snapshot["record"]["status"] = "active"
        snapshot["record"]["current_runtime_mode"] = "execute"
        snapshot["record"]["active_stream_id"] = stream_id
        snapshot["record"]["event_seq"] = event_seq

    def _build_send_start_persistence_task(
        self,
        *,
        project_id: str,
        conversation_id: str,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
        stream_id: str,
        event_seq: int,
    ) -> _PersistenceTask:
        def run() -> None:
            self._storage.conversation_store.mutate_conversation(
                project_id,
                conversation_id,
                lambda snapshot: self._apply_send_start_mutation(
                    snapshot=snapshot,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    stream_id=stream_id,
                    event_seq=event_seq,
                ),
            )

        return _PersistenceTask(run=run)

    def _repair_interrupted_send_start_state(
        self,
        *,
        project_id: str,
        conversation_id: str,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
        event_seq: int,
        error_message: str,
    ) -> ConversationSnapshot:
        return self._storage.conversation_store.mutate_conversation(
            project_id,
            conversation_id,
            lambda snapshot: self._apply_interrupted_send_start_mutation(
                snapshot=snapshot,
                user_message=user_message,
                assistant_message=assistant_message,
                event_seq=event_seq,
                error_message=error_message,
            ),
        )

    def _apply_interrupted_send_start_mutation(
        self,
        *,
        snapshot: ConversationSnapshot,
        user_message: ConversationMessage,
        assistant_message: ConversationMessage,
        event_seq: int,
        error_message: str,
    ) -> None:
        interrupted_at = iso_now()
        repaired_user_message = copy.deepcopy(user_message)
        repaired_assistant_message = copy.deepcopy(assistant_message)
        repaired_assistant_message["status"] = "interrupted"
        repaired_assistant_message["error"] = error_message
        repaired_assistant_message["updated_at"] = interrupted_at
        for part in repaired_assistant_message["parts"]:
            if part["part_type"] == "assistant_text":
                part["status"] = "interrupted"
                part["updated_at"] = interrupted_at
        self._upsert_message_in_snapshot(snapshot["messages"], repaired_user_message)
        self._upsert_message_in_snapshot(snapshot["messages"], repaired_assistant_message)
        snapshot["record"]["status"] = "interrupted"
        snapshot["record"]["current_runtime_mode"] = "execute"
        snapshot["record"]["active_stream_id"] = None
        snapshot["record"]["event_seq"] = max(int(snapshot["record"].get("event_seq", 0) or 0), event_seq)

    def _apply_orphaned_execution_recovery_mutation(
        self,
        *,
        snapshot: ConversationSnapshot,
        error_message: str,
    ) -> None:
        snapshot["record"]["status"] = "interrupted"
        snapshot["record"]["active_stream_id"] = None
        self._mark_latest_in_flight_assistant_message_interrupted(
            snapshot=snapshot,
            error_message=error_message,
        )

    def _mark_latest_in_flight_assistant_message_interrupted(
        self,
        *,
        snapshot: ConversationSnapshot,
        error_message: str,
    ) -> None:
        latest_message = self._find_latest_in_flight_assistant_message(snapshot["messages"])
        if latest_message is None:
            return

        interrupted_at = iso_now()
        latest_message["status"] = "interrupted"
        latest_message["error"] = error_message
        latest_message["updated_at"] = interrupted_at
        latest_part = self._find_latest_assistant_text_part(latest_message)
        if latest_part is not None and latest_part["status"] in {"pending", "streaming"}:
            latest_part["status"] = "interrupted"
            latest_part["updated_at"] = interrupted_at

    def _upsert_message_in_snapshot(
        self,
        messages: list[ConversationMessage],
        next_message: ConversationMessage,
    ) -> None:
        for index, existing_message in enumerate(messages):
            if existing_message["message_id"] == next_message["message_id"]:
                messages[index] = copy.deepcopy(next_message)
                return
        messages.append(copy.deepcopy(next_message))

    def _upsert_message_before_target(
        self,
        messages: list[ConversationMessage],
        next_message: ConversationMessage,
        before_message_id: str | None,
    ) -> None:
        existing_index: int | None = None
        for index, existing_message in enumerate(messages):
            if existing_message["message_id"] == next_message["message_id"]:
                existing_index = index
                break
        if existing_index is not None:
            messages[existing_index] = copy.deepcopy(next_message)
            return

        insert_at = len(messages)
        if before_message_id:
            for index, existing_message in enumerate(messages):
                if existing_message["message_id"] == before_message_id:
                    insert_at = index
                    break
        messages.insert(insert_at, copy.deepcopy(next_message))

    def _upsert_part_in_message(
        self,
        parts: list[ConversationMessagePart],
        next_part: ConversationMessagePart,
    ) -> None:
        for index, existing_part in enumerate(parts):
            if existing_part["part_id"] == next_part["part_id"]:
                parts[index] = copy.deepcopy(next_part)
                break
        else:
            parts.append(copy.deepcopy(next_part))
        parts.sort(key=lambda part: (int(part.get("order", 0) or 0), str(part.get("part_id") or "")))

    def _build_delta_persistence_task(
        self,
        *,
        project_id: str,
        conversation_id: str,
        assistant_message_id: str,
        assistant_part_id: str,
        full_text: str,
        updated_at: str,
        event_seq: int,
    ) -> _PersistenceTask:
        def run() -> None:
            self._storage.conversation_store.mutate_conversation(
                project_id,
                conversation_id,
                lambda snapshot: self._apply_assistant_text_mutation(
                    snapshot=snapshot,
                    assistant_message_id=assistant_message_id,
                    assistant_part_id=assistant_part_id,
                    full_text=full_text,
                    updated_at=updated_at,
                    event_seq=event_seq,
                    message_status="streaming",
                    part_status="streaming",
                    error_message=None,
                    conversation_status=None,
                    active_stream_id=None,
                    app_server_thread_id=None,
                ),
            )

        return _PersistenceTask(run=run)

    def _build_final_text_persistence_task(
        self,
        *,
        project_id: str,
        conversation_id: str,
        assistant_message_id: str,
        assistant_part_id: str,
        full_text: str,
        updated_at: str,
        event_seq: int,
    ) -> _PersistenceTask:
        def run() -> None:
            self._storage.conversation_store.mutate_conversation(
                project_id,
                conversation_id,
                lambda snapshot: self._apply_assistant_text_mutation(
                    snapshot=snapshot,
                    assistant_message_id=assistant_message_id,
                    assistant_part_id=assistant_part_id,
                    full_text=full_text,
                    updated_at=updated_at,
                    event_seq=event_seq,
                    message_status="completed",
                    part_status="completed",
                    error_message=None,
                    conversation_status=None,
                    active_stream_id=None,
                    app_server_thread_id=None,
                ),
            )

        return _PersistenceTask(run=run)

    def _build_completion_persistence_task(
        self,
        *,
        project_id: str,
        conversation_id: str,
        assistant_message_id: str,
        assistant_part_id: str,
        full_text: str,
        updated_at: str,
        event_seq: int,
        status: str,
        error_message: str | None,
        app_server_thread_id: str | None,
        done_event: threading.Event,
        error_holder: list[BaseException],
    ) -> _PersistenceTask:
        def run() -> None:
            self._storage.conversation_store.mutate_conversation(
                project_id,
                conversation_id,
                lambda snapshot: self._apply_assistant_text_mutation(
                    snapshot=snapshot,
                    assistant_message_id=assistant_message_id,
                    assistant_part_id=assistant_part_id,
                    full_text=full_text,
                    updated_at=updated_at,
                    event_seq=event_seq,
                    message_status="completed" if status == "completed" else "error",
                    part_status="completed" if status == "completed" else "error",
                    error_message=error_message,
                    conversation_status=status,
                    active_stream_id=None,
                    app_server_thread_id=app_server_thread_id,
                ),
            )

        return _PersistenceTask(run=run, done_event=done_event, error_holder=error_holder)

    def _apply_assistant_text_mutation(
        self,
        *,
        snapshot: ConversationSnapshot,
        assistant_message_id: str,
        assistant_part_id: str,
        full_text: str,
        updated_at: str,
        event_seq: int,
        message_status: str,
        part_status: str,
        error_message: str | None,
        conversation_status: str | None,
        active_stream_id: str | None,
        app_server_thread_id: str | None,
    ) -> None:
        message = self._find_message(snapshot["messages"], assistant_message_id)
        if message is None:
            raise KeyError(f"Unknown assistant message_id: {assistant_message_id}")
        part = self._find_part(message["parts"], assistant_part_id)
        if part is None:
            raise KeyError(f"Unknown assistant part_id: {assistant_part_id}")
        part["payload"] = {"text": full_text}
        part["status"] = part_status
        part["updated_at"] = updated_at
        message["status"] = message_status
        message["error"] = error_message
        message["updated_at"] = updated_at
        message["usage"] = None
        snapshot["record"]["current_runtime_mode"] = "execute"
        snapshot["record"]["event_seq"] = max(int(snapshot["record"].get("event_seq", 0) or 0), event_seq)
        if conversation_status is not None:
            snapshot["record"]["status"] = conversation_status
            snapshot["record"]["active_stream_id"] = active_stream_id
        if app_server_thread_id:
            snapshot["record"]["app_server_thread_id"] = app_server_thread_id

    def _find_message(
        self,
        messages: list[ConversationMessage],
        message_id: str,
    ) -> ConversationMessage | None:
        for message in messages:
            if message["message_id"] == message_id:
                return message
        return None

    def _find_part(
        self,
        parts: list[ConversationMessagePart],
        part_id: str,
    ) -> ConversationMessagePart | None:
        for part in parts:
            if part["part_id"] == part_id:
                return part
        return None

    def _find_latest_in_flight_assistant_message(
        self,
        messages: list[ConversationMessage],
    ) -> ConversationMessage | None:
        for message in reversed(messages):
            if message["role"] != "assistant":
                continue
            if message["status"] in {"pending", "streaming"}:
                return message
            latest_part = self._find_latest_assistant_text_part(message)
            if latest_part is not None and latest_part["status"] in {"pending", "streaming"}:
                return message
        return None

    def _find_latest_assistant_text_part(
        self,
        message: ConversationMessage,
    ) -> ConversationMessagePart | None:
        for part in reversed(message["parts"]):
            if part["part_type"] == "assistant_text":
                return part
        return None

    def _claim_ownership_locked(
        self,
        session: ProjectCodexSession,
        *,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        app_server_thread_id: str | None,
    ) -> None:
        session.active_streams[conversation_id] = stream_id
        session.active_turns[conversation_id] = turn_id
        if app_server_thread_id:
            existing = session.loaded_runtime_threads.get(app_server_thread_id)
            if existing is None:
                session.loaded_runtime_threads[app_server_thread_id] = RuntimeThreadState(
                    thread_id=app_server_thread_id,
                    last_used_at=iso_now(),
                    active_turn_id=turn_id,
                    status="active",
                )
            else:
                existing.active_turn_id = turn_id
                existing.status = "active"
                existing.last_used_at = iso_now()

    def _clear_ownership_locked(
        self,
        session: ProjectCodexSession,
        *,
        project_id: str,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
        app_server_thread_id: str | None,
    ) -> None:
        if not self._owns_turn_locked(session, conversation_id, stream_id, turn_id):
            return
        session.active_streams.pop(conversation_id, None)
        session.active_turns.pop(conversation_id, None)
        if app_server_thread_id:
            existing = session.loaded_runtime_threads.get(app_server_thread_id)
            if existing is None:
                session.loaded_runtime_threads[app_server_thread_id] = RuntimeThreadState(
                    thread_id=app_server_thread_id,
                    last_used_at=iso_now(),
                    active_turn_id=None,
                    status="idle",
                )
            else:
                existing.active_turn_id = None
                existing.status = "idle"
                existing.last_used_at = iso_now()
        with self._live_state_lock:
            self._live_state.pop((project_id, conversation_id), None)

    def _owns_turn_locked(
        self,
        session: ProjectCodexSession,
        conversation_id: str,
        stream_id: str,
        turn_id: str,
    ) -> bool:
        return (
            session.active_streams.get(conversation_id) == stream_id
            and session.active_turns.get(conversation_id) == turn_id
        )

    def _ensure_live_state_locked(
        self,
        project_id: str,
        conversation_id: str,
        *,
        durable_event_seq: int,
        assistant_text: str | None = None,
    ) -> _LiveConversationState:
        with self._live_state_lock:
            key = (project_id, conversation_id)
            state = self._live_state.get(key)
            if state is None:
                state = _LiveConversationState(
                    event_seq=max(0, durable_event_seq),
                    assistant_text=assistant_text or "",
                )
                self._live_state[key] = state
            elif assistant_text is not None and not state.assistant_text:
                state.assistant_text = assistant_text
            return state

    def _peek_live_event_seq_locked(self, project_id: str, conversation_id: str) -> int:
        with self._live_state_lock:
            state = self._live_state.get((project_id, conversation_id))
            return state.event_seq if state is not None else 0

    def _resolve_passive_part_order_locked(
        self,
        live_state: _LiveConversationState,
        stable_key: str,
    ) -> int:
        order = live_state.passive_part_orders.get(stable_key)
        if order is not None:
            return order
        order = live_state.next_passive_part_order
        live_state.passive_part_orders[stable_key] = order
        live_state.next_passive_part_order += 1
        return order

    def _allocate_event_seq_locked(self, project_id: str, conversation_id: str) -> int:
        live_state = self._ensure_live_state_locked(project_id, conversation_id, durable_event_seq=0)
        live_state.event_seq += 1
        return live_state.event_seq

    def _assert_persistence_handoff_available(self) -> None:
        with self._worker_guard:
            if self._worker_stopped or not self._worker_thread.is_alive():
                raise ConversationPersistenceUnavailable()

    def _enqueue_persistence_task(self, task: _PersistenceTask) -> None:
        self._persistence_queue.put(task)

    def _persistence_worker(self) -> None:
        while True:
            item = self._persistence_queue.get()
            if item is self._persistence_stop:
                self._persistence_queue.task_done()
                return
            task = item
            try:
                task.run()
            except BaseException as exc:  # noqa: BLE001
                logger.exception("Conversation persistence task failed")
                if task.error_holder is not None:
                    task.error_holder.append(exc)
            finally:
                if task.done_event is not None:
                    task.done_event.set()
                self._persistence_queue.task_done()
