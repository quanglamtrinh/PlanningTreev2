# Execution/Audit UIUX Parity Blueprint (CodexMonitor-Style)

Status: draft implementation blueprint.

Last updated: 2026-04-03.

This document defines the target UI/UX rework for `execution` and `audit` threads only, with CodexMonitor-level parity for semantics, interaction, and micro-behavior.

## Decision Freeze (Locked)

The following decisions are locked and are treated as constraints:

1. Parity target is full parity at:
   - semantics
   - interaction
   - micro-behavior
2. Schema and event projector changes are allowed.
3. Scope excludes `ask_legacy` and `ask_planning`.
4. Scope includes only execution/audit thread surfaces.
5. Desktop affordance parity is deferred to a later phase.
6. Visual grammar is ported as-is from CodexMonitor.
7. Plan/user-input behavior must be parity-level equivalent to CodexMonitor.
8. Contract strategy is `V3 parallel` (do not break V2 during rollout).
9. Plan-ready and user-input runtime state must come from structured contract/projector state, not hidden message tags.
10. Semantics needed for parity should be first-class kinds (not hidden in generic tool metadata).
11. UI view state must persist across reload.
12. A dedicated parity-focused test suite is mandatory before cutover.

## Scope

In scope:

- execution thread transcript UI
- audit/review thread transcript UI
- conversation item semantics used by these two surfaces
- event projector and snapshot contract needed for parity behavior
- plan follow-up and user-input workflow UI behavior
- reload persistence for view state

Out of scope (explicitly deferred):

- ask legacy and ask planning UI
- desktop-native file/app affordances:
  - local open in editor
  - file-link context menu
  - desktop reveal/open target behaviors

## Goals

1. Make PT execution/audit transcript feel and behave the same as CodexMonitor.
2. Keep workflow correctness backend-owned while transcript feel is frontend-owned.
3. Avoid high-risk migration by running V3 in parallel with V2 until parity gates pass.
4. Keep future desktop affordance parity easy to add without contract churn.

## Non-Goals

1. Redesigning workflow policy.
2. Changing ask lanes.
3. Introducing new product behaviors outside parity goals.

## Parity Definition

### Semantics parity

Execution/audit transcript supports equivalent view semantics:

- message
- reasoning
- tool
- explore
- userInput (answered inline state)
- review
- diff

PT may keep `status` and `error` as additional kinds for compatibility, but parity rendering must not regress CodexMonitor behavior.

### Interaction parity

Equivalent user interaction rules:

- tool-group collapse/expand behavior
- reasoning collapse/expand behavior
- tool row collapse/expand behavior
- auto-scroll behavior
- command output pinning behavior
- quote/copy message behavior
- plan follow-up CTA flow
- user-input request handling flow

### Micro-behavior parity

Equivalent subtle behavior:

- `near-bottom` thresholds
- clamped vs expanded reasoning/tool command display
- delayed command live-output reveal behavior
- working label derived from latest reasoning
- plan-follow-up suppression rules
- follow-up dismissal scoping and reset rules

## Current vs Target (Execution/Audit)

Current PT V2 is item-card oriented and contract-clean, but not parity-level equivalent in:

- semantic breadth
- tool/reasoning stream grammar
- plan/user-input decision UX
- markdown and in-message interaction affordances

Target model is CodexMonitor-style transcript rendering, with PT-specific workflow gating retained.

## Architecture Strategy

Use a parallel contract and consumer path:

1. Keep V2 unchanged for safety.
2. Introduce `Conversation V3` schema + projector output.
3. Add new execution/audit UI consumer that renders V3 with CodexMonitor visual grammar and behavior.
4. Cut over execution/audit after parity gate pass.

Rationale:

- minimizes blast radius
- supports side-by-side verification
- allows full parity tests before flipping default

## V3 Data Contract Blueprint

### Snapshot (high-level)

```ts
type ThreadSnapshotV3 = {
  threadId: string
  lane: 'execution' | 'audit'
  processingState: 'idle' | 'running' | 'waiting_user_input' | 'failed'
  activeTurnId: string | null
  snapshotVersion: number
  items: ConversationItemV3[]
  uiSignals: UiSignalsV3
  updatedAt: string
}
```

### Item union (high-level)

```ts
type ConversationItemV3 =
  | MessageItemV3
  | ReasoningItemV3
  | ToolItemV3
  | ExploreItemV3
  | UserInputAnsweredItemV3
  | ReviewItemV3
  | DiffItemV3
  | StatusItemV3
  | ErrorItemV3
```

### Structured UI signals (required)

```ts
type UiSignalsV3 = {
  activeUserInputRequests: PendingUserInputRequestV3[]
  planReady: {
    planItemId: string | null
    revision: number | null
    ready: boolean
    failed: boolean
  }
}
```

Notes:

