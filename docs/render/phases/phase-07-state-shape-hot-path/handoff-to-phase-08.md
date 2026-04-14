# Phase 07 to Phase 08 Handoff

Status: Ready for execution handoff with pre-phase-8 hardening constraints.

Date: 2026-04-13.

Source phase: `phase-07-state-shape-hot-path` (C02, C03, C04).

Target phase: `phase-08-store-isolation-selectors` (C05, C06, C08).

## 1. Handoff Summary

Phase 07 implementation is complete and validated:

- V3 reducer item apply path now runs through normalized internal model (`itemsById + orderedItemIds`).
- global-sort work removed from patch-only hot path.
- structural sharing rules enforced for unchanged branches.
- compatibility adapter keeps `snapshot.items` stable for existing UI consumers.

Quantitative Phase 07 gates (`P07-G1/G2/G3`) passed in the original closeout run.
Pre-phase-8 hardening now requires candidate-backed evidence eligibility before any new gate closure.

## 2. Guarantees Intended for Phase 08

Phase 08 may assume:

1. C1/C2 replay and reconnect semantics are unchanged from Phase 06.
2. C5 ordering and identity behavior for Phase 07 reducer paths is deterministic.
3. `snapshot.items` adapter compatibility is still available while selector/store isolation is introduced.

## 3. Implemented Components

Frontend:

- `frontend/src/features/conversation/state/applyThreadEventV3.ts`.
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`.

Tests:

- `frontend/tests/unit/applyThreadEventV3.test.ts`.
- `frontend/tests/unit/threadByIdStoreV3.test.ts`.

Gate scripts:

- `scripts/phase07_state_hot_path_benchmark.py`.
- `scripts/phase07_state_hot_path_trace.py`.
- `scripts/phase07_reducer_identity_tests.py`.
- `scripts/phase07_gate_report.py`.

## 4. Validation Snapshot

Completed validations:

- Frontend typecheck -> pass.
- Frontend unit checks -> pass.
- `scripts/phase07_gate_report.py` -> pass (`P07-G1=32.857`, `P07-G2=3.0`, `P07-G3=0.0`).
- `scripts/validate_render_freeze.py` -> pass.
- Required P06 regression rerun -> pass.
- Pre-phase-8 hardening baseline prepared:
  - typed forced reload reason taxonomy in frontend store
  - candidate eligibility enforcement in P07 source scripts and gate report
  - selector guardrail entrypoints (`selectCore`, `selectTransport`, `selectUiControl`)

Evidence artifacts:

- `docs/render/phases/phase-07-state-shape-hot-path/evidence/state_hot_path_benchmark.json`.
- `docs/render/phases/phase-07-state-shape-hot-path/evidence/state_hot_path_trace.json`.
- `docs/render/phases/phase-07-state-shape-hot-path/evidence/reducer_identity_tests.json`.
- `docs/render/phases/phase-07-state-shape-hot-path/evidence/phase07-gate-report.json`.

## 5. Follow-up Actions (post-handoff)

1. Phase 08 store splitting and selector narrowing must consume existing C5 structural-sharing behavior, not bypass it.
2. Keep forced reload decisions contract-driven (`C2`/`C3`) and avoid broad fallback widening.
3. Regenerate Phase 07 gate evidence with candidate-backed artifacts (no synthetic evidence) before phase closure.
4. If Phase 08 changes V3 apply/store paths materially, rerun both P07 and P06 gate scripts before closure.

## 6. Risk Notes for Phase 08

1. Avoid broad selectors that reintroduce fanout despite improved item-level identity.
2. Preserve explicit reload reason classification to prevent hidden forced-reload regressions.
3. Keep adapter boundaries explicit during store split to avoid accidental public contract drift.

## 7. Decision Linkage

This handoff remains governed by:

- `docs/render/decision-pack-v1.md`.
- `docs/render/phases/phase-07-state-shape-hot-path/normalized-state-shape-v1.md`.
- `docs/render/phases/phase-07-state-shape-hot-path/close-phase-v1.md`.
- `docs/render/phases/phase-08-store-isolation-selectors/pre-phase-8-hardening-v1.md`.
- `docs/render/system-freeze/contracts/c2-replay-resync-contract-v1.md`.
- `docs/render/system-freeze/contracts/c3-lifecycle-gating-contract-v1.md`.
- `docs/render/system-freeze/contracts/c5-frontend-state-contract-v1.md`.
