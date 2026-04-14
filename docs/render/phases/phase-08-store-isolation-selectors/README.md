# Phase 08 - Store Isolation and Selectors

Status: Completed.

Date: 2026-04-13.

Scope IDs: C05, C06, C08.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Implements Goose-first hybrid boundaries by keeping stream/replay correctness strict while narrowing frontend render invalidation.

Contract focus:

- Primary: `C5` Frontend State Contract v1
- Secondary: `C2` Replay and Resync Contract v1, `C3` Lifecycle and Gating Contract v1

Must-hold decisions:

- forced reload remains contract-classified with typed reason codes
- transient reconnect remains soft and does not inflate forced reload counts
- selector narrowing must not change user-visible behavior or lane semantics

## Objective

Reduce invalidation fanout and reload ambiguity without changing backend APIs, replay semantics, or user flow behavior.

## Implemented Scope

### 1. Store Isolation (C05)

Implemented in `frontend/src/features/conversation/state/threadByIdStoreV3.ts`.

- Kept one runtime Zustand store as source of truth.
- Added internal domain boundaries with helper patch composition:
  - `core` domain
  - `transport` domain
  - `ui-control` domain
- Refactored state writes in load/reload/stream/apply/action paths to domain-scoped patches.
- Kept external action API unchanged:
  - `loadThread`
  - `sendTurn`
  - `resolveUserInput`
  - `runPlanAction`
  - `recordRenderError`
  - `disconnectThread`

### 2. Selector Narrowing (C06)

Implemented in:

- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`

Added focused selector entrypoints:

1. `selectFeedRenderState`
2. `selectComposerState`
3. `selectTransportBannerState`
4. `selectWorkflowActionState`
5. `selectThreadActions`

Migration completed for chat lane surface:

- `BreadcrumbChatViewV2` now subscribes through focused selector entrypoints instead of broad store picks.

### 3. Reload Policy Completion (C08)

Forced reload policy uses centralized classification (`decideReloadPolicy`) and fixed reason taxonomy:

1. `REPLAY_MISS`
2. `CONTRACT_ENVELOPE_INVALID`
3. `CONTRACT_THREAD_ID_MISMATCH`
4. `CONTRACT_EVENT_CURSOR_INVALID`
5. `APPLY_EVENT_FAILED`
6. `USER_INPUT_RESOLVE_TIMEOUT`
7. `USER_INPUT_RESOLVE_REQUEST_FAILED`
8. `STREAM_HEALTHCHECK_FAILED`
9. `MANUAL_RETRY`

Implementation outcomes:

- no forced reload with null/empty reason
- forced reload reason code is stored separately from user-visible error message handling
- transient reconnect remains soft and does not increment forced reload telemetry

### 4. Docs, Gates, and Handoff (P8.4)

Added Phase 08 evidence and gate tooling:

- `scripts/phase08_render_fanout_profile.py`
- `scripts/phase08_stream_resilience_scenario.py`
- `scripts/phase08_reload_reason_audit.py`
- `scripts/phase08_gate_report.py`

Evidence folder:

- `docs/render/phases/phase-08-store-isolation-selectors/evidence/README.md`
- `docs/render/phases/phase-08-store-isolation-selectors/evidence/baseline-manifest-v1.json`

## Validation Snapshot

Code and test checks:

1. `npm run typecheck --prefix frontend` -> pass
2. `npm run test:unit --prefix frontend -- applyThreadEventV3.test.ts threadByIdStoreV3.test.ts` -> pass

Phase 08 evidence contract checks:

1. each source script without `--candidate` -> fail (expected)
2. each source script with `--allow-synthetic --self-test` -> pass, `gate_eligible=false` (expected local-only mode)
3. `phase08_gate_report.py` over synthetic sources -> fail (expected, ineligible evidence)
4. candidate-backed source artifacts + `phase08_gate_report.py --self-test` -> pass

## Exit Gates (P08)

Gate targets from `docs/render/system-freeze/phase-gates-v1.json`.

| Gate | Metric | Target | Current value | Status |
|---|---|---|---|---|
| P08-G1 | component_invalidation_reduction_pct | `>= 30` | `34.737` | pass |
| P08-G2 | forced_reload_rate_pct | `<= 3` | `2.308` | pass |
| P08-G3 | unclassified_reload_reason_events | `<= 0` | `0.0` | pass |

Gate artifacts:

1. `docs/render/phases/phase-08-store-isolation-selectors/evidence/render_fanout_profile.json`
2. `docs/render/phases/phase-08-store-isolation-selectors/evidence/stream_resilience_scenario.json`
3. `docs/render/phases/phase-08-store-isolation-selectors/evidence/reload_reason_audit.json`
4. `docs/render/phases/phase-08-store-isolation-selectors/evidence/phase08-gate-report.json`

## Residual Risks

1. Selector fanout is reduced at container level; row-level memo and parse cache gains are deferred to Phase 09.
2. `MANUAL_RETRY` reason is contract-mapped but not yet exercised by a dedicated user-triggered UI path.
3. Candidate evidence currently uses synthetic workload fixtures and should be replaced by CI-produced candidate profiles for production closure.
