# Execution/Audit UIUX V3 Implementation Plan (Phase 5-8)

Status: planning document.

Last updated: 2026-04-03.

## 1. Scope and locked decisions

This plan is based on:

- `docs/thread-rework/uiux/execution-audit-uiux-parity-blueprint.md`
- `docs/thread-rework/uiux/phase3-8-handoff.md`
- current implementation in backend/frontend V3 paths

Locked boundaries:

- Scope is execution and audit lanes only.
- Ask legacy lane stays unchanged.
- V2 contracts and endpoints stay backward-compatible during rollout.
- Plan-ready semantics must use structured V3 signals and dedicated V3 endpoint.
- Desktop affordance parity remains deferred until after Phase 8.

## 2. Current baseline from codebase

Already implemented (input to this plan):

- V3 projector semantics and V3 event stream/read path:
  - `backend/conversation/projector/thread_event_projector_v3.py`
  - `backend/routes/workflow_v3.py`
- V3 frontend store and render pipeline:
  - `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
  - `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
  - `frontend/src/features/conversation/components/v3/messagesV3.utils.ts`
  - `frontend/src/features/conversation/components/v3/messagesV3.viewState.ts`
- V3 UI wiring behind frontend flag:
  - `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`
  - `frontend/src/features/conversation/surfaceRouting.ts`
- Existing tests already cover most Phase 3-4 behavior:
  - backend: `test_conversation_v3_projector.py`, `test_conversation_v3_fixture_replay.py`, `test_chat_v3_api_execution_audit.py`
  - frontend: `MessagesV3.test.tsx`, `messagesV3.viewState.test.ts`, `threadByIdStoreV3.test.ts`, `BreadcrumbChatViewV2.v3-flag.integration.test.tsx`

Key remaining gap before cutover:

- no explicit golden parity harness versus CodexMonitor baseline model
- no cutover-grade lane-scoped rollout controls and observability package

## 3. Cross-phase strategy (Phase 5-8)

Execution order:

1. Phase 5 establishes parity evidence and CI gate.
2. Phase 6 enables V3 default for execution lane only, with rollback-ready controls.
3. Phase 7 enables V3 default for audit lane after execution stabilization window.
4. Phase 8 removes transitional debt and formalizes desktop-prep extension points.

Hard rule:

- do not move to the next phase until previous phase gate is green.

## 4. Phase 5 plan: parity verification hardening

## 4.1 Goals

- Freeze parity evidence in reproducible fixtures.
- Prove behavior parity for semantics, interaction, and micro-behavior.
- Produce a machine-checkable gate artifact for cutover decisions.

## 4.2 Implementation workstreams

### Workstream A: golden parity fixtures

- Add canonical trace fixtures for execution and audit:
  - include snapshot + incremental stream sequences
  - include plan-ready and user-input lifecycle variants
  - include command output growth and pinning scenarios
- Proposed fixture locations:
  - `backend/tests/fixtures/conversation_v3_parity/`
  - `frontend/tests/fixtures/conversation_v3_parity/`
- Add a shared fixture normalization policy:
  - deterministic IDs/timestamps in fixture payload
  - stable ordering for comparison snapshots

### Workstream B: derived parity model compare

- Add derived view-model helpers for parity assertions (not DOM-only snapshots):
  - visible items
  - grouped tool blocks
  - plan-ready card state
  - user-input pending/answered state
- Recommended location:
  - `frontend/src/features/conversation/components/v3/messagesV3.parityModel.ts`
- Add golden compare tests:
  - `frontend/tests/unit/messagesV3.parity.golden.test.ts`
  - `backend/tests/unit/test_conversation_v3_parity_fixtures.py`

### Workstream C: behavior integration coverage

- Expand integration tests for high-risk micro-behaviors:
  - near-bottom auto-scroll thresholds
  - pinned command output behavior while streaming
  - collapse/expand transitions across updates
  - plan follow-up visibility and suppression lifecycle
  - user-input request queue lifecycle
- Recommended additions:
  - `frontend/tests/unit/MessagesV3.behavior.integration.test.tsx`
  - `frontend/tests/unit/threadByIdStoreV3.stream.integration.test.ts`

### Workstream D: parity gate report artifact

- Add a generated report artifact for release decisions:
  - pass/fail matrix by parity gate category
  - divergence list with severity and owner
  - release recommendation: proceed / hold
- Suggested output path:
  - `docs/thread-rework/uiux/artifacts/phase5-parity-gate-report.md`

## 4.3 Exit criteria

- all parity fixture tests are green in CI
- no blocking divergence in plan/user-input behavior
- parity gate report artifact is published and reviewed

## 5. Phase 6 plan: execution lane cutover

## 5.1 Goals

- Make V3 default for execution lane only.
- Keep audit on pre-cutover path until Phase 7.
- Preserve one-step rollback.

## 5.2 Implementation workstreams

### Workstream A: lane-scoped rollout controls

- Introduce lane-scoped UIUX V3 controls (instead of one shared frontend flag):
  - execution lane enabled toggle
  - audit lane enabled toggle
- Update bootstrap surface and frontend routing to consume lane-scoped controls.
- Candidate files:
  - `backend/config/app_config.py`
  - `backend/services/project_service.py`
  - `frontend/src/api/types.ts`
  - `frontend/src/features/conversation/surfaceRouting.ts`
  - `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`

### Workstream B: execution default-on behavior

- Route execution lane to V3 by default when Phase 6 flag is on.
- Keep audit lane on pre-cutover path.
- Verify V2 fallback still works when execution V3 toggle is off.

