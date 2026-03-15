from __future__ import annotations

import copy

from backend.config.app_config import AppPaths
from backend.conversation.contracts import (
    CONVERSATION_SCHEMA_VERSION,
    ConversationMessage,
    ConversationRuntimeMode,
    ConversationSnapshot,
    ConversationState,
    ThreadType,
    conversation_scope_key,
    make_conversation_record,
)
from backend.storage.file_utils import atomic_write_json, iso_now, load_json
from backend.storage.project_ids import normalize_project_id
from backend.storage.project_locks import ProjectLockRegistry


def _default_conversation_state() -> ConversationState:
    return {
        "schema_version": CONVERSATION_SCHEMA_VERSION,
        "scope_index": {},
        "conversations": {},
    }


class ConversationStore:
    def __init__(self, paths: AppPaths, lock_registry: ProjectLockRegistry) -> None:
        self._paths = paths
        self._lock_registry = lock_registry

    def _conversation_state_path(self, project_id: str):
        normalized = normalize_project_id(project_id)
        return self._paths.projects_root / normalized / "conversation_state.json"

    def project_lock(self, project_id: str):
        return self._lock_registry.for_project(project_id)

    def read_conversation_state(self, project_id: str) -> ConversationState:
        with self.project_lock(project_id):
            return self._read_conversation_state_unlocked(project_id)

    def write_conversation_state(self, project_id: str, payload: ConversationState) -> ConversationState:
        with self.project_lock(project_id):
            self._write_conversation_state_unlocked(project_id, payload)
            return copy.deepcopy(payload)

    def get_conversation(self, project_id: str, conversation_id: str) -> ConversationSnapshot | None:
        with self.project_lock(project_id):
            state = self._read_conversation_state_unlocked(project_id)
            snapshot = state["conversations"].get(conversation_id)
            return copy.deepcopy(snapshot) if snapshot else None

    def get_conversation_by_scope(
        self,
        project_id: str,
        node_id: str,
        thread_type: ThreadType,
    ) -> ConversationSnapshot | None:
        with self.project_lock(project_id):
            state = self._read_conversation_state_unlocked(project_id)
            scope_key = conversation_scope_key(project_id, node_id, thread_type)
            conversation_id = state["scope_index"].get(scope_key)
            if conversation_id is None:
                return None
            snapshot = state["conversations"].get(conversation_id)
            return copy.deepcopy(snapshot) if snapshot else None

    def get_or_create_conversation(
        self,
        project_id: str,
        node_id: str,
        thread_type: ThreadType,
        current_runtime_mode: ConversationRuntimeMode,
    ) -> ConversationSnapshot:
        with self.project_lock(project_id):
            state = self._read_conversation_state_unlocked(project_id)
            scope_key = conversation_scope_key(project_id, node_id, thread_type)
            conversation_id = state["scope_index"].get(scope_key)

            if conversation_id is not None and conversation_id in state["conversations"]:
                return copy.deepcopy(state["conversations"][conversation_id])

            record = make_conversation_record(
                project_id=project_id,
                node_id=node_id,
                thread_type=thread_type,
                current_runtime_mode=current_runtime_mode,
            )
            snapshot: ConversationSnapshot = {
                "record": record,
                "messages": [],
            }
            state["scope_index"][scope_key] = record["conversation_id"]
            state["conversations"][record["conversation_id"]] = copy.deepcopy(snapshot)
            self._write_conversation_state_unlocked(project_id, state)
            return copy.deepcopy(snapshot)

    def upsert_snapshot(self, project_id: str, snapshot: ConversationSnapshot) -> ConversationSnapshot:
        with self.project_lock(project_id):
            state = self._read_conversation_state_unlocked(project_id)
            record = copy.deepcopy(snapshot["record"])
            record["updated_at"] = iso_now()
            copied_snapshot: ConversationSnapshot = {
                "record": record,
                "messages": copy.deepcopy(snapshot.get("messages", [])),
            }
            scope_key = conversation_scope_key(
                record["project_id"],
                record["node_id"],
                record["thread_type"],
            )
            state["scope_index"][scope_key] = record["conversation_id"]
            state["conversations"][record["conversation_id"]] = copied_snapshot
            self._write_conversation_state_unlocked(project_id, state)
            return copy.deepcopy(copied_snapshot)

    def upsert_message(
        self,
        project_id: str,
        conversation_id: str,
        message: ConversationMessage,
    ) -> ConversationMessage:
        with self.project_lock(project_id):
            state = self._read_conversation_state_unlocked(project_id)
            snapshot = state["conversations"].get(conversation_id)
            if snapshot is None:
                raise KeyError(f"Unknown conversation_id: {conversation_id}")

            next_message = copy.deepcopy(message)
            next_message["conversation_id"] = conversation_id
            next_message["updated_at"] = iso_now()

            messages = snapshot["messages"]
            for index, existing in enumerate(messages):
                if existing["message_id"] == next_message["message_id"]:
                    messages[index] = next_message
                    break
            else:
                messages.append(next_message)

            snapshot["record"]["updated_at"] = iso_now()
            self._write_conversation_state_unlocked(project_id, state)
            return copy.deepcopy(next_message)

    def set_active_stream(
        self,
        project_id: str,
        conversation_id: str,
        stream_id: str | None,
    ) -> ConversationSnapshot:
        with self.project_lock(project_id):
            state = self._read_conversation_state_unlocked(project_id)
            snapshot = state["conversations"].get(conversation_id)
            if snapshot is None:
                raise KeyError(f"Unknown conversation_id: {conversation_id}")
            snapshot["record"]["active_stream_id"] = stream_id
            snapshot["record"]["updated_at"] = iso_now()
            self._write_conversation_state_unlocked(project_id, state)
            return copy.deepcopy(snapshot)

    def advance_event_seq(
        self,
        project_id: str,
        conversation_id: str,
        event_seq: int,
    ) -> ConversationSnapshot:
        with self.project_lock(project_id):
            state = self._read_conversation_state_unlocked(project_id)
            snapshot = state["conversations"].get(conversation_id)
            if snapshot is None:
                raise KeyError(f"Unknown conversation_id: {conversation_id}")
            current_event_seq = int(snapshot["record"].get("event_seq", 0) or 0)
            if event_seq > current_event_seq:
                snapshot["record"]["event_seq"] = event_seq
                snapshot["record"]["updated_at"] = iso_now()
                self._write_conversation_state_unlocked(project_id, state)
            return copy.deepcopy(snapshot)

    def _read_conversation_state_unlocked(self, project_id: str) -> ConversationState:
        raw = load_json(self._conversation_state_path(project_id), default=None)
        if not isinstance(raw, dict):
            return _default_conversation_state()

        state = _default_conversation_state()
        state["schema_version"] = int(raw.get("schema_version", CONVERSATION_SCHEMA_VERSION) or CONVERSATION_SCHEMA_VERSION)
        scope_index = raw.get("scope_index", {})
        conversations = raw.get("conversations", {})
        state["scope_index"] = copy.deepcopy(scope_index) if isinstance(scope_index, dict) else {}
        state["conversations"] = copy.deepcopy(conversations) if isinstance(conversations, dict) else {}
        return state

    def _write_conversation_state_unlocked(self, project_id: str, payload: ConversationState) -> None:
        atomic_write_json(self._conversation_state_path(project_id), payload)
