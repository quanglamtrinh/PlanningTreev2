from __future__ import annotations

import copy
from typing import Any, Literal, NotRequired, TypedDict, cast

from backend.storage.file_utils import iso_now

ThreadRoleV3 = Literal["ask_planning", "execution", "audit"]
ProcessingStateV3 = Literal["idle", "running", "waiting_user_input", "failed"]
ItemStatusV3 = Literal[
    "pending",
    "in_progress",
    "completed",
    "failed",
    "cancelled",
    "requested",
    "answer_submitted",
    "answered",
    "stale",
]
ItemSourceV3 = Literal["upstream", "backend", "local"]
ItemToneV3 = Literal["neutral", "info", "success", "warning", "danger", "muted"]
ThreadActorModeV3 = Literal["off", "shadow", "on"]
MiniJournalBoundaryTypeV3 = Literal[
    "turn_completed",
    "turn_failed",
    "waiting_user_input",
    "eviction",
    "timer_checkpoint",
]

THREAD_ROLES_V3: tuple[ThreadRoleV3, ...] = ("ask_planning", "execution", "audit")
PROCESSING_STATES_V3: tuple[ProcessingStateV3, ...] = ("idle", "running", "waiting_user_input", "failed")
ITEM_STATUSES_V3: tuple[ItemStatusV3, ...] = (
    "pending",
    "in_progress",
    "completed",
    "failed",
    "cancelled",
    "requested",
    "answer_submitted",
    "answered",
    "stale",
)
ITEM_SOURCES_V3: tuple[ItemSourceV3, ...] = ("upstream", "backend", "local")
ITEM_TONES_V3: tuple[ItemToneV3, ...] = ("neutral", "info", "success", "warning", "danger", "muted")
THREAD_ACTOR_MODES_V3: tuple[ThreadActorModeV3, ...] = ("off", "shadow", "on")
MINI_JOURNAL_BOUNDARY_TYPES_V3: tuple[MiniJournalBoundaryTypeV3, ...] = (
    "turn_completed",
    "turn_failed",
    "waiting_user_input",
    "eviction",
    "timer_checkpoint",
)


class MiniJournalRecordV3(TypedDict):
    journalSeq: int
    projectId: str
    nodeId: str
    threadRole: str
    threadId: str
    turnId: str | None
    eventIdStart: int
    eventIdEnd: int
    boundaryType: MiniJournalBoundaryTypeV3
    snapshotVersionAtWrite: int
    createdAt: str


class ItemBaseV3(TypedDict):
    id: str
    kind: Literal["message", "reasoning", "tool", "explore", "userInput", "review", "diff", "status", "error"]
    threadId: str
    turnId: str | None
    sequence: int
    createdAt: str
    updatedAt: str
    status: ItemStatusV3
    source: ItemSourceV3
    tone: ItemToneV3
    metadata: dict[str, Any]


class MessageItemV3(ItemBaseV3):
    kind: Literal["message"]
    role: Literal["user", "assistant", "system"]
    text: str
    format: Literal["markdown"]


class ReasoningItemV3(ItemBaseV3):
    kind: Literal["reasoning"]
    summaryText: str
    detailText: str | None


class ToolOutputFileV3(TypedDict):
    path: str
    changeType: Literal["created", "updated", "deleted"]
    summary: str | None
    kind: NotRequired[Literal["add", "modify", "delete"]]
    diff: NotRequired[str | None]


class ToolItemV3(ItemBaseV3):
    kind: Literal["tool"]
    toolType: Literal["commandExecution", "fileChange", "generic"]
    title: str
    toolName: str | None
    callId: str | None
    argumentsText: str | None
    outputText: str
    outputFiles: list[ToolOutputFileV3]
    exitCode: int | None


class ExploreItemV3(ItemBaseV3):
    kind: Literal["explore"]
    title: str | None
    text: str


class UserInputAnswerV3(TypedDict):
    questionId: str
    value: str
    label: str | None


