# Execution/Audit UIUX V3 Handoff (Phase 5-8 Starter)

Status: handoff after completing Phase 3-4.

Last updated: 2026-04-03.

## 1. Purpose

This handoff captures the real codebase state after:

- Phase 3: behavior parity
- Phase 4: persistence parity

Next scope:

- Phase 5: parity verification hardening
- Phase 6: execution cutover
- Phase 7: audit cutover
- Phase 8: stabilize + desktop-prep hooks

## 2. Completed work (actual implementation)

### 2.1 Contract and boundaries

- Scope remains as agreed:
  - execution and audit lanes only
  - ask legacy lane unchanged
  - no V2 contract break
- UI source of truth is still:
  - `uiSignals.planReady`
  - `uiSignals.activeUserInputRequests`
- Plan-ready CTA uses dedicated V3 endpoint, not hidden tags.

### 2.2 Backend (Phase 3)

- Projector semantics now map first-class `review/diff/explore`:
  - message with `metadata.workflowReviewSummary` -> `review`
  - system message with `metadata.workflowReviewGuidance` -> `explore`
  - tool `fileChange` -> `diff` (files + summary)
  - `plan` -> `review` with metadata trace (`v2Kind`, `semanticKind`)
- Patch mapping handles converted kinds to avoid mismatch (`review/explore/diff`).
- Added by-id action endpoints:
  - `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/requests/{request_id}/resolve?node_id=...`
  - `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions?node_id=...`
- Added guards:
  - execution/audit lane only
  - active thread for node
  - stale-check by `planItemId + revision + ready/failed`

### 2.3 Frontend (Phase 3-4)

- V3 store:
  - `resolveUserInput` is fully wired with optimistic `answer_submitted`
  - timeout fallback reload when stream confirmation is missing
  - `runPlanAction` uses dedicated V3 endpoint
- `MessagesV3` behavior parity implemented:
  - reasoning/tool collapse-expand
  - tool-group collapse-expand
  - near-bottom auto-scroll
  - command output pinning
  - plan-ready follow-up card with suppression + dismiss key `(threadId, planItemId, revision)`
  - pending requests as dedicated cards, answered requests as compact inline rows
- Persistence parity implemented:
  - key: `ptm.uiux.v3.thread.<threadId>.viewState`
  - versioned payload, stale prune, size cap
  - per-thread hydrate/persist without cross-thread leakage
- Important bug fixed:
  - render loop in pending user-input when request had no linked item.

## 3. API and contract impact (Phase 3-4)

### 3.1 Added (non-breaking)

- Backend routes:
  - resolve request by-id
  - plan-actions by-id
- Frontend API methods:
  - `resolveThreadUserInputByIdV3(...)`
  - `planActionByIdV3(...)`
- V3 event names remain unchanged.

### 3.2 Unchanged

- V2 endpoints and contracts unchanged.
- Ask lanes unchanged.

## 4. Test evidence

### 4.1 Backend

Command:

```bash
python -m pytest backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/integration/test_chat_v3_api_execution_audit.py
```

Result: `12 passed`.

Validated areas:

- semantic mapping for `review/diff/explore`
- patch mapping after conversion
- by-id resolve flow
- by-id plan action stale validation and dispatch

### 4.2 Frontend

Command:

```bash
node frontend/node_modules/vitest/vitest.mjs run tests/unit/messagesV3.viewState.test.ts tests/unit/MessagesV3.test.tsx tests/unit/messagesV3.utils.test.ts tests/unit/threadByIdStoreV3.test.ts tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx --config vitest.config.ts --root frontend --pool=threads --poolOptions.threads.singleThread=true
```

Result: `5 files passed, 16 tests passed`.

Validated areas:

- V3 reducer/store snapshot/patch/fallback behavior
- optimistic resolve user-input + timeout reload fallback
- plan-ready visibility/suppression/dismiss behavior
- pending vs answered user-input rendering
- persistence hydrate/prune/size-cap behavior
- V3 integration behind flags in `BreadcrumbChatViewV2`

## 5. Flags and rollback

Runtime flags:

- `PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_BACKEND`
- `PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND`

Expected behavior:

- both ON: execution/audit run V3 end-to-end
- frontend OFF: UI falls back to V2
- backend OFF: V3 by-id read/action path disabled
- ask lanes: unchanged

Rollback order:

1. Disable frontend flag first (safe UI fallback to V2).
2. Disable backend flag if deeper rollback is needed.

## 6. Known gaps for Phase 5+

- No golden parity fixture harness yet against CodexMonitor baseline.
- No rollout telemetry/dashboard package yet for cutover gates.
- Desktop affordance parity is still deferred:
  - open local file
  - file-link context menu
  - thread link
  - image lightbox
  - copy code block (markdown/render layer)
- React Router future-flag warnings exist in integration tests (not blocking, should be cleaned in stabilize).

## 7. Immediate starter tasks for Phase 5

1. Build parity fixture pack for representative execution/audit traces:
   - stream sequence capture
   - expected visible-state checkpoints
2. Add behavior-level compare suite between PT V3 and baseline model:
   - plan follow-up lifecycle
   - user-input lifecycle
   - command pinning + auto-scroll
3. Define gate report artifact for Phase 6:
   - pass/fail matrix
   - divergence severity list
   - rollback recommendation when divergence is blocking

## 8. Gates for Phase 6-8

### 8.1 Gate into Phase 6 (execution cutover)

- Phase 5 parity suite passes with no blocking divergence for plan/user-input.
- ON/OFF flag safety is proven.
- Minimum metrics are available:
  - reconnect rate
  - apply error + forced snapshot reload rate
  - render error rate
  - time-to-first-frame

### 8.2 Gate into Phase 7 (audit cutover)

- Execution cutover is stable through monitoring window.
- `review/diff` semantics in audit lane remain read-only safe.

### 8.3 Gate into Phase 8 (stabilize)

- Execution and audit are stable with V3 default-on.
- Remaining backlog is mainly cleanup and extension hooks.

## 9. Suggested PR slicing for Phase 5-8

1. PR-5A: parity fixture + compare harness.
2. PR-5B: parity integration specs (autoscroll/pinning/plan/user-input lifecycle).
3. PR-6A: execution cutover wiring + observability.
4. PR-7A: audit cutover wiring + audit-specific regression tests.
5. PR-8A: stabilize cleanup + desktop-affordance extension hooks/docs.

## 10. Required handoff checklist for each next phase

1. Scope note:
   - in scope
   - deferred
2. Contract/API impact:
   - V2 unchanged proof
   - V3 additions
3. Test evidence:
   - exact command list
   - pass/fail summary
4. Flag proof:
   - ON behavior
   - OFF behavior
5. Risk + rollback:
   - top regressions to monitor
   - rollback order
6. Next-phase starter:
   - first 3 tasks
   - blockers/dependencies
