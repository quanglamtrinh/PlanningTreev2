# Phase 12 Preflight v1

Status: Frozen preflight checklist.

Phase: `phase-12-data-volume-and-heavy-content-ux`.

## Entry Criteria

From `docs/render/system-freeze/phase-manifest-v1.json`:

1. `phase_11_passed`
2. `heavy_content_visibility_policy_frozen_v2`

## Required Frozen Inputs

1. `heavy-content-visibility-policy-v2.md`
2. `docs/render/decision-pack-v1.md`
3. `docs/render/system-freeze/phase-gates-v1.json` (P12-G1, P12-G2, P12-G3)
4. baseline manifest in `./evidence/baseline-manifest-v1.json`

Reference only (superseded for E01 cap behavior): `heavy-content-visibility-policy-v1.md`.

## Contract Safety Checklist

1. Snapshot API remains backward compatible when `live_limit` is omitted.
2. Replay/resync cursor contract remains unchanged.
3. Frontend truncation path is presentation-only.
4. Backend semantic coalescing remains canonical and deterministic.
5. Anchor invariants remain intact during history prepend/load-more.
6. Adaptive cap profile resolution is deterministic (`env override > runtime hint > standard`).

## Validation Checklist

1. `npm run typecheck --prefix frontend`
2. `npm run test:unit --prefix frontend -- tests/unit/threadByIdStoreV3.test.ts tests/unit/MessagesV3.test.tsx`
3. `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -k "live_limit_returns_tail_and_history_meta or history_by_id_paginates_by_before_sequence_cursor"`
4. `python -m pytest backend/tests/unit/test_thread_runtime_service_v3.py -k "compacted_and_non_compacted_projection_match"`
5. `npm run check:render_freeze`
6. source evidence scripts:
   - `python scripts/phase12_long_session_volume_tests.py --self-test ...`
   - `python scripts/phase12_heavy_row_classification_suite.py --self-test ...`
   - `python scripts/phase12_preview_to_full_navigation_tests.py --self-test ...`
7. gate aggregation:
   - `python scripts/phase12_gate_report.py --self-test ...`