class UserInputQuestionOptionV3(TypedDict):
    label: str
    description: str | None


class UserInputQuestionV3(TypedDict):
    id: str
    header: str | None
    prompt: str
    inputType: Literal["single_select", "multi_select", "text"]
    options: list[UserInputQuestionOptionV3]


class UserInputItemV3(ItemBaseV3):
    kind: Literal["userInput"]
    requestId: str
    title: str | None
    questions: list[UserInputQuestionV3]
    answers: list[UserInputAnswerV3]
    requestedAt: str
    resolvedAt: str | None


class ReviewItemV3(ItemBaseV3):
    kind: Literal["review"]
    title: str | None
    text: str
    disposition: Literal["approved", "changes_requested", "commented"] | None


class DiffFileV3(TypedDict):
    path: str
    changeType: Literal["created", "updated", "deleted"]
    summary: str | None
    patchText: str | None


class DiffChangeV3(TypedDict):
    path: str
    kind: Literal["add", "modify", "delete"]
    diff: str | None
    summary: str | None


class DiffItemV3(ItemBaseV3):
    kind: Literal["diff"]
    title: str | None
    summaryText: str | None
    changes: list[DiffChangeV3]
    files: list[DiffFileV3]


class StatusItemV3(ItemBaseV3):
    kind: Literal["status"]
    code: str
    label: str
    detail: str | None


class ErrorItemV3(ItemBaseV3):
    kind: Literal["error"]
    code: str
    title: str
    message: str
    recoverable: bool
    relatedItemId: str | None


ConversationItemV3 = (
    MessageItemV3
    | ReasoningItemV3
    | ToolItemV3
    | ExploreItemV3
    | UserInputItemV3
    | ReviewItemV3
    | DiffItemV3
    | StatusItemV3
    | ErrorItemV3
)


class PendingUserInputRequestV3(TypedDict):
    requestId: str
    itemId: str
    threadId: str
    turnId: str | None
    status: Literal["requested", "answer_submitted", "answered", "stale"]
    createdAt: str
    submittedAt: str | None
    resolvedAt: str | None
    answers: list[UserInputAnswerV3]


class PlanReadySignalV3(TypedDict):
    planItemId: str | None
    revision: int | None
    ready: bool
    failed: bool


class UiSignalsV3(TypedDict):
    planReady: PlanReadySignalV3
    activeUserInputRequests: list[PendingUserInputRequestV3]


class ThreadSnapshotV3(TypedDict):
    projectId: str
    nodeId: str
    threadRole: ThreadRoleV3
    threadId: str | None
    activeTurnId: str | None
    processingState: ProcessingStateV3
    snapshotVersion: int
    createdAt: str
    updatedAt: str
    items: list[ConversationItemV3]
    uiSignals: UiSignalsV3


class MessagePatchV3(TypedDict, total=False):
    kind: Literal["message"]
    textAppend: str
    status: ItemStatusV3
    updatedAt: str


class ReasoningPatchV3(TypedDict, total=False):
    kind: Literal["reasoning"]
    summaryTextAppend: str
    detailTextAppend: str
    status: ItemStatusV3
    updatedAt: str


class ToolPatchV3(TypedDict, total=False):
    kind: Literal["tool"]
    title: str
    argumentsText: str | None
    outputTextAppend: str
    outputFilesAppend: list[ToolOutputFileV3]
    outputFilesReplace: list[ToolOutputFileV3]
    exitCode: int | None
    status: ItemStatusV3
    updatedAt: str


class ExplorePatchV3(TypedDict, total=False):
    kind: Literal["explore"]
    title: str | None
    textAppend: str
    status: ItemStatusV3
    updatedAt: str


class UserInputPatchV3(TypedDict, total=False):
    kind: Literal["userInput"]
    answersReplace: list[UserInputAnswerV3]
    resolvedAt: str | None
    status: Literal["requested", "answer_submitted", "answered", "stale"]
    updatedAt: str


