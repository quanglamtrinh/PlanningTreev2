# Phase 11 Preflight v1

Status: Frozen preflight checklist.

Phase: `phase-11-heavy-compute-off-main-thread`.

## Entry Criteria

From `docs/render/system-freeze/phase-manifest-v1.json`:

1. `phase_10_passed`
2. `worker_result_versioning_policy_frozen`

## Required Frozen Inputs

1. `worker-result-versioning-policy-v1.md`
2. `docs/render/system-freeze/phase-gates-v1.json` (P11-G1, P11-G2, P11-G3)
3. baseline manifest in `./evidence/baseline-manifest-v1.json`

## Implementation Safety Checklist

1. Phase 11 mode defaults to `off`.
2. `shadow` mode does not apply worker artifacts.
3. `on` mode enforces version-token stale drop before apply.
4. worker failure path preserves sync output semantics.
5. markdown defer path does not alter canonical content.

## Validation Checklist

1. `npm run typecheck --prefix frontend`
2. `npx vitest run tests/unit/messagesV3.phase10.test.tsx tests/unit/MessagesV3.test.tsx tests/unit/parseArtifactCache.test.ts tests/unit/commandOutputTail.test.ts`
3. `npm run check:render_freeze`
4. source evidence scripts:
   - `python scripts/phase11_heavy_payload_profile.py --self-test ...`
   - `python scripts/phase11_worker_versioning_tests.py --self-test ...`
   - `python scripts/phase11_heavy_content_interaction_smoke.py --self-test ...`
5. gate aggregation:
   - `python scripts/phase11_gate_report.py --self-test ...`
