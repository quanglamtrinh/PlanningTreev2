# Execution/Audit UIUX V3 Handoff (Phase 3-8)

Status: handoff after completing Phase 0-2 foundation.

Last updated: 2026-04-03.

## 1. Purpose

This document is the execution handoff for the next phases after:

- Phase 0: contract freeze
- Phase 1: backend V3 foundation
- Phase 2: frontend V3 core wiring

Goal: move from foundation to parity and cutover with clear scope, tests, and rollback.

## 2. Current baseline

### 2.1 Parallel flags and routing

- Backend flag: `PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_BACKEND`
- Frontend flag: `PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND`
- Bootstrap fields available:
  - `execution_audit_uiux_v3_backend_enabled`
  - `execution_audit_uiux_v3_frontend_enabled`
- With flags OFF: execution/audit still use V2 path.
- Ask lanes are unchanged.

### 2.2 Backend V3 available now

- By-id endpoints:
  - `GET /v3/projects/{project_id}/threads/by-id/{thread_id}?node_id=...`
  - `GET /v3/projects/{project_id}/threads/by-id/{thread_id}/events?node_id=...`
- Stream model:
  - first snapshot frame
  - incremental replay with `after_snapshot_version`
  - version guard returns 409 on mismatch
- Frozen V3 event names:
  - `thread.snapshot.v3`
  - `conversation.item.upsert.v3`
  - `conversation.item.patch.v3`
  - `conversation.ui.plan_ready.v3`
  - `conversation.ui.user_input.v3`
  - `thread.lifecycle.v3`
  - `thread.error.v3`

### 2.3 Frontend V3 available now

- V3 by-id store/reducer:
  - snapshot + patch apply
  - stale target guard
  - snapshot reload fallback on apply errors
- Core render pipeline in place:
  - `MessagesV3`
  - `deriveVisibleMessageStateV3`
  - `buildToolGroupsV3`
  - row shells for `message/reasoning/tool/explore/userInput/review/diff/status/error`
- `BreadcrumbChatViewV2` is wired to switch between V2 and V3 via flag.

### 2.4 Foundation tests already added

- Backend:
  - `test_conversation_v3_projector.py`
  - `test_conversation_v3_fixture_replay.py`
  - `test_chat_v3_api_execution_audit.py`
- Frontend:
  - `messagesV3.utils.test.ts`
  - `threadByIdStoreV3.test.ts`
  - `BreadcrumbChatViewV2.v3-flag.integration.test.tsx`

## 3. Intentionally deferred work

- Full micro-behavior parity for plan/user-input is not done yet.
- Full CodexMonitor interaction parity for reasoning/tool/output pinning is not done yet.
- Reload persistence for expanded/collapsed/dismissed V3 UI state is not done yet.
- Desktop affordance parity is deferred.

## 4. Phase 3: Behavior parity

### 4.1 Goal

Move V3 from core wiring to parity-level behavior for semantics, interactions, and micro-behavior on execution/audit.

### 4.2 Workstream A: semantics parity

- Normalize projector outputs for first-class:
  - `explore`
  - `review`
  - `diff`
- Reduce temporary fallback mapping (`plan -> review` via metadata) where possible.
- Keep `uiSignals.planReady` and `activeUserInputRequests` as source of truth.

### 4.3 Workstream B: interaction parity

- Reasoning collapse/expand parity.
- Tool row collapse/expand parity.
- Tool-group behavior parity.
- Near-bottom auto-scroll parity.
- Command output pinning parity.

### 4.4 Workstream C: plan/user-input parity

- Plan follow-up card:
  - correct show/hide conditions by revision/stale/failed
  - suppression rules per blueprint
- Pending request card and answered-inline semantics parity.
- Implement `resolveUserInput` in V3 store (currently intentionally unsupported).

### 4.5 Exit criteria

- Phase 3 parity behavior suite passes.
- No V2 regressions.
- Flags OFF preserve current behavior.

## 5. Phase 4: Persistence parity

### 5.1 Goal

Persist and restore per-thread V3 view state deterministically.

### 5.2 Persisted state

- Expanded item IDs
- Collapsed tool-group IDs
- Dismissed plan-ready state

Recommended storage key:

`ptm.uiux.v3.thread.<threadId>.viewState`