class ReviewPatchV3(TypedDict, total=False):
    kind: Literal["review"]
    title: str | None
    textAppend: str
    disposition: Literal["approved", "changes_requested", "commented"] | None
    status: ItemStatusV3
    updatedAt: str


class DiffPatchV3(TypedDict, total=False):
    kind: Literal["diff"]
    title: str | None
    summaryText: str | None
    changesAppend: list[DiffChangeV3]
    changesReplace: list[DiffChangeV3]
    filesAppend: list[DiffFileV3]
    filesReplace: list[DiffFileV3]
    status: ItemStatusV3
    updatedAt: str


class StatusPatchV3(TypedDict, total=False):
    kind: Literal["status"]
    label: str
    detail: str | None
    status: ItemStatusV3
    updatedAt: str


class ErrorPatchV3(TypedDict, total=False):
    kind: Literal["error"]
    message: str
    relatedItemId: str | None
    status: ItemStatusV3
    updatedAt: str


ItemPatchV3 = (
    MessagePatchV3
    | ReasoningPatchV3
    | ToolPatchV3
    | ExplorePatchV3
    | UserInputPatchV3
    | ReviewPatchV3
    | DiffPatchV3
    | StatusPatchV3
    | ErrorPatchV3
)


def default_plan_ready_signal_v3() -> PlanReadySignalV3:
    return {
        "planItemId": None,
        "revision": None,
        "ready": False,
        "failed": False,
    }


def default_ui_signals_v3() -> UiSignalsV3:
    return {
        "planReady": default_plan_ready_signal_v3(),
        "activeUserInputRequests": [],
    }


def _normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value.strip() else None


def _coerce_nonnegative_int(value: Any, *, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return parsed if parsed >= 0 else int(default)


def lane_to_thread_role_v3(value: Any, *, default: ThreadRoleV3 = "ask_planning") -> ThreadRoleV3:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "ask":
            return "ask_planning"
        if normalized in {"execution", "audit"}:
            return cast(ThreadRoleV3, normalized)
    return default


def normalize_thread_role_v3(value: Any, *, default: ThreadRoleV3 = "ask_planning") -> ThreadRoleV3:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in THREAD_ROLES_V3:
            return cast(ThreadRoleV3, normalized)
        if normalized in {"ask", "execution", "audit"}:
            return lane_to_thread_role_v3(normalized, default=default)
    return default


def normalize_processing_state_v3(value: Any, *, default: ProcessingStateV3 = "idle") -> ProcessingStateV3:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in PROCESSING_STATES_V3:
            return cast(ProcessingStateV3, normalized)
    return default


def normalize_item_status_v3(value: Any, *, default: ItemStatusV3 = "pending") -> ItemStatusV3:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in ITEM_STATUSES_V3:
            return cast(ItemStatusV3, normalized)
    return default


def normalize_item_source_v3(value: Any, *, default: ItemSourceV3 = "backend") -> ItemSourceV3:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in ITEM_SOURCES_V3:
            return cast(ItemSourceV3, normalized)
    return default


def normalize_item_tone_v3(value: Any, *, default: ItemToneV3 = "neutral") -> ItemToneV3:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in ITEM_TONES_V3:
            return cast(ItemToneV3, normalized)
    return default


def _normalize_tool_kind(value: Any, *, default: Literal["add", "modify", "delete"] = "modify") -> Literal["add", "modify", "delete"]:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"add", "create", "created", "new"}:
            return "add"
        if normalized in {"delete", "deleted", "remove", "removed"}:
            return "delete"
        if normalized in {"modify", "modified", "update", "updated", "change", "changed"}:
            return "modify"
    return default


def _tool_kind_to_change_type(kind: str) -> Literal["created", "updated", "deleted"]:
    if kind == "add":
        return "created"
    if kind == "delete":
        return "deleted"
    return "updated"


