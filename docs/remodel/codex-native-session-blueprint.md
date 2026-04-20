# PlanningTree Session Core V2 Blueprint (Codex-Native, Parallel Rewrite)

Last updated: 2026-04-20  
Status: Approved direction, implementation blueprint  
Owner: Platform (backend + frontend)  
Primary objective: Build a clean Thread/Session core from scratch, run in parallel, cut over hard, keep rollback safe.

Executable contract pack (v1): `docs/remodel/contracts/session-core-v2/*`

---

## 1) Decision Summary

PlanningTree will build a new `Session Core V2` that maps directly to Codex app-server semantics and runs in parallel with legacy architecture.

Key decisions:

1. Rewrite from scratch for thread/session core.
2. Run parallel path first (`legacy` and `v2` coexist).
3. Do not mix old and new logic in the same module.
4. Do not delete legacy path before parity and cutover gates pass.
5. Build parity harness for state and event equivalence.
6. Keep rollback door open at every rollout phase.
7. Phase 1 behavior has no ask/audit/execution business specialization:
   - all thread UIs behave as generic thread/session console,
   - all flows use same thread primitives.

---

## 2) Scope, Non-Goals, and Guardrails

### In scope (Core V2)

- JSON-RPC 2.0 session runtime over stdio (default transport).
- Connection lifecycle and handshake.
- Codex-native primitives (`Thread`, `Turn`, `Item`).
- Runtime journal and snapshot durability for replay/resume.
- Thread lifecycle APIs and event stream.
- Turn lifecycle APIs and event stream.
- Server-request lifecycle (`requestUserInput`, approvals).
- Canonical frontend session store driven by native stream semantics.
- Codex-like thread/session UI shell for Phase 1.
- Parity harness, canary, hard cutover, rollback.

### Out of scope for Phase 1

- ask/execution/audit workflow policy behavior.
- queue policy and operator gating from legacy workflow.
- node-domain workflow transitions (review, mark done, etc.).
- migration of all business metadata into V2.

### Guardrails

