# Phase 08 to Phase 09 Handoff

Status: Ready for implementation handoff.

Date: 2026-04-13.

Source phase: `phase-08-store-isolation-selectors` (C05, C06, C08).

Target phase: `phase-09-row-isolation-cache` (D01, D02, D10).

Scope authority note:

- This handoff captures Phase 08 outputs and assumptions only.
- Phase 09 implementation scope IDs are defined by `docs/render/system-freeze/phase-manifest-v1.json`.

## 1. Handoff Summary

Phase 08 completed and validated:

- store internals are isolated into domain-scoped write helpers (`core`, `transport`, `ui-control`)
- chat lane moved to focused selector entrypoints
- forced reload classification is centralized and reason-coded
- candidate-backed Phase 08 gate evidence passes all P08 gates

## 2. Guarantees for Phase 09

Phase 09 may assume:

1. no forced reload path can emit null/empty reason codes.
2. transient reconnect path stays soft and does not increment forced reload telemetry.
3. chat container subscription surface is already narrowed and stable for row-level memo follow-up.
4. store external action APIs are unchanged from pre-Phase-08 behavior.

## 3. Implemented Components

Frontend:

- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`

Tests:

- `frontend/tests/unit/threadByIdStoreV3.test.ts`

Gate scripts:

- `scripts/phase08_render_fanout_profile.py`
- `scripts/phase08_stream_resilience_scenario.py`
- `scripts/phase08_reload_reason_audit.py`
- `scripts/phase08_gate_report.py`

## 4. Validation Snapshot

Completed validations:

- frontend typecheck -> pass
- targeted frontend unit tests -> pass
- source evidence contract checks (missing candidate, synthetic local-only, candidate-backed) -> pass
- P08 gate report with candidate-backed evidence -> pass

Evidence artifacts:

- `docs/render/phases/phase-08-store-isolation-selectors/evidence/render_fanout_profile.json`
- `docs/render/phases/phase-08-store-isolation-selectors/evidence/stream_resilience_scenario.json`
- `docs/render/phases/phase-08-store-isolation-selectors/evidence/reload_reason_audit.json`
- `docs/render/phases/phase-08-store-isolation-selectors/evidence/phase08-gate-report.json`

## 5. Follow-up Actions for Phase 09

1. use focused selector contracts as fixed inputs for row-level memoization.
2. keep row selector output shapes stable while adding cache/memo layers.
3. do not widen subscriptions back to root-level selectors in chat surfaces.
4. preserve forced reload reason contract while optimizing render/cache paths.

## 6. Residual Risks and Notes

1. `MANUAL_RETRY` is classified but still not exercised by a dedicated UI trigger.
2. candidate evidence in this closeout uses fixture-style candidate files; CI-generated candidate profiles should replace fixtures for production closure.
3. performance gains are container-level in Phase 08; row-level churn reduction is intentionally deferred to Phase 09.

## 7. Decision and Contract Linkage

This handoff remains governed by:

- `docs/render/decision-pack-v1.md`
- `docs/render/system-freeze/contracts/c2-replay-resync-contract-v1.md`
- `docs/render/system-freeze/contracts/c3-lifecycle-gating-contract-v1.md`
- `docs/render/system-freeze/contracts/c5-frontend-state-contract-v1.md`
- `docs/render/phases/phase-08-store-isolation-selectors/README.md`
- `docs/render/phases/phase-08-store-isolation-selectors/close-phase-v1.md`
