# Phase 6: Execution and Audit Production Cutover

Status: in progress.

## Goal

Cut execution and the full audit namespace to V2 in production without splitting the audit namespace across V1 and V2, then close the phase only once the execution and audit surfaces reach semantic presentation parity with the active spec and the closest practical CodexMonitor patterns.

## In Scope

- production execution conversation path
- production audit namespace
- workflow bridge production enablement
- semantic presentation parity for execution and audit V2 surfaces
- CodexMonitor-style view-state and streaming UX where the active spec calls for lifecycle or view-state separation
- cutover monitoring and rollback plan

## Out of Scope

- ask-planning cutover
- hard cleanup of V1 files

## Preconditions

- Phase 5 complete
- no production audit writer remains on V1 helper paths
- V2 backend core and frontend path are validated in isolated rehearsal

## Checklist

- enable V2 routes and runtime for execution
- enable V2 routes and runtime for all audit producers
- confirm manual audit, rollup audit, frame/spec audit records, and auto-review persistence all land in V2
- enable workflow bridge production path
- confirm read-only rules still hold for execution and automated audit contexts
- close semantic presentation findings on execution and audit feeds before marking the phase complete
- monitor mismatch, reconnect, and error rates during rollout

## Implemented So Far

- added dedicated production gate `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED`
- wired `backend/main.py` and config helpers so production cutover does not reuse the rehearsal-only flag
- switched `FinishTaskService.finish_task()` production branching onto the shared V2 execution runtime
- migrated production auto-review transcript flow onto V2 audit turns via `thread_runtime_service_v2.begin_turn()`, `stream_agent_turn()`, and `complete_turn()`
- kept legacy auto-review transcript persistence off the production V2 path
- switched `ReviewService.start_review_rollup()` production branching onto the V2 rollup path
- preserved V2 system-message audit writers for immutable frame/spec records and accepted rollup package records
- moved production graph, sidebar, `/chat`, and `/chat-v2` routing so execution and audit surfaces land on `/chat-v2`, while ask redirects back to `/chat`
- added targeted backend plus frontend coverage for production cutover routing and transcript behavior

## What Is Still Missing Before Phase 6 Can Close

The production cutover path is substantially landed, but the execution surface still falls short of semantic presentation parity with CodexMonitor in six ways:

1. the V2 feed still renders as a flat list of rows instead of using a dedicated view-state layer for grouped entries
2. the working indicator is generic and does not surface semantic progress labels from reasoning
3. tool streaming is rendered as static cards rather than a command-stream-oriented surface
4. auto-scroll always forces the viewport to the bottom instead of respecting near-bottom semantics
5. reasoning items are rendered, but not semanticized into progress labels or filtered for empty bodies
6. backend projection still ignores `item/commandExecution/terminalInteraction`, so some command semantics never reach canonical tool items

Phase 6 remains open until the execution and audit V2 surfaces close these gaps.

## Semantic Presentation Closeout Plan

### Workstream A: Add a dedicated frontend view-state layer

Goal:

- move the V2 feed closer to CodexMonitor by separating item rendering from view-state derivation

Required changes:

- add `frontend/src/features/conversation/components/useConversationViewState.ts`
- move expansion state, collapsed tool-group state, near-bottom auto-scroll state, and derived grouped entries into this hook
- update `ConversationFeed.tsx` to render grouped entries rather than `items.map(...)` directly
- preserve the active spec rule that the canonical render source remains `ConversationItem[]`; grouping is a pure view-state transform, not a second transcript model

CodexMonitor references:

- `src/features/messages/components/Messages.tsx`
- `src/features/messages/components/useMessagesViewState.ts`

### Workstream B: Upgrade the working indicator from generic to semantic

Goal:

- show the user what the agent is doing, not just that a turn is active

Required changes:

- extend frontend V2 thread store state with local view telemetry:
  - `processingStartedAt`
  - `lastCompletedAt`
  - `lastDurationMs`
- update reducer or store transition handling so `thread.lifecycle(turn_started)` starts a timer window and terminal lifecycle events close it
- derive `latestReasoningLabel` from visible reasoning items in `useConversationViewState.ts`
- update `WorkingIndicator.tsx` to accept `reasoningLabel`, timer data, and optional done-state display

CodexMonitor references:

- `src/features/messages/components/Messages.tsx`
- `src/features/messages/components/MessageRows.tsx`
- `src/features/messages/components/useMessagesViewState.ts`

### Workstream C: Bring tool streaming UX closer to CodexMonitor

Goal:

- make command and file-change items feel like live tool execution instead of static cards

Required changes:

- extend `ToolRow.tsx` with command-output presentation suitable for live append semantics
- add a scrollable command-output viewport for `toolType="commandExecution"`
- support view-state-driven expansion and collapse for tool rows
- add tool grouping for adjacent tool-heavy segments in `useConversationViewState.ts`
- allow grouped tool sections to collapse and expand without mutating canonical items
- wire tool rows to `requestAutoScroll()` when live output is appending and the user is already near the bottom

CodexMonitor references:

- `src/features/messages/components/Messages.tsx`
- `src/features/messages/components/MessageRows.tsx`

