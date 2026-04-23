from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

ConnectionPhase = Literal["disconnected", "connecting", "initialized", "error"]
TurnRuntimeStatus = Literal[
    "idle",
    "inProgress",
    "waitingUserInput",
    "completed",
    "failed",
    "interrupted",
]
TurnCodexStatus = Literal["inProgress", "completed", "failed", "interrupted"]
ItemKind = Literal[
    "userMessage",
    "agentMessage",
    "reasoning",
    "plan",
    "commandExecution",
    "fileChange",
    "userInput",
    "error",
]
ItemStatus = Literal["inProgress", "completed", "failed"]
PendingRequestStatus = Literal["pending", "submitted", "resolved", "rejected", "expired"]
EventTier = Literal["tier0", "tier1", "tier2"]
EventSource = Literal["journal", "replay"]

SessionErrorCode = Literal[
    "ERR_SESSION_NOT_INITIALIZED",
    "ERR_CURSOR_INVALID",
    "ERR_CURSOR_EXPIRED",
    "ERR_TURN_TERMINAL",
    "ERR_TURN_NOT_STEERABLE",
    "ERR_ACTIVE_TURN_MISMATCH",
    "ERR_REQUEST_STALE",
    "ERR_IDEMPOTENCY_PAYLOAD_MISMATCH",
    "ERR_PROVIDER_UNAVAILABLE",
    "ERR_SANDBOX_FAILURE",
    "ERR_INTERNAL",
]

SessionNotificationMethod = Literal[
    "error",
    "thread/started",
    "thread/status/changed",
    "thread/closed",
    "thread/archived",
    "thread/unarchived",
    "thread/name/updated",
    "thread/compacted",
    "thread/tokenUsage/updated",
    "turn/started",
    "turn/completed",
    "turn/diff/updated",
    "turn/plan/updated",
    "item/started",
    "item/completed",
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/summaryPartAdded",
    "item/reasoning/textDelta",
    "item/commandExecution/outputDelta",
    "item/fileChange/outputDelta",
    "serverRequest/resolved",
]

ServerRequestMethod = Literal[
    "item/tool/requestUserInput",
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "mcpServer/elicitation/request",
]

THREAD_ACTIVE_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "waitingOnApproval",
        "waitingOnUserInput",
    }
)

TERMINAL_TURN_STATES: Final[frozenset[TurnRuntimeStatus]] = frozenset(
    {"completed", "failed", "interrupted"}
)

ALLOWED_TURN_TRANSITIONS: Final[dict[TurnRuntimeStatus, frozenset[TurnRuntimeStatus]]] = {
    "idle": frozenset({"inProgress"}),
    "inProgress": frozenset({"inProgress", "waitingUserInput", "completed", "failed", "interrupted"}),
    "waitingUserInput": frozenset({"inProgress", "interrupted"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "interrupted": frozenset(),
}


class SessionError(TypedDict):
    code: SessionErrorCode
    message: str
    details: dict[str, Any]


class ConnectionState(TypedDict):
    phase: ConnectionPhase
    clientName: str | None
    serverVersion: str | None
    error: SessionError | None


class ThreadStatusNotLoaded(TypedDict):
    type: Literal["notLoaded"]


class ThreadStatusIdle(TypedDict):
    type: Literal["idle"]


class ThreadStatusSystemError(TypedDict):
    type: Literal["systemError"]


class ThreadStatusActive(TypedDict):
    type: Literal["active"]
    activeFlags: list[str]


ThreadStatus = ThreadStatusNotLoaded | ThreadStatusIdle | ThreadStatusSystemError | ThreadStatusActive


class SessionItem(TypedDict):
    id: str
    threadId: str
    turnId: str | None
    kind: ItemKind
    status: ItemStatus
    createdAtMs: int
    updatedAtMs: int
    payload: dict[str, Any]


class SessionTurn(TypedDict):
    id: str
    threadId: str
    status: TurnRuntimeStatus
    lastCodexStatus: TurnCodexStatus | None
    startedAtMs: int
    completedAtMs: int | None
    items: list[SessionItem]
    error: SessionError | None


class SessionThread(TypedDict):
    id: str
    name: str | None
    preview: str | None
    model: str | None
    modelProvider: str
    cwd: str
    path: str | None
    ephemeral: bool
    archived: bool
    status: ThreadStatus
    createdAt: int
    updatedAt: int
    metadata: dict[str, Any]
    turns: list[SessionTurn]


class PendingServerRequest(TypedDict):
    requestId: str
    method: ServerRequestMethod
    threadId: str
    turnId: str | None
    itemId: str | None
    status: PendingRequestStatus
    createdAtMs: int
    submittedAtMs: int | None
    resolvedAtMs: int | None
    payload: dict[str, Any]


class SessionEventEnvelope(TypedDict):
    schemaVersion: int
    eventId: str
    eventSeq: int
    tier: EventTier
    method: SessionNotificationMethod
    threadId: str
    turnId: str | None
    occurredAtMs: int
    replayable: bool
    snapshotVersion: int | None
    source: EventSource
    params: dict[str, Any]


class ServerRequestEnvelope(TypedDict):
    schemaVersion: int
    requestId: str
    method: ServerRequestMethod
    threadId: str
    turnId: str | None
    itemId: str | None
    status: Literal["pending", "resolved", "rejected", "expired"]
    occurredAtMs: int
    params: dict[str, Any]


class TurnStartAction(TypedDict):
    clientActionId: str
    threadId: str
    input: list[dict[str, Any]]
    overrides: dict[str, Any]


class TurnSteerAction(TypedDict):
    clientActionId: str
    threadId: str
    expectedTurnId: str
    input: list[dict[str, Any]]


class TurnInterruptAction(TypedDict):
    clientActionId: str
    threadId: str
    turnId: str


class RequestResolutionAction(TypedDict):
    resolutionKey: str
    requestId: str
    result: dict[str, Any]
