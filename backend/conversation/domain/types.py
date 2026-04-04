from __future__ import annotations

import copy
from typing import Any, Literal, NotRequired, TypedDict, cast

from backend.storage.file_utils import iso_now

ThreadRole = Literal["ask_planning", "audit", "execution"]
ProcessingState = Literal["idle", "running", "waiting_user_input", "failed"]
ItemStatus = Literal[
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
ItemSource = Literal["upstream", "backend", "local"]
ItemTone = Literal["neutral", "info", "success", "warning", "danger", "muted"]

THREAD_ROLES: tuple[ThreadRole, ...] = ("ask_planning", "audit", "execution")
PROCESSING_STATES: tuple[ProcessingState, ...] = ("idle", "running", "waiting_user_input", "failed")
ITEM_STATUSES: tuple[ItemStatus, ...] = (
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
ITEM_SOURCES: tuple[ItemSource, ...] = ("upstream", "backend", "local")
ITEM_TONES: tuple[ItemTone, ...] = ("neutral", "info", "success", "warning", "danger", "muted")


class ItemBase(TypedDict):
    id: str
    kind: Literal["message", "reasoning", "plan", "tool", "userInput", "status", "error"]
    threadId: str
    turnId: str | None
    sequence: int
    createdAt: str
    updatedAt: str
    status: ItemStatus
    source: ItemSource
    tone: ItemTone
    metadata: dict[str, Any]


class MessageItem(ItemBase):
    kind: Literal["message"]
    role: Literal["user", "assistant", "system"]
    text: str
    format: Literal["markdown"]


class ReasoningItem(ItemBase):
    kind: Literal["reasoning"]
    summaryText: str
    detailText: str | None


class PlanStep(TypedDict):
    id: str
    text: str
    status: Literal["pending", "in_progress", "completed"]


class PlanItem(ItemBase):
    kind: Literal["plan"]
    title: str | None
    text: str
    steps: list[PlanStep]


class ToolOutputFile(TypedDict):
    path: str
    changeType: Literal["created", "updated", "deleted"]
    summary: str | None
    kind: NotRequired[Literal["add", "modify", "delete"]]
    diff: NotRequired[str | None]


class ToolChange(TypedDict):
    path: str
    kind: Literal["add", "modify", "delete"]
    diff: str | None
    summary: str | None


class ToolItem(ItemBase):
    kind: Literal["tool"]
    toolType: Literal["commandExecution", "fileChange", "generic"]
    title: str
    toolName: str | None
    callId: str | None
    argumentsText: str | None
    outputText: str
    outputFiles: list[ToolOutputFile]
    changes: NotRequired[list[ToolChange]]
    exitCode: int | None


class UserInputAnswer(TypedDict):
    questionId: str
    value: str
    label: str | None


class UserInputQuestionOption(TypedDict):
    label: str
    description: str | None


class UserInputQuestion(TypedDict):
    id: str
    header: str | None
    prompt: str
    inputType: Literal["single_select", "multi_select", "text"]
    options: list[UserInputQuestionOption]


class UserInputItem(ItemBase):
    kind: Literal["userInput"]
    requestId: str
    title: str | None
    questions: list[UserInputQuestion]
    answers: list[UserInputAnswer]
    requestedAt: str
    resolvedAt: str | None


class StatusItem(ItemBase):
    kind: Literal["status"]
    code: str
    label: str
    detail: str | None


class ErrorItem(ItemBase):
    kind: Literal["error"]
    code: str
    title: str
    message: str
    recoverable: bool
    relatedItemId: str | None


ConversationItem = MessageItem | ReasoningItem | PlanItem | ToolItem | UserInputItem | StatusItem | ErrorItem


class PendingUserInputRequest(TypedDict):
    requestId: str
    itemId: str
    threadId: str
    turnId: str | None
    status: Literal["requested", "answer_submitted", "answered", "stale"]
    createdAt: str
    submittedAt: str | None
    resolvedAt: str | None
    answers: list[UserInputAnswer]


class ThreadLineage(TypedDict):
    forkedFromThreadId: str | None
    forkedFromNodeId: str | None
    forkedFromRole: ThreadRole | None
    forkReason: str | None
    lineageRootThreadId: str | None


class ThreadSnapshotV2(TypedDict):
    projectId: str
    nodeId: str
    threadRole: ThreadRole
    threadId: str | None
    activeTurnId: str | None
    processingState: ProcessingState
    snapshotVersion: int
    createdAt: str
    updatedAt: str
    lineage: ThreadLineage
    items: list[ConversationItem]
    pendingRequests: list[PendingUserInputRequest]


class ThreadRegistryEntry(TypedDict):
    projectId: str
    nodeId: str
    threadRole: ThreadRole
    threadId: str | None
    forkedFromThreadId: str | None
    forkedFromNodeId: str | None
    forkedFromRole: ThreadRole | None
    forkReason: str | None
    lineageRootThreadId: str | None
    createdAt: str
    updatedAt: str


class MessagePatch(TypedDict, total=False):
    kind: Literal["message"]
    textAppend: str
    status: ItemStatus
    updatedAt: str


class ReasoningPatch(TypedDict, total=False):
    kind: Literal["reasoning"]
    summaryTextAppend: str
    detailTextAppend: str
    status: ItemStatus
    updatedAt: str


class PlanPatch(TypedDict, total=False):
    kind: Literal["plan"]
    textAppend: str
    stepsReplace: list[PlanStep]
    status: ItemStatus
    updatedAt: str


class ToolPatch(TypedDict, total=False):
    kind: Literal["tool"]
    title: str
    argumentsText: str | None
    outputTextAppend: str
    outputFilesAppend: list[ToolOutputFile]
    outputFilesReplace: list[ToolOutputFile]
    changesAppend: list[ToolChange]
    changesReplace: list[ToolChange]
    exitCode: int | None
    status: ItemStatus
    updatedAt: str


class UserInputPatch(TypedDict, total=False):
    kind: Literal["userInput"]
    answersReplace: list[UserInputAnswer]
    resolvedAt: str | None
    status: Literal["requested", "answer_submitted", "answered", "stale"]
    updatedAt: str


class StatusPatch(TypedDict, total=False):
    kind: Literal["status"]
    label: str
    detail: str | None
    status: ItemStatus
    updatedAt: str


class ErrorPatch(TypedDict, total=False):
    kind: Literal["error"]
    message: str
    relatedItemId: str | None
    status: ItemStatus
    updatedAt: str


ItemPatch = MessagePatch | ReasoningPatch | PlanPatch | ToolPatch | UserInputPatch | StatusPatch | ErrorPatch


def _normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value.strip() else None


def _normalize_tool_change_kind(value: Any, *, fallback: Literal["add", "modify", "delete"] = "modify") -> Literal["add", "modify", "delete"]:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"add", "create", "created", "new"}:
            return "add"
        if normalized in {"delete", "deleted", "remove", "removed"}:
            return "delete"
        if normalized in {"modify", "modified", "update", "updated", "change", "changed"}:
            return "modify"
    return fallback


def _tool_change_kind_to_change_type(kind: str) -> Literal["created", "updated", "deleted"]:
    if kind == "add":
        return "created"
    if kind == "delete":
        return "deleted"
    return "updated"


def normalize_thread_role(value: Any, *, default: ThreadRole = "ask_planning") -> ThreadRole:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in THREAD_ROLES:
            return normalized  # type: ignore[return-value]
    return default


def normalize_processing_state(value: Any, *, default: ProcessingState = "idle") -> ProcessingState:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in PROCESSING_STATES:
            return normalized  # type: ignore[return-value]
    return default


def normalize_item_status(value: Any, *, default: ItemStatus = "pending") -> ItemStatus:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in ITEM_STATUSES:
            return normalized  # type: ignore[return-value]
    return default


def normalize_item_source(value: Any, *, default: ItemSource = "backend") -> ItemSource:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in ITEM_SOURCES:
            return normalized  # type: ignore[return-value]
    return default


def normalize_item_tone(value: Any, *, default: ItemTone = "neutral") -> ItemTone:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in ITEM_TONES:
            return normalized  # type: ignore[return-value]
    return default


def default_thread_lineage() -> ThreadLineage:
    return {
        "forkedFromThreadId": None,
        "forkedFromNodeId": None,
        "forkedFromRole": None,
        "forkReason": None,
        "lineageRootThreadId": None,
    }


def normalize_thread_lineage(payload: Any) -> ThreadLineage:
    source = payload if isinstance(payload, dict) else {}
    raw_role = source.get("forkedFromRole") or source.get("forked_from_role")
    return {
        "forkedFromThreadId": _normalize_optional_string(source.get("forkedFromThreadId") or source.get("forked_from_thread_id")),
        "forkedFromNodeId": _normalize_optional_string(source.get("forkedFromNodeId") or source.get("forked_from_node_id")),
        "forkedFromRole": normalize_thread_role(raw_role, default="ask_planning") if _normalize_optional_string(raw_role) else None,
        "forkReason": _normalize_optional_string(source.get("forkReason") or source.get("fork_reason")),
        "lineageRootThreadId": _normalize_optional_string(source.get("lineageRootThreadId") or source.get("lineage_root_thread_id")),
    }


def default_thread_registry_entry(project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadRegistryEntry:
    now = iso_now()
    return {
        "projectId": project_id,
        "nodeId": node_id,
        "threadRole": thread_role,
        "threadId": None,
        "forkedFromThreadId": None,
        "forkedFromNodeId": None,
        "forkedFromRole": None,
        "forkReason": None,
        "lineageRootThreadId": None,
        "createdAt": now,
        "updatedAt": now,
    }


def normalize_thread_registry_entry(payload: Any, *, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadRegistryEntry:
    source = payload if isinstance(payload, dict) else {}
    default = default_thread_registry_entry(project_id, node_id, thread_role)
    raw_role = source.get("forkedFromRole") or source.get("forked_from_role")
    return {
        "projectId": _normalize_optional_string(source.get("projectId")) or default["projectId"],
        "nodeId": _normalize_optional_string(source.get("nodeId")) or default["nodeId"],
        "threadRole": normalize_thread_role(source.get("threadRole"), default=thread_role),
        "threadId": _normalize_optional_string(source.get("threadId") or source.get("thread_id")),
        "forkedFromThreadId": _normalize_optional_string(source.get("forkedFromThreadId") or source.get("forked_from_thread_id")),
        "forkedFromNodeId": _normalize_optional_string(source.get("forkedFromNodeId") or source.get("forked_from_node_id")),
        "forkedFromRole": normalize_thread_role(raw_role, default="ask_planning") if _normalize_optional_string(raw_role) else None,
        "forkReason": _normalize_optional_string(source.get("forkReason") or source.get("fork_reason")),
        "lineageRootThreadId": _normalize_optional_string(source.get("lineageRootThreadId") or source.get("lineage_root_thread_id")),
        "createdAt": source.get("createdAt") if isinstance(source.get("createdAt"), str) else default["createdAt"],
        "updatedAt": source.get("updatedAt") if isinstance(source.get("updatedAt"), str) else default["updatedAt"],
    }


def default_thread_snapshot(project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadSnapshotV2:
    now = iso_now()
    return {
        "projectId": project_id,
        "nodeId": node_id,
        "threadRole": thread_role,
        "threadId": None,
        "activeTurnId": None,
        "processingState": "idle",
        "snapshotVersion": 0,
        "createdAt": now,
        "updatedAt": now,
        "lineage": default_thread_lineage(),
        "items": [],
        "pendingRequests": [],
    }


def normalize_tool_output_file(raw: Any) -> ToolOutputFile | None:
    if not isinstance(raw, dict):
        return None
    path = _normalize_optional_string(raw.get("path"))
    if not path:
        return None
    inferred_kind = _normalize_tool_change_kind(
        raw.get("kind") or raw.get("changeKind") or raw.get("change_kind"),
        fallback="modify",
    )
    change_type = str(raw.get("changeType") or raw.get("change_type") or "").strip()
    if change_type not in {"created", "updated", "deleted"}:
        change_type = _tool_change_kind_to_change_type(inferred_kind)
    output_file: ToolOutputFile = {
        "path": path,
        "changeType": change_type,  # type: ignore[typeddict-item]
        "summary": _normalize_optional_string(raw.get("summary")),
    }
    raw_kind = raw.get("kind") or raw.get("changeKind") or raw.get("change_kind")
    if raw_kind is not None:
        output_file["kind"] = _normalize_tool_change_kind(raw_kind, fallback="modify")
    diff_text = _normalize_optional_text(raw.get("diff") if "diff" in raw else raw.get("patchText") or raw.get("patch_text"))
    if diff_text is not None:
        output_file["diff"] = diff_text
    return output_file


def normalize_tool_change(raw: Any) -> ToolChange | None:
    if not isinstance(raw, dict):
        return None
    path = _normalize_optional_string(raw.get("path"))
    if not path:
        return None
    kind = _normalize_tool_change_kind(
        raw.get("kind")
        or raw.get("changeKind")
        or raw.get("change_kind")
        or raw.get("changeType")
        or raw.get("change_type"),
        fallback="modify",
    )
    diff_text = _normalize_optional_text(raw.get("diff") if "diff" in raw else raw.get("patchText") or raw.get("patch_text"))
    return {
        "path": path,
        "kind": kind,  # type: ignore[typeddict-item]
        "diff": diff_text,
        "summary": _normalize_optional_string(raw.get("summary")),
    }


def normalize_user_input_answer(raw: Any) -> UserInputAnswer | None:
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


def normalize_user_input_question_option(raw: Any) -> UserInputQuestionOption | None:
    if not isinstance(raw, dict):
        return None
    label = _normalize_optional_string(raw.get("label"))
    if not label:
        return None
    return {
        "label": label,
        "description": _normalize_optional_string(raw.get("description")),
    }


def normalize_user_input_question(raw: Any) -> UserInputQuestion | None:
    if not isinstance(raw, dict):
        return None
    question_id = _normalize_optional_string(raw.get("id"))
    prompt = _normalize_optional_string(raw.get("prompt") or raw.get("question"))
    if not question_id or prompt is None:
        return None
    input_type = str(raw.get("inputType") or raw.get("input_type") or "text").strip()
    if input_type not in {"single_select", "multi_select", "text"}:
        input_type = "text"
    options: list[UserInputQuestionOption] = []
    if isinstance(raw.get("options"), list):
        for option in raw["options"]:
            normalized = normalize_user_input_question_option(option)
            if normalized is not None:
                options.append(normalized)
    return {
        "id": question_id,
        "header": _normalize_optional_string(raw.get("header")),
        "prompt": prompt,
        "inputType": input_type,  # type: ignore[typeddict-item]
        "options": options,
    }


def normalize_plan_step(raw: Any) -> PlanStep | None:
    if not isinstance(raw, dict):
        return None
    step_id = _normalize_optional_string(raw.get("id"))
    text = _normalize_optional_string(raw.get("text"))
    if not step_id or text is None:
        return None
    status = str(raw.get("status") or "pending").strip()
    if status not in {"pending", "in_progress", "completed"}:
        status = "pending"
    return {
        "id": step_id,
        "text": text,
        "status": status,  # type: ignore[typeddict-item]
    }


def normalize_item(raw: Any, *, thread_id: str | None = None) -> ConversationItem:
    if not isinstance(raw, dict):
        raise ValueError("Conversation item payload must be a dict.")
    kind = str(raw.get("kind") or "").strip()
    item_id = _normalize_optional_string(raw.get("id"))
    if not item_id or kind not in {"message", "reasoning", "plan", "tool", "userInput", "status", "error"}:
        raise ValueError("Invalid conversation item payload.")
    base = {
        "id": item_id,
        "threadId": _normalize_optional_string(raw.get("threadId")) or thread_id or "",
        "turnId": _normalize_optional_string(raw.get("turnId")),
        "sequence": int(raw.get("sequence") or 0),
        "createdAt": raw.get("createdAt") if isinstance(raw.get("createdAt"), str) else iso_now(),
        "updatedAt": raw.get("updatedAt") if isinstance(raw.get("updatedAt"), str) else iso_now(),
        "status": normalize_item_status(raw.get("status")),
        "source": normalize_item_source(raw.get("source")),
        "tone": normalize_item_tone(raw.get("tone")),
        "metadata": copy.deepcopy(raw.get("metadata")) if isinstance(raw.get("metadata"), dict) else {},
    }
    if kind == "message":
        role = str(raw.get("role") or "assistant").strip()
        if role not in {"user", "assistant", "system"}:
            role = "assistant"
        return MessageItem(
            **base,
            kind="message",
            role=role,  # type: ignore[typeddict-item]
            text=str(raw.get("text") or ""),
            format="markdown",
        )
    if kind == "reasoning":
        return ReasoningItem(
            **base,
            kind="reasoning",
            summaryText=str(raw.get("summaryText") or ""),
            detailText=_normalize_optional_string(raw.get("detailText")),
        )
    if kind == "plan":
        steps: list[PlanStep] = []
        if isinstance(raw.get("steps"), list):
            for step in raw["steps"]:
                normalized = normalize_plan_step(step)
                if normalized is not None:
                    steps.append(normalized)
        return PlanItem(
            **base,
            kind="plan",
            title=_normalize_optional_string(raw.get("title")),
            text=str(raw.get("text") or ""),
            steps=steps,
        )
    if kind == "tool":
        tool_type = str(raw.get("toolType") or "generic").strip()
        if tool_type not in {"commandExecution", "fileChange", "generic"}:
            tool_type = "generic"
        output_files: list[ToolOutputFile] = []
        if isinstance(raw.get("outputFiles"), list):
            for file_item in raw["outputFiles"]:
                normalized = normalize_tool_output_file(file_item)
                if normalized is not None:
                    output_files.append(normalized)
        changes: list[ToolChange] = []
        raw_changes = raw.get("changes")
        if not isinstance(raw_changes, list):
            raw_files = raw.get("files")
            raw_changes = raw_files if isinstance(raw_files, list) else None
        if isinstance(raw_changes, list):
            for change_item in raw_changes:
                normalized_change = normalize_tool_change(change_item)
                if normalized_change is not None:
                    changes.append(normalized_change)
        if not output_files and changes:
            output_files = []
            for change in changes:
                output_file: ToolOutputFile = {
                    "path": change["path"],
                    "changeType": _tool_change_kind_to_change_type(str(change.get("kind") or "modify")),
                    "summary": change.get("summary"),
                }
                if isinstance(change.get("diff"), str) and str(change.get("diff") or "").strip():
                    output_file["diff"] = str(change.get("diff"))
                output_files.append(output_file)
        if not changes and output_files:
            changes = [
                {
                    "path": output_file["path"],
                    "kind": cast(Any, _normalize_tool_change_kind(output_file.get("kind") or output_file.get("changeType"), fallback="modify")),
                    "diff": output_file.get("diff"),
                    "summary": output_file.get("summary"),
                }
                for output_file in output_files
            ]
        return ToolItem(
            **base,
            kind="tool",
            toolType=tool_type,  # type: ignore[typeddict-item]
            title=str(raw.get("title") or ""),
            toolName=_normalize_optional_string(raw.get("toolName")),
            callId=_normalize_optional_string(raw.get("callId")),
            argumentsText=_normalize_optional_string(raw.get("argumentsText")),
            outputText=str(raw.get("outputText") or ""),
            outputFiles=output_files,
            changes=changes,
            exitCode=raw.get("exitCode") if isinstance(raw.get("exitCode"), int) else None,
        )
    if kind == "userInput":
        request_id = _normalize_optional_string(raw.get("requestId"))
        if not request_id:
            raise ValueError("UserInput item requires requestId.")
        questions: list[UserInputQuestion] = []
        if isinstance(raw.get("questions"), list):
            for question in raw["questions"]:
                normalized = normalize_user_input_question(question)
                if normalized is not None:
                    questions.append(normalized)
        answers: list[UserInputAnswer] = []
        if isinstance(raw.get("answers"), list):
            for answer in raw["answers"]:
                normalized = normalize_user_input_answer(answer)
                if normalized is not None:
                    answers.append(normalized)
        return UserInputItem(
            **base,
            kind="userInput",
            requestId=request_id,
            title=_normalize_optional_string(raw.get("title")),
            questions=questions,
            answers=answers,
            requestedAt=raw.get("requestedAt") if isinstance(raw.get("requestedAt"), str) else str(base["createdAt"]),
            resolvedAt=_normalize_optional_string(raw.get("resolvedAt")),
        )
    if kind == "status":
        return StatusItem(
            **base,
            kind="status",
            code=str(raw.get("code") or ""),
            label=str(raw.get("label") or ""),
            detail=_normalize_optional_string(raw.get("detail")),
        )
    return ErrorItem(
        **base,
        kind="error",
        code=str(raw.get("code") or ""),
        title=str(raw.get("title") or ""),
        message=str(raw.get("message") or ""),
        recoverable=bool(raw.get("recoverable")),
        relatedItemId=_normalize_optional_string(raw.get("relatedItemId")),
    )


def normalize_pending_request(raw: Any, *, thread_id: str | None = None) -> PendingUserInputRequest | None:
    if not isinstance(raw, dict):
        return None
    request_id = _normalize_optional_string(raw.get("requestId") or raw.get("request_id"))
    item_id = _normalize_optional_string(raw.get("itemId") or raw.get("item_id"))
    if not request_id or not item_id:
        return None
    status = str(raw.get("status") or "requested").strip()
    if status not in {"requested", "answer_submitted", "answered", "stale"}:
        status = "requested"
    answers: list[UserInputAnswer] = []
    if isinstance(raw.get("answers"), list):
        for answer in raw["answers"]:
            normalized = normalize_user_input_answer(answer)
            if normalized is not None:
                answers.append(normalized)
    return {
        "requestId": request_id,
        "itemId": item_id,
        "threadId": _normalize_optional_string(raw.get("threadId") or raw.get("thread_id")) or thread_id or "",
        "turnId": _normalize_optional_string(raw.get("turnId") or raw.get("turn_id")),
        "status": status,  # type: ignore[typeddict-item]
        "createdAt": raw.get("createdAt") if isinstance(raw.get("createdAt"), str) else iso_now(),
        "submittedAt": _normalize_optional_string(raw.get("submittedAt") or raw.get("submitted_at")),
        "resolvedAt": _normalize_optional_string(raw.get("resolvedAt") or raw.get("resolved_at")),
        "answers": answers,
    }


def normalize_thread_snapshot(payload: Any, *, project_id: str, node_id: str, thread_role: ThreadRole) -> ThreadSnapshotV2:
    default = default_thread_snapshot(project_id, node_id, thread_role)
    source = payload if isinstance(payload, dict) else {}
    snapshot: ThreadSnapshotV2 = {
        "projectId": _normalize_optional_string(source.get("projectId")) or default["projectId"],
        "nodeId": _normalize_optional_string(source.get("nodeId")) or default["nodeId"],
        "threadRole": normalize_thread_role(source.get("threadRole"), default=thread_role),
        "threadId": _normalize_optional_string(source.get("threadId")),
        "activeTurnId": _normalize_optional_string(source.get("activeTurnId")),
        "processingState": normalize_processing_state(source.get("processingState")),
        "snapshotVersion": max(0, int(source.get("snapshotVersion") or 0)),
        "createdAt": source.get("createdAt") if isinstance(source.get("createdAt"), str) else default["createdAt"],
        "updatedAt": source.get("updatedAt") if isinstance(source.get("updatedAt"), str) else default["updatedAt"],
        "lineage": normalize_thread_lineage(source.get("lineage")),
        "items": [],
        "pendingRequests": [],
    }
    if isinstance(source.get("items"), list):
        for raw_item in source["items"]:
            snapshot["items"].append(normalize_item(raw_item, thread_id=snapshot["threadId"]))
    snapshot["items"].sort(key=lambda item: (int(item.get("sequence") or 0), str(item.get("id") or "")))
    if isinstance(source.get("pendingRequests"), list):
        for raw_request in source["pendingRequests"]:
            normalized = normalize_pending_request(raw_request, thread_id=snapshot["threadId"])
            if normalized is not None:
                snapshot["pendingRequests"].append(normalized)
    return snapshot


def copy_snapshot(snapshot: ThreadSnapshotV2) -> ThreadSnapshotV2:
    return copy.deepcopy(snapshot)


def copy_registry_entry(entry: ThreadRegistryEntry) -> ThreadRegistryEntry:
    return copy.deepcopy(entry)


def next_snapshot_version(snapshot: ThreadSnapshotV2) -> int:
    return int(snapshot.get("snapshotVersion") or 0) + 1


def snapshot_with_metadata(snapshot: ThreadSnapshotV2, registry_entry: ThreadRegistryEntry) -> ThreadSnapshotV2:
    updated = copy_snapshot(snapshot)
    updated["threadId"] = registry_entry.get("threadId")
    updated["lineage"] = {
        "forkedFromThreadId": registry_entry.get("forkedFromThreadId"),
        "forkedFromNodeId": registry_entry.get("forkedFromNodeId"),
        "forkedFromRole": registry_entry.get("forkedFromRole"),
        "forkReason": registry_entry.get("forkReason"),
        "lineageRootThreadId": registry_entry.get("lineageRootThreadId"),
    }
    return updated