def normalize_tool_output_file_v3(raw: Any) -> ToolOutputFileV3 | None:
    if not isinstance(raw, dict):
        return None
    path = _normalize_optional_string(raw.get("path"))
    if not path:
        return None
    kind = _normalize_tool_kind(raw.get("kind") or raw.get("changeKind") or raw.get("change_kind"))
    raw_change_type = str(raw.get("changeType") or raw.get("change_type") or "").strip()
    if raw_change_type not in {"created", "updated", "deleted"}:
        raw_change_type = _tool_kind_to_change_type(kind)
    output_file: ToolOutputFileV3 = {
        "path": path,
        "changeType": cast(Any, raw_change_type),
        "summary": _normalize_optional_string(raw.get("summary")),
    }
    if raw.get("kind") is not None:
        output_file["kind"] = kind
    diff_text = _normalize_optional_text(raw.get("diff") if "diff" in raw else raw.get("patchText") or raw.get("patch_text"))
    if diff_text is not None:
        output_file["diff"] = diff_text
    return output_file


def normalize_user_input_answer_v3(raw: Any) -> UserInputAnswerV3 | None:
    if not isinstance(raw, dict):
        return None
    question_id = _normalize_optional_string(raw.get("questionId") or raw.get("question_id"))
    value = _normalize_optional_string(raw.get("value"))
    if not question_id or value is None:
        return None
    return {
        "questionId": question_id,
        "value": value,
        "label": _normalize_optional_string(raw.get("label")),
    }


def _normalize_user_input_question_option_v3(raw: Any) -> UserInputQuestionOptionV3 | None:
    if not isinstance(raw, dict):
        return None
    label = _normalize_optional_string(raw.get("label"))
    if not label:
        return None
    return {
        "label": label,
        "description": _normalize_optional_string(raw.get("description")),
    }


def _normalize_user_input_question_v3(raw: Any) -> UserInputQuestionV3 | None:
    if not isinstance(raw, dict):
        return None
    question_id = _normalize_optional_string(raw.get("id"))
    prompt = _normalize_optional_string(raw.get("prompt") or raw.get("question"))
    if not question_id or prompt is None:
        return None
    input_type = str(raw.get("inputType") or raw.get("input_type") or "text").strip()
    if input_type not in {"single_select", "multi_select", "text"}:
        input_type = "text"
    options: list[UserInputQuestionOptionV3] = []
    if isinstance(raw.get("options"), list):
        for option in raw["options"]:
            normalized_option = _normalize_user_input_question_option_v3(option)
            if normalized_option is not None:
                options.append(normalized_option)
    return {
        "id": question_id,
        "header": _normalize_optional_string(raw.get("header")),
        "prompt": prompt,
        "inputType": cast(Any, input_type),
        "options": options,
    }


def _normalize_diff_change_v3(raw: Any) -> DiffChangeV3 | None:
    if not isinstance(raw, dict):
        return None
    path = _normalize_optional_string(raw.get("path"))
    if not path:
        return None
    kind = _normalize_tool_kind(
        raw.get("kind")
        or raw.get("changeKind")
        or raw.get("change_kind")
        or raw.get("changeType")
        or raw.get("change_type")
    )
    diff_text = _normalize_optional_text(raw.get("diff") if "diff" in raw else raw.get("patchText") or raw.get("patch_text"))
    return cast(
        DiffChangeV3,
        {
            "path": path,
            "kind": kind,
            "diff": diff_text,
            "summary": _normalize_optional_string(raw.get("summary")),
        },
    )


def _normalize_diff_file_v3(raw: Any) -> DiffFileV3 | None:
    if not isinstance(raw, dict):
        return None
    path = _normalize_optional_string(raw.get("path"))
    if not path:
        return None
    raw_change_type = str(raw.get("changeType") or raw.get("change_type") or "").strip().lower()
    if raw_change_type not in {"created", "updated", "deleted"}:
        raw_change_type = _tool_kind_to_change_type(_normalize_tool_kind(raw.get("kind")))
    return cast(
        DiffFileV3,
        {
            "path": path,
            "changeType": raw_change_type,
            "summary": _normalize_optional_string(raw.get("summary")),
            "patchText": _normalize_optional_text(raw.get("patchText") or raw.get("patch_text")),
        },
    )


