from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from backend.storage.file_utils import iso_now, new_id

CONVERSATION_SCHEMA_VERSION = 1

ThreadType = Literal["ask", "planning", "execution"]
ConversationRuntimeMode = Literal["ask", "planning", "plan", "execute"]
ConversationStatus = Literal["idle", "active", "completed", "interrupted", "cancelled", "error"]
MessageRole = Literal["system", "user", "assistant", "tool"]
MessageStatus = Literal[
    "pending",
    "streaming",
    "completed",
    "error",
    "cancelled",
    "interrupted",
    "superseded",
]
MessagePartType = Literal[
    "user_text",
    "assistant_text",
    "reasoning",
    "tool_call",
    "tool_result",
    "plan_block",
    "plan_step_update",
    "approval_request",
    "user_input_request",
    "user_input_response",
    "diff_summary",
    "file_change_summary",
    "status_block",
]
ConversationEventType = Literal[
    "message_created",
    "assistant_text_delta",
    "assistant_text_final",
    "reasoning_state",
    "tool_call_start",
    "tool_call_update",
    "tool_call_finish",
    "tool_result",
    "plan_block",
    "plan_step_status_change",
    "approval_request",
    "request_user_input",
    "request_resolved",
    "user_input_resolved",
    "diff_summary",
    "file_change_summary",
    "completion_status",
    "stream_interrupted",
    "stream_cancelled",
]


class ConversationLineage(TypedDict, total=False):
    parent_message_id: str | None
    retry_of_message_id: str | None
    continue_of_message_id: str | None
    regenerate_of_message_id: str | None
    superseded_by_message_id: str | None


class ConversationMessagePart(TypedDict):
    part_id: str
    part_type: MessagePartType
    status: MessageStatus
    order: int
    item_key: str | None
    created_at: str
    updated_at: str
    payload: dict[str, Any]


class ConversationMessage(TypedDict):
    message_id: str
    conversation_id: str
    turn_id: str
    role: MessageRole
    runtime_mode: ConversationRuntimeMode
    status: MessageStatus
    created_at: str
    updated_at: str
    lineage: ConversationLineage
    usage: dict[str, Any] | None
    error: str | None
    parts: list[ConversationMessagePart]


class ConversationRecord(TypedDict):
    conversation_id: str
    project_id: str
    node_id: str
    thread_type: ThreadType
    app_server_thread_id: str | None
    current_runtime_mode: ConversationRuntimeMode
    status: ConversationStatus
    active_stream_id: str | None
    event_seq: int
    created_at: str
    updated_at: str


class ConversationSnapshot(TypedDict):
    record: ConversationRecord
    messages: list[ConversationMessage]


class ConversationState(TypedDict):
    schema_version: int
    scope_index: dict[str, str]
    conversations: dict[str, ConversationSnapshot]


class ConversationEventEnvelope(TypedDict):
    event_type: ConversationEventType
    conversation_id: str
    stream_id: str
    event_seq: int
    created_at: str
    payload: dict[str, Any]
    turn_id: NotRequired[str]
    message_id: NotRequired[str]
    item_id: NotRequired[str]


def conversation_scope_key(project_id: str, node_id: str, thread_type: ThreadType) -> str:
    return f"{project_id}:{node_id}:{thread_type}"


def make_conversation_record(
    *,
    project_id: str,
    node_id: str,
    thread_type: ThreadType,
    current_runtime_mode: ConversationRuntimeMode,
    conversation_id: str | None = None,
    app_server_thread_id: str | None = None,
    status: ConversationStatus = "idle",
    active_stream_id: str | None = None,
    event_seq: int = 0,
) -> ConversationRecord:
    timestamp = iso_now()
    return {
        "conversation_id": conversation_id or new_id("conv"),
        "project_id": project_id,
        "node_id": node_id,
        "thread_type": thread_type,
        "app_server_thread_id": app_server_thread_id,
        "current_runtime_mode": current_runtime_mode,
        "status": status,
        "active_stream_id": active_stream_id,
        "event_seq": event_seq,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def make_conversation_part(
    *,
    part_type: MessagePartType,
    order: int,
    payload: dict[str, Any],
    status: MessageStatus = "completed",
    part_id: str | None = None,
    item_key: str | None = None,
) -> ConversationMessagePart:
    timestamp = iso_now()
    return {
        "part_id": part_id or new_id("part"),
        "part_type": part_type,
        "status": status,
        "order": order,
        "item_key": item_key,
        "created_at": timestamp,
        "updated_at": timestamp,
        "payload": payload,
    }


def make_conversation_message(
    *,
    conversation_id: str,
    turn_id: str,
    role: MessageRole,
    runtime_mode: ConversationRuntimeMode,
    parts: list[ConversationMessagePart] | None = None,
    message_id: str | None = None,
    status: MessageStatus = "completed",
    lineage: ConversationLineage | None = None,
    usage: dict[str, Any] | None = None,
    error: str | None = None,
) -> ConversationMessage:
    timestamp = iso_now()
    return {
        "message_id": message_id or new_id("msg"),
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "role": role,
        "runtime_mode": runtime_mode,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "lineage": lineage or {},
        "usage": usage,
        "error": error,
        "parts": list(parts or []),
    }