### Workstream D: Semanticize reasoning instead of only rendering it

Goal:

- use reasoning to improve live progress semantics

Required changes:

- add reasoning parsing helpers under `frontend/src/features/conversation/` or `frontend/src/features/conversation/utils/`
- filter out empty reasoning bodies from visible grouped entries
- derive `latestReasoningLabel` from the most relevant in-progress reasoning item
- keep the raw reasoning item in canonical state untouched; semanticization happens only in view-state

CodexMonitor references:

- `src/features/messages/components/useMessagesViewState.ts`

### Workstream E: Fix destructive auto-scroll behavior

Goal:

- stop the execution feed from fighting the user during long-running tool output

Required changes:

- remove unconditional scroll-to-bottom behavior from `ConversationFeed.tsx`
- implement `updateAutoScroll()` and `requestAutoScroll()` semantics in `useConversationViewState.ts`
- auto-scroll only when the user is already near the bottom
- keep explicit live-output auto-scroll for command output when the viewport is pinned

CodexMonitor references:

- `src/features/messages/components/useMessagesViewState.ts`
- `src/features/messages/components/MessageRows.tsx`

### Workstream F: Project command terminal interaction into canonical tool output

Goal:

- ensure command-interaction semantics make it from backend runtime to frontend canonical items

Required changes:

- extend `backend/conversation/projector/thread_event_projector.py` to handle `item/commandExecution/terminalInteraction`
- patch the canonical `tool` item via `outputTextAppend`
- normalize terminal input similarly to CodexMonitor by appending a clear marker such as:
  - `[stdin]`
  - normalized stdin content
- add backend unit tests for terminal interaction projection
- add integration coverage proving a command tool item shows terminal interaction text in the V2 feed

CodexMonitor references:

- `src/features/app/hooks/useAppServerEvents.ts`
- `src/features/threads/hooks/useThreadItemEvents.ts`

## Required File Targets For Phase 6 Closeout

Frontend:

- `frontend/src/features/conversation/components/ConversationFeed.tsx`
- `frontend/src/features/conversation/components/ToolRow.tsx`
- `frontend/src/features/conversation/components/ReasoningRow.tsx`
- `frontend/src/features/conversation/components/WorkingIndicator.tsx`
- `frontend/src/features/conversation/components/ItemRow.tsx`
- `frontend/src/features/conversation/state/threadStoreV2.ts`
- `frontend/src/features/conversation/state/applyThreadEvent.ts`
- new `frontend/src/features/conversation/components/useConversationViewState.ts`
- optional new helper utils under `frontend/src/features/conversation/`

Backend:

- `backend/conversation/projector/thread_event_projector.py`
- `backend/ai/codex_client.py` only if additional event normalization is still needed

Tests:

- `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
- `frontend/tests/unit/threadStoreV2.test.ts`
- `frontend/tests/unit/applyThreadEvent.test.ts`
- new unit coverage for semantic view-state grouping and working-indicator behavior
- `backend/tests/unit/test_conversation_v2_projector.py`
- `backend/tests/integration/test_phase6_execution_audit_cutover.py`

## Verification Evidence So Far

- backend unit: `python -m pytest backend/tests/unit/test_finish_task_service.py backend/tests/unit/test_review_service.py`
- backend integration: `python -m pytest backend/tests/integration/test_phase6_execution_audit_cutover.py`
- frontend route suite: `npm run test:unit --prefix frontend -- GraphWorkspace.test.tsx Sidebar.test.tsx BreadcrumbChatView.test.tsx BreadcrumbChatViewV2.test.tsx`

## Remaining To Close The Phase

- implement Workstreams A through F above
- populate rollout artifacts under `artifacts/phase-6/`
- run and record staging or production-like smoke with the production flag enabled
- capture semantic-parity verification evidence, not just route or transport evidence
- document rollback steps and observed telemetry after first enablement window
- mark `progress.yaml` and this phase doc as completed only after rollout evidence is attached and semantic presentation parity checks pass

## Verification

- targeted production-like integration pass
- smoke checks for execution feed, audit feed, workflow refresh, and audit system messages
- semantic parity checks for:
  - grouped tool rendering
  - reasoning-derived progress labels
  - non-destructive auto-scroll during long tool output
  - command output viewport behavior
  - command terminal interaction projection

## Exit Criteria

- execution uses V2 end to end
- audit namespace uses V2 end to end
- no audit producer writes V1 transcript state
- execution and audit V2 surfaces match the active spec's lifecycle or view-state separation intent
- execution semantic presentation is close to CodexMonitor in grouped rendering, reasoning progress display, tool streaming, and working-indicator behavior
- `item/commandExecution/terminalInteraction` reaches canonical tool items and is visible in the V2 feed

## Artifacts To Produce

- `artifacts/phase-6/cutover-checklist.md`
- `artifacts/phase-6/smoke-results.md`
- `artifacts/phase-6/rollback-notes.md`
- `artifacts/phase-6/semantic-presentation-parity-plan.md`
- `artifacts/phase-6/semantic-parity-verification.md`