def normalize_conversation_item_v3(raw: Any, *, thread_id: str | None = None) -> ConversationItemV3 | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    if kind not in {"message", "reasoning", "tool", "explore", "userInput", "review", "diff", "status", "error"}:
        return None
    item_id = _normalize_optional_string(raw.get("id"))
    if not item_id:
        return None
    now = iso_now()
    created_at = raw.get("createdAt") if isinstance(raw.get("createdAt"), str) else now
    updated_at = raw.get("updatedAt") if isinstance(raw.get("updatedAt"), str) else created_at
    base = {
        "id": item_id,
        "kind": kind,
        "threadId": _normalize_optional_string(raw.get("threadId")) or thread_id or "",
        "turnId": _normalize_optional_string(raw.get("turnId")),
        "sequence": _coerce_nonnegative_int(raw.get("sequence"), default=0),
        "createdAt": created_at,
        "updatedAt": updated_at,
        "status": normalize_item_status_v3(raw.get("status")),
        "source": normalize_item_source_v3(raw.get("source")),
        "tone": normalize_item_tone_v3(raw.get("tone")),
        "metadata": copy.deepcopy(raw.get("metadata")) if isinstance(raw.get("metadata"), dict) else {},
    }

    if kind == "message":
        role = str(raw.get("role") or "assistant").strip()
        if role not in {"user", "assistant", "system"}:
            role = "assistant"
        return cast(
            ConversationItemV3,
            {
                **base,
                "role": role,
                "text": str(raw.get("text") or ""),
                "format": "markdown",
            },
        )
    if kind == "reasoning":
        return cast(
            ConversationItemV3,
            {
                **base,
                "summaryText": str(raw.get("summaryText") or ""),
                "detailText": _normalize_optional_string(raw.get("detailText")),
            },
        )
    if kind == "tool":
        tool_type = str(raw.get("toolType") or "generic").strip()
        if tool_type not in {"commandExecution", "fileChange", "generic"}:
            tool_type = "generic"
        output_files: list[ToolOutputFileV3] = []
        if isinstance(raw.get("outputFiles"), list):
            for output_file in raw["outputFiles"]:
                normalized_file = normalize_tool_output_file_v3(output_file)
                if normalized_file is not None:
                    output_files.append(normalized_file)
        exit_code = raw.get("exitCode")
        return cast(
            ConversationItemV3,
            {
                **base,
                "toolType": tool_type,
                "title": str(raw.get("title") or ""),
                "toolName": _normalize_optional_string(raw.get("toolName")),
                "callId": _normalize_optional_string(raw.get("callId")),
                "argumentsText": _normalize_optional_string(raw.get("argumentsText")),
                "outputText": str(raw.get("outputText") or ""),
                "outputFiles": output_files,
                "exitCode": int(exit_code) if isinstance(exit_code, int) else None,
            },
        )
    if kind == "explore":
        return cast(
            ConversationItemV3,
            {
                **base,
                "title": _normalize_optional_string(raw.get("title")),
                "text": str(raw.get("text") or ""),
            },
        )
    if kind == "userInput":
        questions: list[UserInputQuestionV3] = []
        if isinstance(raw.get("questions"), list):
            for question in raw["questions"]:
                normalized_question = _normalize_user_input_question_v3(question)
                if normalized_question is not None:
                    questions.append(normalized_question)
        answers: list[UserInputAnswerV3] = []
        if isinstance(raw.get("answers"), list):
            for answer in raw["answers"]:
                normalized_answer = normalize_user_input_answer_v3(answer)
                if normalized_answer is not None:
                    answers.append(normalized_answer)
        return cast(
            ConversationItemV3,
            {
                **base,
                "requestId": _normalize_optional_string(raw.get("requestId")) or item_id,
                "title": _normalize_optional_string(raw.get("title")),
                "questions": questions,
                "answers": answers,
                "requestedAt": raw.get("requestedAt") if isinstance(raw.get("requestedAt"), str) else created_at,
                "resolvedAt": _normalize_optional_string(raw.get("resolvedAt")),
            },
        )
    if kind == "review":
        disposition = raw.get("disposition")
        if disposition not in {"approved", "changes_requested", "commented"}:
            disposition = None
        return cast(
            ConversationItemV3,
            {
                **base,
                "title": _normalize_optional_string(raw.get("title")),
                "text": str(raw.get("text") or ""),
                "disposition": disposition,
            },
        )
    if kind == "diff":
        changes: list[DiffChangeV3] = []
        if isinstance(raw.get("changes"), list):
            for change in raw["changes"]:
                normalized_change = _normalize_diff_change_v3(change)
                if normalized_change is not None:
                    changes.append(normalized_change)
        files: list[DiffFileV3] = []
        if isinstance(raw.get("files"), list):
            for file_item in raw["files"]:
                normalized_file = _normalize_diff_file_v3(file_item)
                if normalized_file is not None:
                    files.append(normalized_file)
        return cast(
            ConversationItemV3,
            {
                **base,
                "title": _normalize_optional_string(raw.get("title")),
                "summaryText": _normalize_optional_string(raw.get("summaryText")),
                "changes": changes,
                "files": files,
            },
        )
    if kind == "status":
        return cast(
            ConversationItemV3,
            {
                **base,
                "code": str(raw.get("code") or ""),
                "label": str(raw.get("label") or ""),
                "detail": _normalize_optional_string(raw.get("detail")),
            },
        )
    return cast(
        ConversationItemV3,
        {
            **base,
            "code": str(raw.get("code") or ""),
            "title": str(raw.get("title") or ""),
            "message": str(raw.get("message") or ""),
            "recoverable": bool(raw.get("recoverable")),
            "relatedItemId": _normalize_optional_string(raw.get("relatedItemId")),
        },
    )


