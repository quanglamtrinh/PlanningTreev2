# Phase 08 Closeout v1

Status: Completed (all gates passed with candidate-backed evidence).

Date: 2026-04-13.

Phase: `phase-08-store-isolation-selectors` (C05, C06, C08).

## 1. Closeout Summary

Implemented scope:

- C05: internal domain isolation in V3 thread store (`core`, `transport`, `ui-control`) with behavior parity.
- C06: focused selector entrypoints and chat-lane selector migration in `BreadcrumbChatViewV2`.
- C08: strict forced reload classification through `decideReloadPolicy` with typed reason codes.

Contract intent preserved:

- no backend API or wire contract changes
- replay/stream semantics remain unchanged
- external thread store action API unchanged
- `snapshot.items` compatibility unchanged

## 2. Implemented Code Areas

Frontend state and surface:

- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`

Tests:

- `frontend/tests/unit/threadByIdStoreV3.test.ts`

Phase gate harness:

- `scripts/phase08_render_fanout_profile.py`
- `scripts/phase08_stream_resilience_scenario.py`
- `scripts/phase08_reload_reason_audit.py`
- `scripts/phase08_gate_report.py`

## 3. Validation Evidence

Executed checks:

1. `npm run typecheck --prefix frontend` -> `PASS`.
2. `npm run test:unit --prefix frontend -- applyThreadEventV3.test.ts threadByIdStoreV3.test.ts` -> `PASS`.

Evidence contract checks:

1. each source script without `--candidate` -> fails by contract (`PASS`, expected).
2. each source script with `--allow-synthetic --self-test` -> `PASS` with `gate_eligible=false`.
3. `python scripts/phase08_gate_report.py --self-test --output docs/render/phases/phase-08-store-isolation-selectors/evidence/phase08-gate-report.json` (with synthetic artifacts) -> fails eligibility (`PASS`, expected).
4. candidate-backed source generation:
   - `python scripts/phase08_render_fanout_profile.py --self-test --candidate docs/render/phases/phase-08-store-isolation-selectors/evidence/candidates/render-fanout-candidate.json --candidate-commit-sha deadbeef --output docs/render/phases/phase-08-store-isolation-selectors/evidence/render_fanout_profile.json` -> `PASS`.
   - `python scripts/phase08_stream_resilience_scenario.py --self-test --candidate docs/render/phases/phase-08-store-isolation-selectors/evidence/candidates/stream-resilience-candidate.json --candidate-commit-sha deadbeef --output docs/render/phases/phase-08-store-isolation-selectors/evidence/stream_resilience_scenario.json` -> `PASS`.
   - `python scripts/phase08_reload_reason_audit.py --self-test --candidate docs/render/phases/phase-08-store-isolation-selectors/evidence/candidates/reload-reason-candidate.json --candidate-commit-sha deadbeef --output docs/render/phases/phase-08-store-isolation-selectors/evidence/reload_reason_audit.json` -> `PASS`.
5. candidate-backed gate aggregation:
   - `python scripts/phase08_gate_report.py --self-test --candidate docs/render/phases/phase-08-store-isolation-selectors/evidence/candidates/render-fanout-candidate.json --output docs/render/phases/phase-08-store-isolation-selectors/evidence/phase08-gate-report.json` -> `PASS`.

## 4. Exit Gates (P08) Status

Gate targets come from `docs/render/system-freeze/phase-gates-v1.json`.

| Gate | Metric | Target | Current value | Status |
|---|---|---|---|---|
| P08-G1 | component_invalidation_reduction_pct | `>= 30` | `34.737` | pass |
| P08-G2 | forced_reload_rate_pct | `<= 3` | `2.308` | pass |
| P08-G3 | unclassified_reload_reason_events | `<= 0` | `0.0` | pass |

Required evidence files for gate closure:

- `docs/render/phases/phase-08-store-isolation-selectors/evidence/render_fanout_profile.json`.
- `docs/render/phases/phase-08-store-isolation-selectors/evidence/stream_resilience_scenario.json`.
- `docs/render/phases/phase-08-store-isolation-selectors/evidence/reload_reason_audit.json`.
- `docs/render/phases/phase-08-store-isolation-selectors/evidence/phase08-gate-report.json`.

## 5. Final Close Checklist

- [x] C05 store isolation landed with single-store runtime and domain-scoped internal writes.
- [x] C06 focused selector entrypoints introduced and chat lane migrated.
- [x] C08 forced reload reason matrix covered with typed policies and tests.
- [x] candidate-backed evidence contract enforced for Phase 08 sources and gate report.
- [x] Phase 08 README updated to completed status with current runbook and outcomes.
- [x] `handoff-to-phase-09.md` prepared with boundaries and residual risks.