### Workstream C: observability package for rollout

- Add minimal cutover metrics and log counters:
  - V3 stream reconnect count/rate
  - apply error and forced snapshot reload count
  - time-to-first-frame
  - frontend render error count
- Candidate instrumentation point:
  - `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- Add backend-side guardrails logs around V3 by-id endpoint failures in:
  - `backend/routes/workflow_v3.py`

### Workstream D: staged rollout procedure

- Stage 1: internal enablement (execution-only).
- Stage 2: canary projects or controlled environment.
- Stage 3: default-on execution.

## 5.3 Exit criteria

- execution lane runs V3 by default without blocking regression
- observability metrics are available and stable through monitoring window
- rollback to V2 execution path is confirmed in test and staging

## 6. Phase 7 plan: audit lane cutover

## 6.1 Goals

- Enable V3 default for audit lane after Phase 6 stabilization.
- Preserve audit read-only and review/diff semantic integrity.

## 6.2 Implementation workstreams

### Workstream A: audit default-on switch

- Turn on audit lane V3 routing via lane-scoped controls.
- Keep execution lane behavior unchanged from Phase 6 stable baseline.

### Workstream B: audit-specific regression safety

- Validate read-only constraints remain intact.
- Validate review/diff visibility and grouping in audit context.
- Validate no ask-lane routing regression.

### Workstream C: monitoring and rollback drill

- Run monitoring window focused on audit traffic.
- Execute rollback drill:
  - disable audit V3 first
  - preserve execution V3 as-is

## 6.3 Exit criteria

- audit lane V3 stable through monitoring window
- no audit read-only policy regressions
- rollback drill is successful

## 7. Phase 8 plan: stabilize and desktop-prep hooks

## 7.1 Goals

- Reduce transition debt.
- Prepare clean extension points for deferred desktop affordances.

## 7.2 Implementation workstreams

### Workstream A: cleanup and hardening

- remove or isolate transitional compatibility branches no longer needed post-cutover
- tighten test ownership and CI grouping for V3 parity and rollout suites
- resolve test warnings that can hide regressions (for example router future-flag warnings)

### Workstream B: extension points for desktop affordances

- document and expose explicit hooks in markdown/render layer for:
  - local file opener
  - file-link context menu
  - thread deep-link handling
  - image lightbox behavior
  - code-block copy UX
- candidate target:
  - `frontend/src/features/conversation/components/ConversationMarkdown.tsx`
  - shared markdown/render utilities in conversation components

### Workstream C: docs and ownership finalization

- publish post-cutover architecture notes for V3 execution/audit
- define maintenance ownership for:
  - projector semantics
  - parity fixture updates
  - render micro-behavior guard tests

## 7.3 Exit criteria

- transitional debt items accepted or closed
- desktop-prep extension points documented and tested at API level
- V3 path is maintainable without ad-hoc parity fixes

## 8. Test and CI plan for Phase 5-8

## 8.1 Mandatory suites per phase

- Backend:
  - `backend/tests/unit/test_conversation_v3_projector.py`
  - `backend/tests/unit/test_conversation_v3_fixture_replay.py`
  - `backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - new parity fixture tests (Phase 5)
- Frontend:
  - `frontend/tests/unit/messagesV3.utils.test.ts`
  - `frontend/tests/unit/messagesV3.viewState.test.ts`
  - `frontend/tests/unit/MessagesV3.test.tsx`
  - `frontend/tests/unit/threadByIdStoreV3.test.ts`
  - `frontend/tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx`
  - new parity/integration tests (Phase 5+)

## 8.2 Recommended commands

Backend:

```bash
python -m pytest backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/integration/test_chat_v3_api_execution_audit.py
```

Frontend (stable mode for this repo):

```bash
node frontend/node_modules/vitest/vitest.mjs run tests/unit/messagesV3.viewState.test.ts tests/unit/MessagesV3.test.tsx tests/unit/messagesV3.utils.test.ts tests/unit/threadByIdStoreV3.test.ts tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx --config vitest.config.ts --root frontend --pool=threads --poolOptions.threads.singleThread=true
```

Cutover phases must also run full legacy safety suites with flags OFF.

## 9. Risks and mitigations (Phase 5-8)

1. Risk: shared frontend flag cannot safely stage execution then audit.
   - Mitigation: add lane-scoped rollout controls before Phase 6 default-on.
2. Risk: parity drift over time.
   - Mitigation: fixture-based parity suite as release gate.
3. Risk: stream/apply edge cases during rollout.
   - Mitigation: reconnect and reload metrics + staged rollout + rollback drill.
4. Risk: desktop affordance prep accidentally changes current UX.
   - Mitigation: hooks-only in Phase 8, no behavior flip.

## 10. PR slicing and dependency order

1. PR-5A: fixture harness + parity model compare.
2. PR-5B: behavior parity integration suite + gate report artifact.
3. PR-6A: lane-scoped flags/bootstrap fields + execution default-on routing.
4. PR-6B: execution observability counters + rollback playbook docs.
5. PR-7A: audit default-on routing + audit regression suite.
6. PR-7B: audit rollout monitoring and rollback drill evidence.
7. PR-8A: cleanup + extension hooks for desktop affordances.
8. PR-8B: final docs and ownership handoff.

## 11. Definition of done for the full 5-8 cycle

- Phase 5 parity gate is green and reproducible in CI.
- Execution and audit lanes are on V3 by default with rollback controls.
- Monitoring confirms no blocking stream/render regressions.
- Transitional debt is reduced and desktop-prep hooks are documented.