### 5.3 Rules

- Prune IDs not present in current hydrated snapshot.
- Include persisted schema version.
- Enforce payload size cap.

### 5.4 Exit criteria

- Deterministic reload behavior per thread.
- No state leak between different execution/audit thread IDs.

## 6. Phase 5: Parity verification

### 6.1 Goal

Lock parity with fixture and integration evidence before cutover.

### 6.2 Required test artifacts

- Golden fixtures for representative execution/audit traces.
- Derived view-model compare:
  - PT V3 output
  - expected CodexMonitor baseline model
- Behavior integration tests for:
  - near-bottom autoscroll
  - command pinning
  - plan follow-up lifecycle
  - user-input queue lifecycle

### 6.3 Gate

Phase 6 is blocked until:

- parity suites pass
- no blocking plan/user-input behavior divergence

## 7. Phase 6: Execution cutover

### 7.1 Goal

Enable V3 as default for execution lane.

### 7.2 Rollout stages

- Stage 1: internal flag-on (backend + frontend)
- Stage 2: canary cohort
- Stage 3: default-on execution

### 7.3 Minimum observability

- Stream reconnect rate
- Apply error / reload fallback rate
- Time-to-first-frame
- UI render error rate

### 7.4 Rollback

- Disable `execution_audit_uiux_v3_frontend` to return UI to V2.
- If needed, also disable `execution_audit_uiux_v3_backend`.

## 8. Phase 7: Audit cutover

### 8.1 Goal

Enable V3 as default for audit lane after execution stabilizes.

### 8.2 Audit-specific checks

- `review/diff` semantics must be stable before enabling.
- Audit read-only policy must remain unchanged.

### 8.3 Gate

- Execution cutover is stable through monitoring window.
- Audit parity suite passes.

## 9. Phase 8: Stabilize and desktop prep

### 9.1 Goal

Remove transitional adapters and prepare extension points for deferred desktop affordances.

### 9.2 Deferred desktop prep hooks

- Local file opener hooks
- File link context menu hooks
- Thread deep-link hooks
- Image lightbox hooks
- Copy code block UX hooks

Keep these as render/markdown extension points to avoid V3 contract churn.

## 10. Suggested PR slicing

1. PR-A: Phase 3 semantics/projector
2. PR-B: Phase 3 interaction + plan/user-input behavior
3. PR-C: Phase 4 persistence
4. PR-D: Phase 5 parity fixtures + verification
5. PR-E: Phase 6 execution cutover
6. PR-F: Phase 7 audit cutover
7. PR-G: Phase 8 stabilize + desktop-prep hooks/docs

## 11. Quick start for next team

1. Read:
   - `docs/thread-rework/uiux/execution-audit-uiux-parity-blueprint.md`
   - `docs/thread-rework/uiux/phase3-8-handoff.md`
2. Run V3 foundation tests before phase work.
3. For every Phase 3+ PR, prove:
   - flags OFF keep behavior unchanged
   - V2 tests remain green
   - V3 tests are expanded only for that phase scope

## 12. Handoff package checklist (required per phase)

Each phase handoff should include all artifacts below before moving to the next phase:

1. Scope note:
   - what was in scope
   - what was explicitly deferred
2. Contract impact note:
   - confirm no V2 break
   - list any V3 contract additions
3. Test evidence:
   - exact commands run
   - pass/fail summary
   - new tests added in phase
4. Flag behavior proof:
   - behavior when flags ON
   - behavior when flags OFF
5. Risk + rollback note:
   - top regressions to watch
   - explicit rollback toggle sequence
6. Next-phase starter list:
   - first 3 implementation tasks
   - known blockers/dependencies

## 13. Immediate next actions (start of Phase 3)

1. Expand projector semantics for `explore/review/diff` and reduce metadata fallback mapping.
2. Implement V3 `resolveUserInput` flow end-to-end in store + API integration.
3. Add parity behavior tests for:
   - reasoning/tool collapse-expand
   - plan follow-up visibility/suppression
   - pending vs answered user-input rendering
4. Validate flag safety:
   - ON: execution/audit uses V3 behavior path
   - OFF: execution/audit remains V2
5. Prepare Phase 3 handoff package using section 12 checklist.