1. No import dependency from V2 core to:
   - `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
   - `backend/ai/codex_client.py`
2. Legacy and V2 runtime live in separate modules and separate route namespaces.
3. Frontend shells are isolated; no "half old half new" module.
4. Every phase must have explicit cut criteria and rollback criteria.

---

## 3) Direct Mapping from Codex Semantics

This section is the contract target for V2.

### 3.1 Protocol and connection lifecycle

- JSON-RPC 2.0 bi-directional protocol.
- stdio transport as default.
- Client must call:
  1. `initialize`
  2. `initialized` notification
- Any request before handshake completion is invalid.
- `initialize` must support:
  - `clientInfo.name`
  - `clientInfo.version`
  - `capabilities.experimentalApi`
  - `capabilities.optOutNotificationMethods`

### 3.2 Core primitives

V2 data model is built on:

- `Thread`: conversation container and runtime status owner.
- `Turn`: one interaction cycle with terminal status.
- `Item`: persisted/context-visible units.

Required item families:

- `userMessage`
- `agentMessage`
- `reasoning`
- `commandExecution`
- `fileChange`
- `plan`
- `userInput`
- `error`

### 3.3 Thread lifecycle feature set

Must support:

- `thread/start`
- `thread/resume`
- `thread/fork`
- `thread/list`
- `thread/read`
- `thread/turns/list`
- `thread/loaded/list`
- `thread/unsubscribe`
- runtime notifications:
  - `thread/started`
  - `thread/status/changed`
  - `thread/closed`

Thread fork behavior target:

- if source thread is mid-turn, create interruption marker and avoid inheriting partial suffix.
- support `ephemeral: true` threads (in-memory only, no persistent path).

Thread status model target:

- `notLoaded`
- `idle`
- `active`
- `systemError`

Loaded lifecycle target:

- unsubscribe disconnects this subscriber only.
- server unload policy based on inactivity and no subscribers (target: 30 minutes).

### 3.4 Turn/runtime feature set

Must support:

- `turn/start` with turn-level overrides:
  - `model`
  - `cwd`
  - `approvalPolicy`
  - `sandboxPolicy`
  - `personality`
  - `effort`
  - `summary`
  - `outputSchema` (turn-local)
- `turn/steer`
- `turn/interrupt`
- `thread/inject_items`

### 3.5 Event stream feature set

Must stream item lifecycle in native order:

1. `item/started`
2. delta notifications (`item/agentMessage/delta`, `item/plan/delta`, reasoning deltas, command/file deltas)
3. `item/completed`
4. `turn/completed`

Must preserve semantic separation by item type (do not collapse everything into assistant text).

### 3.6 Error model target

V2 must carry distinct error categories across turn lifecycle:

- state errors (`ActiveTurnNotSteerable`, invalid thread/turn references)
- sandbox/permission errors
- model/provider errors
- stream/disconnect errors
- context/usage limit errors

Terminal turn status target includes at least:

- `completed`
- `failed`
- `interrupted`
- `waiting_user_input`

### 3.7 Server-request and approvals lifecycle

Must support server-initiated request pattern:

- request arrives (`item/tool/requestUserInput`, approval requests)
- client resolves request
- server emits `serverRequest/resolved`
- authoritative finalization remains on item completion events

Required request families for V2:

- `item/tool/requestUserInput`
- `item/commandExecution/requestApproval`
- `item/fileChange/requestApproval`
- `item/permissions/requestApproval` (phase-gated)
- MCP elicitation request pattern (phase-gated)

---

## 4) Parallel Architecture (No Mixed Modules)

## 4.1 Runtime lanes

- Legacy lane (unchanged): current routes, stores, services.
- V2 lane (new): clean session core.

No shared "hybrid" core module.

## 4.2 Backend module layout (new)

Create:

- `backend/session_core_v2/transport/stdio_jsonrpc.py`
- `backend/session_core_v2/protocol/codec.py`
- `backend/session_core_v2/protocol/models.py`
- `backend/session_core_v2/connection/manager.py`
- `backend/session_core_v2/connection/state_machine.py`
- `backend/session_core_v2/threads/service.py`
- `backend/session_core_v2/turns/service.py`
- `backend/session_core_v2/events/stream_router.py`
- `backend/session_core_v2/events/priority_queue.py`
- `backend/session_core_v2/events/journal.py`
- `backend/session_core_v2/events/replay.py`
- `backend/session_core_v2/requests/registry.py`
- `backend/session_core_v2/requests/resolver.py`
- `backend/session_core_v2/storage/thread_store.py`
- `backend/session_core_v2/storage/runtime_store.py`
- `backend/session_core_v2/storage/snapshot_store.py`
- `backend/session_core_v2/api/router.py`
- `backend/session_core_v2/parity/harness.py`

Rule:

- V2 does not import legacy `backend/ai/codex_client.py`.
- Legacy does not need to import V2.

## 4.3 Frontend module layout (new)

Create:

- `frontend/src/features/session_v2/shell/SessionConsoleV2.tsx`
- `frontend/src/features/session_v2/store/threadSessionStore.ts`
- `frontend/src/features/session_v2/store/connectionStore.ts`
- `frontend/src/features/session_v2/store/pendingRequestsStore.ts`
- `frontend/src/features/session_v2/state/applySessionEvent.ts`
- `frontend/src/features/session_v2/state/sessionEventParser.ts`
- `frontend/src/features/session_v2/api/client.ts`
- `frontend/src/features/session_v2/components/*`

Rule:

- no import from `threadByIdStoreV3.ts`.
- no feature mixing inside same store.

## 4.4 Route isolation

Introduce new namespace:

- `/v4/session/*` for V2 APIs.
- keep old `/v3/*` fully intact until hard cutover.

## 4.5 Runtime source of truth

Hard contract:

- `backend/session_core_v2` journal + snapshot is the runtime source of truth.
- frontend stores (`threadSessionStore`, `connectionStore`, `pendingRequestsStore`) are projection/render caches only.
- replay, resume, and reconnect recovery never depend on frontend state.

---

## 5) Core V2 State Contracts

## 5.1 Connection state

```ts
type ConnectionState =
  | { phase: "disconnected" }
  | { phase: "connecting" }
  | { phase: "initialized"; clientName: string; serverVersion: string }
  | { phase: "error"; code: string; message: string };
```

## 5.2 Thread primitive

```ts
type ThreadStatus = "notLoaded" | "idle" | "active" | "systemError";

type SessionThread = {
  id: string;
  name: string | null;
  model: string;
  modelProvider: string;
  cwd: string | null;
  ephemeral: boolean;
  archived: boolean;
  status: ThreadStatus;
  createdAtMs: number;
  updatedAtMs: number;
  metadata: Record<string, unknown>;
};
```

## 5.3 Turn primitive

```ts
type TurnStatus = "idle" | "running" | "waiting_user_input" | "completed" | "failed" | "interrupted";

type SessionTurn = {
  id: string;
  threadId: string;
  status: TurnStatus;
  startedAtMs: number;
  completedAtMs: number | null;
  error: { type: string; message: string } | null;
};
```

## 5.4 Item primitive

```ts
type ItemKind =
  | "userMessage"
  | "agentMessage"
  | "reasoning"
  | "plan"
  | "commandExecution"
  | "fileChange"
  | "userInput"
  | "error";

type SessionItem = {
  id: string;
  threadId: string;
  turnId: string | null;
  kind: ItemKind;
  status: "in_progress" | "completed" | "failed";
  createdAtMs: number;
  updatedAtMs: number;
  payload: Record<string, unknown>;
};
```

## 5.5 Pending server request model

```ts
type PendingServerRequest = {
  requestId: string;
  method: string;
  threadId: string;
  turnId: string;
  itemId: string | null;
  status: "pending" | "submitted" | "resolved" | "rejected" | "expired";
  createdAtMs: number;
  submittedAtMs: number | null;
  resolvedAtMs: number | null;
  payload: Record<string, unknown>;
};
```

## 5.6 Turn state machine contract

Allowed transitions:

1. `not_created -> idle` via accepted `turn/start`.
2. `idle -> running` when first runtime item is emitted.
3. `running -> running` via accepted `turn/steer`.
4. `running -> waiting_user_input` when server request is emitted and unresolved.
5. `waiting_user_input -> running` via valid resolve/reject continuation.
6. `running|waiting_user_input -> interrupted` via valid `turn/interrupt`.
7. `running -> completed|failed` via terminal model/runtime completion.

Terminal invariants:

- `completed`, `failed`, `interrupted` are terminal.
- `turn/steer`, `turn/interrupt`, and request resolve/reject against terminal turns must fail deterministically.
- deterministic state errors must be stable across reconnect/retry (`ERR_TURN_TERMINAL`, `ERR_TURN_NOT_STEERABLE`, `ERR_REQUEST_STALE`).

---

## 6) API Contract for V2 (`/v4/session`)

## 6.1 Connection

- `POST /v4/session/initialize`
- `GET /v4/session/status`

Notes:

- `initialized` is an internal protocol transition emitted by the session manager to Codex app-server after successful `initialize`.
- do not expose `POST /v4/session/initialized` as public REST by default.
- only add a public `initialized` bridge if a non-embedded remote client actually requires two-step handshake control.

## 6.2 Threads

- `POST /v4/session/threads/start`
- `POST /v4/session/threads/{threadId}/resume`
- `POST /v4/session/threads/{threadId}/fork`
- `GET /v4/session/threads/list`
- `GET /v4/session/threads/{threadId}/read`
- `GET /v4/session/threads/{threadId}/turns`
- `GET /v4/session/threads/loaded/list`
- `POST /v4/session/threads/{threadId}/unsubscribe`

Phase-gated:

- `POST /v4/session/threads/{threadId}/archive`
- `POST /v4/session/threads/{threadId}/unarchive`
- `POST /v4/session/threads/{threadId}/name/set`
- `POST /v4/session/threads/{threadId}/metadata/update`
- `POST /v4/session/threads/{threadId}/rollback`

## 6.3 Turns

- `POST /v4/session/threads/{threadId}/turns/start`
- `POST /v4/session/threads/{threadId}/turns/{turnId}/steer`
- `POST /v4/session/threads/{threadId}/turns/{turnId}/interrupt`
- `POST /v4/session/threads/{threadId}/inject-items`

Write contract:

- all mutating turn requests must include `clientActionId` (string, caller-generated, stable across retries).

## 6.4 Server requests

- `GET /v4/session/requests/pending`
- `POST /v4/session/requests/{requestId}/resolve`
- `POST /v4/session/requests/{requestId}/reject`

Write contract:

- all resolve/reject calls must include `resolutionKey` (string, caller-generated, stable across retries).

## 6.5 Event stream

- `GET /v4/session/threads/{threadId}/events`

## 6.6 Request idempotency contract

1. `clientActionId` applies to:
   - `turn/start`
   - `turn/steer`
   - `turn/interrupt`
   - `thread/inject-items` (if mutating)
2. `resolutionKey` applies to:
   - `requests/{requestId}/resolve`
   - `requests/{requestId}/reject`
3. duplicate key with same payload returns previously accepted result (no duplicate side effects).
4. duplicate key with different payload returns deterministic conflict (`ERR_IDEMPOTENCY_PAYLOAD_MISMATCH`).
5. resolve/reject for stale or already-terminal request returns deterministic state error (`ERR_REQUEST_STALE`).
6. idempotency records are persisted with journal sequence reference for replay-consistent behavior across reconnect/restart.

---

## 7) Event Priority and Backpressure Policy

Core rule:

- Tier 0 is lossless by `journal + replay`, not by blocking producer execution.
- transport consumers must not directly throttle model/runtime execution.

## 7.1 Journal-first delivery pipeline

1. runtime producer appends canonical event to backend journal first.
2. append ack updates runtime store/snapshot metadata.
3. stream router fans out from journal using subscriber cursor.
4. lagging subscriber is reset to replay mode (not allowed to stall producer).
5. replay uses cursor; if cursor invalid/expired, server returns deterministic resync error.

## 7.2 Priority tiers

Tier 0 (lossless, replay-authoritative):

- `item/started`
- `item/agentMessage/delta`
- `item/plan/delta`
- `item/completed`
- `turn/completed`
- `thread/status/changed`
- all server requests and `serverRequest/resolved`

Tier 0 behavior:

- never dropped from journal.
- per-subscriber delivery can be interrupted/reset under pressure.
- recovery is replay by cursor (or snapshot + replay), not producer blocking.

Tier 1 (merge-safe):

- reasoning deltas
- command/file output deltas

Tier 1 behavior:

- coalesce by `(threadId, turnId, itemId, method)` window.
- keep chunk boundaries semantically valid.

Tier 2 (best effort):

- cosmetic progress signals
- optional diagnostics

Tier 2 behavior:

- drop allowed under pressure with explicit counters.

## 7.3 Session durability and replay contract

1. Event ID format:
   - per-thread monotonic sequence `eventSeq` (`uint64`).
   - composite identifier `{threadId}:{eventSeq}`.
2. Cursor semantics:
   - cursor means "last fully applied `eventSeq`".
   - replay starts at `cursor + 1`.
3. Snapshot contract:
   - snapshots are versioned (`snapshotVersion`) per thread.
   - snapshot contains thread state + turn/item/request indexes + last `eventSeq`.
   - default snapshot cadence: configurable, with target every 200 Tier 0 events or 10 seconds (whichever comes first).
4. Replay retention:
   - retain journal window per thread by configurable event count and age.
   - initial production target: at least 7 days or 200k events per thread (whichever is larger).
5. Cursor miss fallback:
   - if cursor is outside retention, return `ERR_CURSOR_EXPIRED` with latest snapshot pointer.
   - client must perform deterministic resync from snapshot baseline + available forward replay.

Backpressure telemetry:

- journal append latency
- per-subscriber queue depth
- replay reset count
- cursor-expired count
- drop counts by tier (Tier 2 only)

---

## 8) Phase 1 UI Contract (Codex-like Session Console)

Phase 1 UI must treat all threads uniformly.

No lane-specific business UI:

- no ask-specific composer rules
- no execution/audit special action panel
- no workflow transition buttons inside V2 shell

Required UI surfaces:

1. Thread list panel
2. Thread transcript panel (item-typed rendering)
3. Composer
4. Active turn controls (`steer`, `interrupt`)
5. Pending request drawer/modal (`requestUserInput`, approvals)
6. Runtime status indicators (connection, thread status, turn status)

Functional parity target with Codex session UX:

- event-driven incremental rendering by item type
- explicit turn terminal state
- request/resolve loop with authoritative completion from events

---

## 9) Parity Harness Design

Parity harness is mandatory before cutover.

## 9.1 Harness outputs

For each scenario, emit:

- raw rpc transcript (`request`, `response`, `notification`)
- normalized event trace
- canonical end-state snapshot
- diff report (legacy vs v2)

## 9.2 Comparison dimensions

1. Protocol semantics:
   - handshake order and rejection behavior
   - request/response shape
2. Event order:
   - item lifecycle order
   - turn terminal sequencing
3. State parity:
   - thread status
   - turn status
   - item set and item terminal statuses
   - pending request lifecycle
4. Error parity:
   - category mapping and terminal status mapping

## 9.3 Harness modes

- `offline-replay`: deterministic transcript replay to both engines.
- `shadow-read`: V2 parses live stream in observer mode, no user-visible effects.
- `canary-live`: V2 serves real users under allowlist.

## 9.4 Required parity suites

1. thread start/resume/fork baseline
2. active turn streaming and completion
3. turn steer while running
4. turn interrupt terminal path
5. requestUserInput roundtrip
6. command approval roundtrip
7. fileChange approval roundtrip
8. reconnect + replay cursor
9. queue pressure + backpressure
10. fork from mid-turn

---

## 10) Rollout, Cutover, and Rollback

## 10.1 Runtime flags

Backend:

- `SESSION_CORE_V2_MODE=off|shadow|canary|on`
- `SESSION_CORE_V2_ALLOWLIST=<project ids>`

Frontend:

- `VITE_SESSION_V2_UI=off|shadow|on`
- `VITE_SESSION_V2_ALLOWLIST=<project ids>`

## 10.2 Rollout phases

### Phase P0: Contract Freeze

- finalize v2 protocol and state contracts.
- finalize runtime source-of-truth boundary (backend authoritative, frontend projection-only).
- freeze session durability/replay contract (event id, cursor, snapshot, retention, cursor-miss fallback).
- freeze idempotency contract (`clientActionId`, `resolutionKey`, duplicate and stale semantics).
- freeze turn state machine transitions and deterministic illegal-transition errors.
- freeze parity suite definitions.
- phase closeout artifact: `docs/remodel/contracts/session-core-v2/phase-0-gate-report-v1.md`.

Exit gate:

- architecture and contract signoff.

### Phase P1: Core Skeleton

- implement handshake, connection state machine, typed models.
- implement thread start/resume/read/list minimal path.

Exit gate:

- integration tests pass for P1 methods.

### Phase P2: Turn Runtime

- implement turn start/steer/interrupt.
- implement item lifecycle stream routing.

Exit gate:

- turn runtime suites pass.
- legal/illegal state transition suite passes with deterministic error codes.

### Phase P3: Server Request Lifecycle

- implement pending request registry.
- implement resolve/reject APIs and resolved ack handling.

Exit gate:

- request lifecycle suites pass.
- idempotency duplicate/retry suite passes for turn actions and request resolutions.

### Phase P4: V2 UI Shell

- ship isolated session console UI.
- no business lane logic.

Exit gate:

- UI acceptance test matrix pass.

### Phase P5: Parity Shadow

- enable shadow mode for allowlisted projects.
- collect parity diff reports.
- verify replay behavior under lagged subscribers and cursor-expired recovery paths.

Exit gate:

- no critical parity diffs for agreed suite window.

### Phase P6: Canary Live

- enable v2 for small allowlist.
- monitor SLOs and error budget.

Exit gate:

- canary stability threshold met.

### Phase P7: Hard Cutover

- switch default route to V2.
- keep legacy path available behind rollback flag.

Exit gate:

- full production SLO stability over agreed soak period.

## 10.3 Rollback rules

Rollback trigger examples:

- Tier 0 event integrity failure
- unresolved request registry corruption
- protocol incompatibility with app-server behavior
- sustained SLO breach

Rollback action:

1. flip frontend flag to legacy shell.
2. flip backend mode to legacy service path.
3. keep V2 logs/transcripts for forensic parity analysis.

Rollback must be config-only (no destructive migration required).

---

## 11) Hard Separation from Legacy

To avoid "half old half new":

1. New routes only in `/v4/session/*`.
2. New frontend feature root `features/session_v2/*`.
3. New backend root `backend/session_core_v2/*`.
4. No shared monolithic store.
5. No refactor-in-place inside legacy modules.

Legacy remains untouched except:

- route registration for new namespace
- optional bridge for parity harness instrumentation

---

## 12) Testing and Quality Gates

## 12.1 Unit

- state machine transitions
- illegal transition rejection with deterministic errors
- event parser strictness
- item reducer correctness
- request registry transitions
- idempotency key conflict and replay semantics

## 12.2 Integration

- full request/notification roundtrip over stdio json-rpc
- reconnect, replay cursor, lagged subscriber behavior
- cursor expired fallback and snapshot resync path
- steer/interrupt race conditions

## 12.3 Load and backpressure

- saturated stream with mixed tier events
- ensure Tier 0 journal no-drop guarantee
- verify lagged consumers cannot block runtime producer
- controlled behavior under queue full conditions

## 12.4 UI E2E

- generic thread lifecycle
- item-typed rendering
- pending request modal resolve path
- interrupt and steer UX

---

## 13) SLO Targets for Cutover

Required during canary and early post-cutover:

1. Tier 0 journal dropped event count = 0
2. request resolution ack mismatch = 0
3. p95 turn terminal render lag <= 300 ms (local desktop target)
4. reconnect recovery success >= 99.9% in allowlist window
5. no unresolved pending request older than threshold (for example 5 minutes) without explicit status
6. lagged-subscriber reset recovery success >= 99.9% in canary window

---

## 14) Post-Core Roadmap (After Stable Cutover)

Only after V2 session core is stable:

1. Reintroduce PlanningTree workflow projections on top of V2 session signals.
2. Add ask/execution/audit domain behavior as separate policy layer.
3. Add queue/operator gating as business projection module.
4. Add thread utilities (`archive`, `rollback`, `compact`) by product priority.
5. Add MCP elicitation and granular permissions flow if needed.

Rule:

- business features are consumers of V2 session core, not owners of protocol semantics.

## 14.1 Session Binding Contract (Reserved for post-core integration)

Reserved integration points for phase 2+ business mapping:

1. Thread-domain ownership:
   - `thread.metadata.domain.projectId`
   - `thread.metadata.domain.nodeId`
   - `thread.metadata.domain.phase` (ask/execution/audit)
2. Lineage rules:
   - `thread/fork` must write `metadata.lineage.parentThreadId` and `metadata.lineage.forkedAtEventSeq`.
   - business branch actions must consume lineage metadata, not clone transcript outside core.
3. Turn-domain annotations:
   - turn-local business tags are attached under `turn.metadata.domain.*`.
   - session core does not interpret domain tags.
4. Ownership boundary:
   - session core owns protocol/runtime semantics.
   - workflow/business layer owns policy transitions and operator gating.
5. Compatibility rule:
   - domain binding must be additive metadata only; no mutation of core Thread/Turn/Item invariants.

---

## 15) Definition of Done for Session Core V2

V2 is considered complete for hard cutover when:

1. protocol parity suite passes for mandatory scenarios.
2. v2 UI shell operates without legacy store dependencies.
3. no Tier 0 event loss under stress and canary.
4. server request lifecycle is deterministic and auditable.
5. idempotency and turn state machine contracts are fully enforced.
6. backend journal/snapshot remains the only runtime source of truth.
7. cutover and rollback are both one-flag operations.

---

## 16) Immediate Build Order (Recommended Next 4 Milestones)

Milestone 1:

- scaffold `backend/session_core_v2/*`, `/v4/session/initialize`, and journal/snapshot foundation.
- implement contract tests for handshake, idempotency key persistence, and turn state machine baseline.

Milestone 2:

- implement `thread/start|resume|fork|read|list` + status events + `loaded/list`.

Milestone 3:

- implement `turn/start|steer|interrupt` + item lifecycle stream reducer.

Milestone 4:

- implement pending server request registry + resolve path + V2 session console shell.
- implement replay endpoint behavior for cursor recovery and cursor-expired fallback.

This sequence keeps risk low and supports shadow parity quickly.
