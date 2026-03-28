# Conversation Streaming V2

Status: draft spec (implementation not started). Defines the canonical item-centric conversation model, backend/runtime contract, and frontend rendering contract for the PlanningTreeMain streaming chat rewrite.

Primary rollout docs:

- `docs/handoff/conversation-streaming-v2/README.md`
- `docs/handoff/conversation-streaming-v2/progress.yaml`

Reference architecture:

- `C:/Users/Thong/CodexMonitor_tmp/src/types.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/app/hooks/useAppServerEvents.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/threads/hooks/useThreadItemEvents.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/threads/hooks/threadReducer/threadItemsSlice.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/utils/threadItems.conversion.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/messages/components/Messages.tsx`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/messages/components/MessageRows.tsx`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/messages/components/useMessagesViewState.ts`

## Goals

- Replace the legacy `content / parts / items` render pipeline with one canonical `ConversationItem[]` model.
- Make live SSE and reload/resume converge on the same model.
- Make `message`, `reasoning`, `plan`, `tool`, `userInput`, `status`, and `error` first-class item kinds.
- Use item-centric `upsert` and `patch` semantics instead of pair-based message events.
- Unify chat, review, and execution on one thread contract.

## Non-Goals

- Backward compatibility with legacy thread data.
- Migrating old persisted transcripts into the new schema.
- Preserving the V1 semantic mapper, message pair assumptions, or legacy SSE event taxonomy.

## Current-State Diagnosis

Current PlanningTreeMain conversation rendering is fragmented across:

- frontend `ChatSession -> ChatMessage -> content / parts / items`
- semantic mapping and semantic blocks
- backend part accumulation and synthetic tool identity
- multiple service-specific live event contracts

Representative files:

- `frontend/src/api/types.ts`
- `frontend/src/stores/chat-store.ts`
- `frontend/src/features/breadcrumb/semanticMapper.ts`
- `frontend/src/features/breadcrumb/MessageFeed.tsx`
- `backend/ai/part_accumulator.py`
- `backend/ai/codex_client.py`
- `backend/services/chat_service.py`
- `backend/services/review_service.py`
- `backend/services/finish_task_service.py`
- `backend/routes/chat.py`
- `backend/storage/chat_state_store.py`

Key failures in the V1 model:

- frontend reconciles multiple representations before render
- backend publishes inconsistent message creation contracts
- tool identity is partly synthetic and can duplicate
- `GET` session load has stateful repair/bootstrap semantics mixed into read paths
- live stream and reload do not use one canonical item model

## Copy Strategy From CodexMonitor

Copy as close as possible:

- central event router
- item-by-item upsert and patch flow
- id-based merge rules
- hydration through the same model used by live events
- render directly by `item.kind`
- lifecycle/view-state separated from item rendering

Do not copy 1:1:

- exact item union
- pending user-input behavior
- backend REST/SSE contract
- metadata and lineage persistence
- status/error item semantics

PlanningTreeMain V2 extends the CodexMonitor pattern with:

- `plan` as its own item kind
- `status` and `error` as first-class items
- pending user-input items that survive reload
- backend snapshot persistence
- thread registry and lineage reconciliation
- workflow side-channel events

## Target Architecture

Conversation content source of truth:

- `thread_snapshot_store_v2`

Thread metadata source of truth:

- `thread_registry_store`

Frontend render source of truth:

- `ConversationThreadStateV2.snapshot.items`

Runtime flow:

1. codex app-server emits raw events
2. `backend/ai/codex_client.py` adapts and normalizes upstream fields
3. `thread_runtime_service` owns turn lifecycle and runtime sequencing
4. `thread_event_projector` mutates `ThreadSnapshotV2`
5. `thread_snapshot_store_v2` persists authoritative snapshot state
6. SSE broker publishes thread or workflow events
7. frontend event router applies events into reducer state
8. UI renders directly from canonical items

## Canonical Types

