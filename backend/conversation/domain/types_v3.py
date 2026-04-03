from __future__ import annotations

import copy
from typing import Any, Literal, TypedDict

from backend.storage.file_utils import iso_now

ThreadLaneV3 = Literal["execution", "audit"]
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

THREAD_LANES_V3: tuple[ThreadLaneV3, ...] = ("execution", "audit")
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


class DiffItemV3(ItemBaseV3):
    kind: Literal["diff"]
    title: str | None
    summaryText: str | None
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
    threadId: str | None
    lane: ThreadLaneV3
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


def default_thread_snapshot_v3(
    project_id: str,
    node_id: str,
    lane: ThreadLaneV3,
    *,
    thread_id: str | None = None,
) -> ThreadSnapshotV3:
    now = iso_now()
    return {
        "projectId": project_id,
        "nodeId": node_id,
        "threadId": thread_id,
        "lane": lane,
        "activeTurnId": None,
        "processingState": "idle",
        "snapshotVersion": 0,
        "createdAt": now,
        "updatedAt": now,
        "items": [],
        "uiSignals": default_ui_signals_v3(),
    }


def copy_snapshot_v3(snapshot: ThreadSnapshotV3) -> ThreadSnapshotV3:
    return copy.deepcopy(snapshot)