def normalize_pending_user_input_request_v3(
    raw: Any,
    *,
    thread_id: str | None = None,
) -> PendingUserInputRequestV3 | None:
    if not isinstance(raw, dict):
        return None
    request_id = _normalize_optional_string(raw.get("requestId") or raw.get("request_id"))
    item_id = _normalize_optional_string(raw.get("itemId") or raw.get("item_id"))
    if not request_id or not item_id:
        return None
    status = str(raw.get("status") or "requested").strip()
    if status not in {"requested", "answer_submitted", "answered", "stale"}:
        status = "requested"
    answers: list[UserInputAnswerV3] = []
    if isinstance(raw.get("answers"), list):
        for answer in raw["answers"]:
            normalized_answer = normalize_user_input_answer_v3(answer)
            if normalized_answer is not None:
                answers.append(normalized_answer)
    now = iso_now()
    return {
        "requestId": request_id,
        "itemId": item_id,
        "threadId": _normalize_optional_string(raw.get("threadId") or raw.get("thread_id")) or thread_id or "",
        "turnId": _normalize_optional_string(raw.get("turnId") or raw.get("turn_id")),
        "status": cast(Any, status),
        "createdAt": raw.get("createdAt") if isinstance(raw.get("createdAt"), str) else now,
        "submittedAt": _normalize_optional_string(raw.get("submittedAt") or raw.get("submitted_at")),
        "resolvedAt": _normalize_optional_string(raw.get("resolvedAt") or raw.get("resolved_at")),
        "answers": answers,
    }


def normalize_plan_ready_signal_v3(raw: Any) -> PlanReadySignalV3:
    source = raw if isinstance(raw, dict) else {}
    revision: int | None = None
    if source.get("revision") is not None:
        revision = _coerce_nonnegative_int(source.get("revision"), default=0)
    return {
        "planItemId": _normalize_optional_string(source.get("planItemId") or source.get("plan_item_id")),
        "revision": revision,
        "ready": bool(source.get("ready")),
        "failed": bool(source.get("failed")),
    }