```ts
type ThreadRole = "ask_planning" | "audit" | "execution";
type ProcessingState = "idle" | "running" | "waiting_user_input" | "failed";

type ItemStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled"
  | "requested"
  | "answer_submitted"
  | "answered"
  | "stale";

type ItemSource = "upstream" | "backend" | "local";
type ItemTone = "neutral" | "info" | "success" | "warning" | "danger" | "muted";

type ItemBase = {
  id: string;
  kind: "message" | "reasoning" | "plan" | "tool" | "userInput" | "status" | "error";
  threadId: string;
  turnId: string | null;
  sequence: number;
  createdAt: string;
  updatedAt: string;
  status: ItemStatus;
  source: ItemSource;
  tone: ItemTone;
  metadata: Record<string, unknown>;
};

type MessageItem = ItemBase & {
  kind: "message";
  role: "user" | "assistant" | "system";
  text: string;
  format: "markdown";
};

type ReasoningItem = ItemBase & {
  kind: "reasoning";
  summaryText: string;
  detailText: string | null;
};

type PlanStep = {
  id: string;
  text: string;
  status: "pending" | "in_progress" | "completed";
};

type PlanItem = ItemBase & {
  kind: "plan";
  title: string | null;
  text: string;
  steps: PlanStep[];
};

type ToolOutputFile = {
  path: string;
  changeType: "created" | "updated" | "deleted";
  summary: string | null;
};

type ToolItem = ItemBase & {
  kind: "tool";
  toolType: "commandExecution" | "fileChange" | "generic";
  title: string;
  toolName: string | null;
  callId: string | null;
  argumentsText: string | null;
  outputText: string;
  outputFiles: ToolOutputFile[];
  exitCode: number | null;
};

type UserInputAnswer = {
  questionId: string;
  value: string;
  label: string | null;
};

type UserInputQuestionOption = {
  label: string;
  description: string | null;
};

type UserInputQuestion = {
  id: string;
  header: string | null;
  prompt: string;
  inputType: "single_select" | "multi_select" | "text";
  options: UserInputQuestionOption[];
};

type UserInputItem = ItemBase & {
  kind: "userInput";
  requestId: string;
  title: string | null;
  questions: UserInputQuestion[];
  answers: UserInputAnswer[];
  requestedAt: string;
  resolvedAt: string | null;
};

type StatusItem = ItemBase & {
  kind: "status";
  code: string;
  label: string;
  detail: string | null;
};

type ErrorItem = ItemBase & {
  kind: "error";
  code: string;
  title: string;
  message: string;
  recoverable: boolean;
  relatedItemId: string | null;
};

type ConversationItem =
  | MessageItem
  | ReasoningItem
  | PlanItem
  | ToolItem
  | UserInputItem
  | StatusItem
  | ErrorItem;

type PendingUserInputRequest = {
  requestId: string;
  itemId: string;
  threadId: string;
  turnId: string | null;
  status: "requested" | "answer_submitted" | "answered" | "stale";
  createdAt: string;
  submittedAt: string | null;
  resolvedAt: string | null;
  answers: UserInputAnswer[];
};

type ThreadSnapshotV2 = {
  projectId: string;
  nodeId: string;
  threadRole: ThreadRole;
  threadId: string | null;
  activeTurnId: string | null;
  processingState: ProcessingState;
  snapshotVersion: number;
  createdAt: string;
  updatedAt: string;
  lineage: {
    forkedFromThreadId: string | null;
    forkedFromNodeId: string | null;
    forkedFromRole: ThreadRole | null;
    forkReason: string | null;
    lineageRootThreadId: string | null;
  };
  items: ConversationItem[];
  pendingRequests: PendingUserInputRequest[];
};
```

Schema rules:

- Python and TypeScript definitions must mirror each other 1:1.
- `id` is the canonical item identity for merge and patch.
- `sequence` is the only ordering key used for render.
- `message.role` is fixed at creation and never patched.
- `userInput.requestId` is a request handle, not the item identity.
- immutable audit records are represented as `message` items with `role="system"`.

## Patch Contract

