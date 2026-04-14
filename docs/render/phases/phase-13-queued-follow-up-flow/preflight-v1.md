# Phase 13 Preflight v1

Status: Frozen preflight checklist.

Phase: `phase-13-queued-follow-up-flow`.

## Entry Criteria

From `docs/render/system-freeze/phase-manifest-v1.json`:

1. `phase_12_passed`
2. `queue_confirmation_risk_policy_frozen`

## Required Frozen Inputs

1. `queue-confirmation-risk-policy-v1.md`
2. `docs/render/decision-pack-v1.md`
3. `docs/render/system-freeze/phase-gates-v1.json` (`P13-G1`, `P13-G2`, `P13-G3`)
4. baseline manifest in `./evidence/baseline-manifest-v1.json`

## Contract Safety Checklist

1. Phase 13 queue is execution-lane only (`ask_planning` unchanged).
2. Existing backend wire/API contract stays unchanged.
3. Queue send path propagates per-entry `idempotencyKey`.
4. Single-flight send invariant holds (`<= 1` sending entry).
5. No queued message loss across reload (`localStorage` hydrate/dehydrate).
6. `requires_confirmation` entries are never auto-sent.
7. Plan-ready gate pauses auto-flush but allows explicit manual send path.

## Validation Checklist

1. `npm run typecheck --prefix frontend`
2. `npx vitest run tests/unit/threadByIdStoreV3.test.ts tests/unit/BreadcrumbChatViewV2.test.tsx` (run from `frontend/`)
3. `npm run check:render_freeze`
4. source evidence scripts:
   - `python scripts/phase13_queue_state_machine_suite.py --self-test ...`
   - `python scripts/phase13_queue_reorder_integration.py --self-test ...`
   - `python scripts/phase13_queue_risk_policy_tests.py --self-test ...`
5. gate aggregation:
   - `python scripts/phase13_gate_report.py --self-test ...`