- `planReady` is projector-owned structured state; no hidden tag parsing.
- pending input requests are structured state; no inference-only heuristics.

## Event Projector V3 Requirements

Projector responsibilities:

1. Emit append/patch events for the expanded item semantics.
2. Emit/refresh `uiSignals.planReady` based on structured plan lifecycle and output readiness.
3. Emit/refresh `uiSignals.activeUserInputRequests` from request lifecycle.
4. Preserve deterministic replay behavior (`snapshot + incremental`).
5. Keep enough metadata for parity-level rendering without ad-hoc frontend scraping.

Event families (illustrative):

- `thread.snapshot.v3`
- `conversation.item.upsert.v3`
- `conversation.item.patch.v3`
- `conversation.ui.plan_ready.v3`
- `conversation.ui.user_input.v3`
- `thread.lifecycle.v3`
- `thread.error.v3`

## Rendering Model (Target)

Execution/audit surfaces adopt CodexMonitor-style render topology:

1. `Messages` root container
2. `deriveVisibleMessageState`
3. `buildToolGroups`
4. row-level renderers:
   - message
   - reasoning
   - review
   - diff
   - userInput (answered)
   - tool
   - explore
5. out-of-band cards:
   - pending user input request card
   - plan ready follow-up card
6. working indicator driven by processing + latest reasoning label

Visual grammar rule:

- port class-level structure and spacing pattern from CodexMonitor with minimal PT adaptation.
- do not redesign cards/rows in this phase.

## Plan and User-Input Behavior (Parity Rules)

### Plan-ready behavior

Must match CodexMonitor behavior while using structured signals:

1. Show follow-up card only when:
   - plan is structurally ready
   - no active visible pending user-input request blocks it
   - no later user message already superseded that plan revision
2. Hide follow-up card if plan is failed or stale.
3. Dismissal is keyed by `(threadId, planItemId, revision)` and persists across reload.
4. `Implement this plan` and `Send changes` actions route through structured request handling (no hidden text protocol).

### User-input behavior

1. Pending requests render as dedicated request card (not inline transcript answer row).
2. Answered requests are represented as compact inline transcript items.
3. Queue state supports multiple pending requests with deterministic active ordering.
4. Request submission status transitions are reflected in both `uiSignals` and transcript semantics.

## Reload-Persistent View State

Persist across reload per thread:

- expanded item IDs
- collapsed tool-group IDs
- dismissed plan-ready state

Storage key blueprint:

```txt
ptm.uiux.v3.thread.<threadId>.viewState
```

State hygiene:

1. prune IDs not present in current hydrated items
2. bound persisted payload size
3. include schema version for forward migration

## Deferred Desktop Parity (Phase-Later Contract)

The V3 render architecture must keep extension points for later desktop parity:

- file link opener
- file link context menu
- open-thread deep link handler
- native reveal/open target adapters

Phase-1 fallback behavior:

- keep links readable and safe
- do not silently imply desktop actions that are not implemented

## Rollout Plan Skeleton

### Phase 0: Contract freeze

- finalize V3 schema
- finalize projector event set
- freeze parity acceptance checklist

### Phase 1: Backend V3 foundation

- implement V3 projector output
- add snapshot/read and stream endpoints for V3
- fixture generation for parity tests

### Phase 2: Frontend V3 core

- add V3 store and reducer
- add `Messages`/row/util pipeline modeled after CodexMonitor
- wire execution/audit consumer behind flag

### Phase 3: Behavior parity

- implement reasoning/tool/group/working indicator parity
- implement plan-ready structured flow
- implement pending/answered user-input parity

### Phase 4: Persistence parity

- implement and validate reload-persistent view state
- enforce cleanup/versioning rules

### Phase 5: Parity verification

- run behavior parity suite
- resolve diffs against CodexMonitor baseline fixtures

### Phase 6: Execution cutover

- enable V3 UI for execution lane
- monitor metrics/errors

### Phase 7: Audit cutover

- enable V3 UI for audit lane
- monitor metrics/errors

### Phase 8: Stabilize and prep desktop parity

- cleanup transitional adapters
- document extension points for desktop parity phase

## Test Strategy (Mandatory)

### Unit tests

- message render utils parity
- group building rules
- plan/user-input visibility rules
- view-state persistence serializer/rehydrator

### Reducer/integration tests

- replay snapshot + patch streams
- out-of-order and duplicate-safe behavior
- plan/user-input signal transitions

### UI behavior tests

- auto-scroll thresholds and pinned command viewport
- expand/collapse persistence across reload
- plan follow-up CTA lifecycle
- user-input request queue lifecycle

### Golden parity fixtures

- normalize a canonical event trace
- assert PT V3 derived view model equals CodexMonitor expected model for scoped semantics

## Acceptance Gates

Execution/audit cutover is blocked until all are true:

1. All parity test suites pass.
2. No blocking divergence in plan/user-input behavior.
3. Reload persistence behaves deterministically.
4. V2 fallback remains available during staged rollout.
5. Observability dashboards show no regression in stream/render stability.

## Risks and Mitigations

1. Risk: parity drift from CodexMonitor utility logic over time.
   - Mitigation: maintain golden fixtures and explicit parity contract tests.

2. Risk: expanded semantics increase payload size and render cost.
   - Mitigation: cap text fields and apply bounded virtualization strategy if needed.

3. Risk: persistent view state becomes stale/noisy.
   - Mitigation: versioned storage + pruning + TTL.

4. Risk: behavior mismatch between projector state and UI heuristics.
   - Mitigation: structured `uiSignals` are source of truth; keep heuristics secondary.

## Implementation References

CodexMonitor reference areas:

- `src/features/messages/components/Messages.tsx`
- `src/features/messages/components/MessageRows.tsx`
- `src/features/messages/components/Markdown.tsx`
- `src/features/messages/utils/messageRenderUtils.ts`
- `src/features/app/components/PlanReadyFollowupMessage.tsx`
- `src/features/app/components/RequestUserInputMessage.tsx`

PT current areas to replace/extend for execution/audit:

- `frontend/src/features/conversation/components/ConversationFeed.tsx`
- `frontend/src/features/conversation/components/useConversationViewState.ts`
- `frontend/src/features/conversation/components/*Row.tsx`
- `frontend/src/features/conversation/state/*V2.ts`
- backend conversation projector and stream routes for V3 path

## Definition of Done

This blueprint is considered implemented when:

1. Execution/audit run on V3 UI by default.
2. Behavior parity suite is green and tracked in CI.
3. Plan/user-input behavior matches CodexMonitor-equivalent semantics and interaction.
4. Reload persists view-state invariants.
5. V2 path is retired for execution/audit only after stability window.

## Contract Appendix (Phase 0 Freeze)

This appendix is frozen for Phase 0-2 implementation.
No open TODO items are allowed in this section.

### A. V3 snapshot contract (frozen)

```ts
type ThreadSnapshotV3 = {
  projectId: string
  nodeId: string
  threadId: string | null
  lane: 'execution' | 'audit'
  processingState: 'idle' | 'running' | 'waiting_user_input' | 'failed'
  activeTurnId: string | null
  snapshotVersion: number
  createdAt: string
  updatedAt: string
  items: ConversationItemV3[]
  uiSignals: UiSignalsV3
}
```

### B. V3 item union (frozen)

```ts
type ConversationItemV3 =
  | MessageItemV3
  | ReasoningItemV3
  | ToolItemV3
  | ExploreItemV3
  | UserInputItemV3
  | ReviewItemV3
  | DiffItemV3
  | StatusItemV3
  | ErrorItemV3
```

Required covered kinds for this program:

- `message`
- `reasoning`
- `tool`
- `explore`
- `userInput`
- `review`
- `diff`
- `status`
- `error`

### C. Structured UI signals (frozen)

```ts
type UiSignalsV3 = {
  planReady: {
    planItemId: string | null
    revision: number | null
    ready: boolean
    failed: boolean
  }
  activeUserInputRequests: PendingUserInputRequestV3[]
}
```

Hard rule:

- plan-ready must come from structured projector signal state (never hidden text tags).

### D. Event naming convention (frozen)

Thread channel V3 event names are fixed:

- `thread.snapshot.v3`
- `conversation.item.upsert.v3`
- `conversation.item.patch.v3`
- `conversation.ui.plan_ready.v3`
- `conversation.ui.user_input.v3`
- `thread.lifecycle.v3`
- `thread.error.v3`

### E. Scope boundary freeze

- Scope is execution/audit only.
- Ask lanes remain on existing contract.
- V2 behavior and endpoints remain unchanged.
- V3 is additive, parallel, and flag-gated.
- Hidden tag inference is prohibited for plan-ready.

### F. Phase-3+ parity gate checklist (frozen for later use)

This gate checklist is prepared in Phase 0 and consumed in Phase 3+:

1. Semantics gate:
   - visible transcript model parity for message/reasoning/tool/explore/userInput/review/diff
   - no fallback heuristics that contradict structured `uiSignals`
2. Interaction gate:
   - tool grouping + collapse/expand parity
   - reasoning collapse/expand parity
   - near-bottom auto-scroll and pinned command output parity
3. Plan/user-input gate:
   - plan-ready follow-up visibility and suppression parity
   - pending request card + answered inline semantics parity
4. Micro-behavior gate:
   - clamped/expanded display transitions parity
   - dismissal scope + reload persistence parity
5. Safety gate:
   - flags OFF keeps V2 behavior unchanged for execution/audit
   - ask lanes unaffected