```ts
type MessagePatch = {
  kind: "message";
  textAppend?: string;
  status?: ItemStatus;
  updatedAt: string;
};

type ReasoningPatch = {
  kind: "reasoning";
  summaryTextAppend?: string;
  detailTextAppend?: string;
  status?: ItemStatus;
  updatedAt: string;
};

type PlanPatch = {
  kind: "plan";
  textAppend?: string;
  stepsReplace?: PlanStep[];
  status?: ItemStatus;
  updatedAt: string;
};

type ToolPatch = {
  kind: "tool";
  title?: string;
  argumentsText?: string | null;
  outputTextAppend?: string;
  outputFilesAppend?: ToolOutputFile[];
  outputFilesReplace?: ToolOutputFile[];
  exitCode?: number | null;
  status?: ItemStatus;
  updatedAt: string;
};

type UserInputPatch = {
  kind: "userInput";
  answersReplace?: UserInputAnswer[];
  resolvedAt?: string | null;
  status?: Extract<ItemStatus, "requested" | "answer_submitted" | "answered" | "stale">;
  updatedAt: string;
};

type StatusPatch = {
  kind: "status";
  label?: string;
  detail?: string | null;
  status?: ItemStatus;
  updatedAt: string;
};

type ErrorPatch = {
  kind: "error";
  message?: string;
  relatedItemId?: string | null;
  status?: ItemStatus;
  updatedAt: string;
};

type ItemPatch =
  | MessagePatch
  | ReasoningPatch
  | PlanPatch
  | ToolPatch
  | UserInputPatch
  | StatusPatch
  | ErrorPatch;
```

Patch rules:

- `conversation.item.upsert` always carries a full item.
- `conversation.item.patch` always targets exactly one item.
- only fields ending in `Append` use append semantics
- only fields ending in `Replace` use replace semantics
- all other fields use replace semantics
- `updatedAt` is required in every patch
- patch kind must match the existing item kind
- a patch against a missing item is a protocol error or stream mismatch
- only `conversation.item.upsert` and `conversation.item.patch` may mutate `ConversationItem[]`

Immutable fields:

- `id`
- `kind`
- `threadId`
- `turnId`
- `sequence`
- `createdAt`
- `source`
- `message.role`
- `tool.toolType`
- `userInput.requestId`

Structured file-change rule:

- `outputFilesAppend` is optional preview-only incremental data
- `outputFilesReplace` is the authoritative final file list
- when both exist across the lifetime of one tool item, `outputFilesReplace` wins

## Backend API And SSE Contract

REST endpoints:

- `GET /v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}`
- `GET /v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/events?after_snapshot_version={n}`
- `POST /v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/turns`
- `POST /v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/requests/{request_id}/resolve`
- `POST /v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/reset`
- `GET /v2/projects/{project_id}/events`

Public GET semantics:

- `GET /threads/{role}` is ensure-and-read, not pure read
- it may repair metadata, bootstrap missing state, or mark stale request state before returning

Thread SSE event types:

- `thread.snapshot`
- `conversation.item.upsert`
- `conversation.item.patch`
- `thread.lifecycle`
- `conversation.request.user_input.requested`
- `conversation.request.user_input.resolved`
- `thread.reset`
- `thread.error`

Workflow SSE event types:

- `node.workflow.updated`
- `node.detail.invalidate`

Envelope:

```json
{
  "eventId": "evt_0001",
  "channel": "thread",
  "projectId": "p1",
  "nodeId": "n1",
  "threadRole": "ask_planning",
  "occurredAt": "2026-03-28T10:00:02Z",
  "snapshotVersion": 43,
  "type": "conversation.item.upsert",
  "payload": {}
}
```

Contract rules:

- `thread.snapshot` is the first frame of every V2 thread stream
- `snapshotVersion` is monotonic for each logical thread resource
- `persist-before-publish` is required for every thread mutation
- `message_created` does not exist in V2
- `conversation.request.user_input.*` and `thread.error` are companion events and do not bypass item mutation rules

## Metadata Synchronization Rules

Every metadata-bearing mutation must synchronize through `thread.snapshot`.

Metadata-bearing mutations include:

- bootstrap thread creation
- fork
- resume
- rebuild
- stale recovery
- registry or snapshot repair
- reset

Required sequence:

1. write metadata into `thread_registry_store`
2. reconcile the metadata into `ThreadSnapshotV2`
3. bump `snapshotVersion`
4. persist `thread_snapshot_store_v2`
5. publish `thread.snapshot`

