from __future__ import annotations

import copy
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable

from backend.conversation.contracts import (
    ConversationEventEnvelope,
    ConversationMessage,
    ConversationMessagePart,
    ConversationSnapshot,
    make_conversation_message,
    make_conversation_part,
)
from backend.errors.app_errors import ChatTurnAlreadyActive, ConversationStreamMismatch, NodeNotFound, NodeUpdateNotAllowed
from backend.services.codex_session_manager import CodexSessionManager, ProjectCodexSession, RuntimeThreadState
from backend.services.conversation_context_builder import ConversationContextBuilder
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.conversation_broker import ConversationEventBroker

logger = logging.getLogger(__name__)


@dataclass
class _LiveConversationState:
    event_seq: int
    assistant_text: str = ""


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
        session_manager: CodexSessionManager,
        event_broker: ConversationEventBroker,
        context_builder: ConversationContextBuilder,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._session_manager = session_manager
        self._event_broker = event_broker
        self._context_builder = context_builder
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

        self._storage.conversation_store.mutate_conversation(
            project_id,
            conversation_id,
            lambda snapshot: self._apply_send_start_mutation(
                snapshot=snapshot,
                user_message=user_message,
                assistant_message=assistant_message,
                stream_id=stream_id,
                event_seq=assistant_event_seq,
            ),
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

        request_context = self._context_builder.build_execution_request(
            project_id=project_id,
            snapshot=project_snapshot,
            node=node,
            state=state,
            user_message=text,
        )
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
            if final_text:
                live_state.assistant_text = final_text
            full_text = live_state.assistant_text
            final_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)
            completion_event_seq = self._allocate_event_seq_locked(project_id, conversation_id)

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

    def _allocate_event_seq_locked(self, project_id: str, conversation_id: str) -> int:
        live_state = self._ensure_live_state_locked(project_id, conversation_id, durable_event_seq=0)
        live_state.event_seq += 1
        return live_state.event_seq

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
