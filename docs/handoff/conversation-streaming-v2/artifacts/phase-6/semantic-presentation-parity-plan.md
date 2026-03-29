# Phase 6 Semantic Presentation Parity Plan

Status: active closeout plan for Phase 6.

## Objective

Close Phase 6 only after execution and audit V2 surfaces follow the active spec and match CodexMonitor as closely as practical in semantic presentation, not just in transport and persistence.

## Why This Exists

Execution and audit production cutover is largely landed, but the V2 feed still under-delivers on semantic streaming UX:

- feed rendering is flat
- working indicator is generic
- tool streaming lacks command-centric presentation
- auto-scroll is destructive during long output
- reasoning does not drive progress semantics
- command terminal interaction is not yet projected into canonical tool output

## Closeout Workstreams

### 1. View-State Layer

Create `frontend/src/features/conversation/components/useConversationViewState.ts`.

Responsibilities:

- compute visible grouped entries from canonical items
- own expansion state
- own collapsed tool-group state
- own near-bottom auto-scroll state
- derive `latestReasoningLabel`
- expose `requestAutoScroll()` and `updateAutoScroll()`

Do not:

- mutate canonical items
- create a second transcript model

CodexMonitor references:

- `src/features/messages/components/Messages.tsx`
- `src/features/messages/components/useMessagesViewState.ts`

### 2. Grouped Rendering

Update `ConversationFeed.tsx` to:

- consume `useConversationViewState.ts`
- render grouped entries rather than raw `items.map(...)`
- keep `ConversationItem[]` as the source of truth
- preserve pending user-input rendering and workflow bridge behavior

Expected grouped forms:

- standalone item rows
- tool groups for adjacent tool-heavy segments
- semantic working indicator area

### 3. Working Indicator Parity

Update `threadStoreV2.ts` and `WorkingIndicator.tsx`.

Required frontend local state:

- `processingStartedAt`
- `lastCompletedAt`
- `lastDurationMs`

Required behavior:

- timer starts on `thread.lifecycle(turn_started)`
- timer clears and duration freezes on terminal lifecycle
- reasoning label appears while the turn is active
- done state can show completion timing after the turn ends

### 4. Tool Streaming UX

Update `ToolRow.tsx`.

Required behavior:

- command tools show a scrollable live output viewport
- view-state controls expansion or collapse
- live output can request auto-scroll only when the viewport is pinned near bottom
- grouped tool sections can collapse or expand
- final file list remains authoritative through `outputFilesReplace`

CodexMonitor references:

- `src/features/messages/components/MessageRows.tsx`
- `src/features/messages/components/Messages.tsx`

### 5. Reasoning Semanticization

Update `ReasoningRow.tsx` and new view-state helpers.

Required behavior:

- parse reasoning text for display metadata where useful
- hide empty reasoning bodies from visible grouped entries
- derive `latestReasoningLabel` from the latest relevant reasoning item
- keep reasoning body rendering markdown-first

### 6. Terminal Interaction Projection

Update `backend/conversation/projector/thread_event_projector.py`.

Required behavior:

- handle `item/commandExecution/terminalInteraction`
- patch the tool item using `outputTextAppend`
- normalize appended terminal input with a visible marker such as `[stdin]`
- keep command output append semantics compatible with existing `outputTextAppend`

CodexMonitor references:

- `src/features/app/hooks/useAppServerEvents.ts`
- `src/features/threads/hooks/useThreadItemEvents.ts`

## Suggested Implementation Order

1. backend terminal-interaction projection
2. frontend view-state hook
3. non-destructive auto-scroll
4. reasoning-derived progress label
5. working indicator parity
6. tool grouping and command-output viewport
7. semantic verification and smoke

## File Targets

Frontend:

- `frontend/src/features/conversation/components/ConversationFeed.tsx`
- `frontend/src/features/conversation/components/ToolRow.tsx`
- `frontend/src/features/conversation/components/ReasoningRow.tsx`
- `frontend/src/features/conversation/components/WorkingIndicator.tsx`
- `frontend/src/features/conversation/components/ItemRow.tsx`
- `frontend/src/features/conversation/state/threadStoreV2.ts`
- optional helper file(s) under `frontend/src/features/conversation/`

Backend:

- `backend/conversation/projector/thread_event_projector.py`
- `backend/tests/unit/test_conversation_v2_projector.py`
- `backend/tests/integration/test_phase6_execution_audit_cutover.py`

## Verification Requirements

Frontend:

- grouped tool rendering is covered by unit tests
- reasoning-derived progress label is covered by unit tests
- auto-scroll does not snap to bottom when the user is reading older output
- command-output viewport behavior is covered by tests

Backend:

- `terminalInteraction` appends into canonical tool output
- terminal interaction appears in integration execution feed results

Phase-close smoke:

- long-running execution with multiple tool items
- reasoning visible during execution
- command output grows live without destroying the user’s reading position
- final command/file summaries converge after completion