No separate `thread.metadata.updated` event exists in the initial V2 rollout.

## Shared Internal Turn Contract

Only `thread_runtime_service` may mutate:

- `activeTurnId`
- `processingState`
- thread lifecycle events

Internal runtime API:

```ts
beginTurn({
  projectId,
  nodeId,
  threadRole,
  origin,       // "interactive" | "execution" | "review" | "auto_review"
  createdItems, // [] or [userItem]
}): TurnContext

completeTurn({
  projectId,
  nodeId,
  threadRole,
  turnId,
  outcome,      // "completed" | "failed" | "waiting_user_input"
  errorItem?,   // optional ErrorItem
}): void
```

`beginTurn` sequence:

1. ensure or reconcile the thread through `thread_query_service`
2. allocate `turnId`
3. set `activeTurnId`
4. set `processingState = "running"`
5. persist snapshot mutation, including `createdItems` if any
6. bump `snapshotVersion`
7. publish `conversation.item.upsert` for `createdItems`
8. publish `thread.lifecycle(state="turn_started")`

`completeTurn` sequence:

1. finalize open items if needed
2. publish all final item upserts or patches first
3. if waiting for user input, upsert the `userInput` item before emitting waiting lifecycle
4. if success, clear `activeTurnId` and emit `thread.lifecycle(state="turn_completed")`
5. if failure, upsert `ErrorItem` if present, emit `thread.error`, then emit `thread.lifecycle(state="turn_failed")`

## Raw Event Mapping

Raw event mapping rules:

- `item/started + agentMessage` -> upsert `message`
- `item/agentMessage/delta` -> patch `message.textAppend`
- `item/completed + agentMessage` -> patch `message.status = completed`
- `item/started + plan` -> upsert `plan`
- `item/plan/delta` -> patch `plan.textAppend`
- `item/completed + plan` -> patch `plan.status = completed`
- `item/reasoning/*` -> upsert or patch `reasoning`
- `item/started + commandExecution` -> upsert `tool`
- `item/commandExecution/outputDelta` -> patch `tool.outputTextAppend`
- `item/completed + commandExecution` -> patch `tool.status`, `exitCode`
- `item/started + fileChange` -> upsert `tool`
- `item/fileChange/outputDelta` -> preview patch using `outputTextAppend` and optional `outputFilesAppend`
- `item/completed + fileChange` -> authoritative patch using `outputFilesReplace`
- `item/tool/requestUserInput` -> upsert `userInput`, persist `PendingUserInputRequest`, publish requested companion event
- `serverRequest/resolved` -> patch `userInput` answers by `itemId`, patch ledger by `requestId`, publish resolved companion event
- `item/tool/call` -> provisional enrichment keyed by `callId`, collapsed into typed tool item when present
- `thread/status/changed` -> lifecycle state update, optional `status` item if user-visible
- `turn/completed` -> authoritative terminal lifecycle signal

Tool de-duplication rules:

- typed upstream item id is the canonical tool identity
- raw `item/tool/call` may only create provisional state keyed by `callId`
- provisional tool state must collapse into the typed tool item if that item appears later
- provisional tool state may only finalize as a generic tool item if the turn ends without a typed tool item ever appearing

## Audit Cutover Rule

Audit is a whole-namespace cutover.

Before production audit cutover:

- no production path may write audit records through `append_immutable_audit_record(...)`
- `node_detail_service.py` frame and spec audit writes must go through `thread_runtime_service.upsert_system_message()` or an equivalent V2 abstraction
- `review_service.py` rollup package writes must go through the same V2 abstraction

## Testing Invariants

Required invariant tests:

- live event state equals fresh snapshot state
- patch semantics are identical in backend and frontend
- tool provisional collapse never leaves duplicates
- `outputFilesReplace` overwrites preview file lists
- metadata-bearing mutations always emit `thread.snapshot`
- user-input resolution always bridges `requestId` and `itemId`
- no pair-based message assumption remains anywhere in reducer or runtime paths

## Open Questions

- whether upstream always emits `itemId` for every agent message delta
- whether file-change completed payload always includes an authoritative final file list
- whether interrupted turns should surface as `failed` or `idle + warning status` after the terminal event