def normalize_ui_signals_v3(raw: Any, *, thread_id: str | None = None) -> UiSignalsV3:
    source = raw if isinstance(raw, dict) else {}
    requests: list[PendingUserInputRequestV3] = []
    raw_requests = source.get("activeUserInputRequests")
    if isinstance(raw_requests, list):
        for raw_request in raw_requests:
            normalized_request = normalize_pending_user_input_request_v3(raw_request, thread_id=thread_id)
            if normalized_request is not None:
                requests.append(normalized_request)
    requests.sort(key=lambda request: (str(request.get("createdAt") or ""), str(request.get("requestId") or "")))
    return {
        "planReady": normalize_plan_ready_signal_v3(source.get("planReady")),
        "activeUserInputRequests": requests,
    }


def default_thread_snapshot_v3(
    project_id: str,
    node_id: str,
    thread_role: ThreadRoleV3 | str,
    *,
    thread_id: str | None = None,
) -> ThreadSnapshotV3:
    resolved_thread_role = normalize_thread_role_v3(thread_role, default="ask_planning")
    now = iso_now()
    return {
        "projectId": project_id,
        "nodeId": node_id,
        "threadRole": resolved_thread_role,
        "threadId": thread_id,
        "activeTurnId": None,
        "processingState": "idle",
        "snapshotVersion": 0,
        "createdAt": now,
        "updatedAt": now,
        "items": [],
        "uiSignals": default_ui_signals_v3(),
    }


def normalize_thread_snapshot_v3(
    payload: Any,
    *,
    project_id: str,
    node_id: str,
    thread_role: ThreadRoleV3 | str,
) -> ThreadSnapshotV3:
    default_snapshot = default_thread_snapshot_v3(
        project_id=project_id,
        node_id=node_id,
        thread_role=thread_role,
    )
    source = payload if isinstance(payload, dict) else {}
    resolved_thread_role = normalize_thread_role_v3(
        source.get("threadRole")
        or source.get("thread_role")
        or source.get("thread-role")
        or source.get("lane"),
        default=normalize_thread_role_v3(thread_role, default="ask_planning"),
    )
    thread_id = _normalize_optional_string(source.get("threadId") or source.get("thread_id"))
    items: list[ConversationItemV3] = []
    if isinstance(source.get("items"), list):
        for raw_item in source["items"]:
            normalized_item = normalize_conversation_item_v3(raw_item, thread_id=thread_id)
            if normalized_item is not None:
                items.append(normalized_item)
    items.sort(key=lambda item: (_coerce_nonnegative_int(item.get("sequence"), default=0), str(item.get("id") or "")))

    now = iso_now()
    created_at = source.get("createdAt") if isinstance(source.get("createdAt"), str) else default_snapshot["createdAt"]
    updated_at = source.get("updatedAt") if isinstance(source.get("updatedAt"), str) else created_at

    return {
        "projectId": _normalize_optional_string(source.get("projectId")) or default_snapshot["projectId"],
        "nodeId": _normalize_optional_string(source.get("nodeId")) or default_snapshot["nodeId"],
        "threadRole": resolved_thread_role,
        "threadId": thread_id,
        "activeTurnId": _normalize_optional_string(source.get("activeTurnId") or source.get("active_turn_id")),
        "processingState": normalize_processing_state_v3(source.get("processingState"), default="idle"),
        "snapshotVersion": _coerce_nonnegative_int(source.get("snapshotVersion"), default=0),
        "createdAt": created_at if isinstance(created_at, str) else now,
        "updatedAt": updated_at if isinstance(updated_at, str) else created_at,
        "items": items,
        "uiSignals": normalize_ui_signals_v3(source.get("uiSignals"), thread_id=thread_id),
    }


def copy_snapshot_v3(snapshot: ThreadSnapshotV3) -> ThreadSnapshotV3:
    return copy.deepcopy(snapshot)
