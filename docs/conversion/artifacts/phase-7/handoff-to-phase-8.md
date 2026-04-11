# Handoff: Phase 7 -> Phase 8

Date: 2026-04-10
Owner handoff: BE + FE -> BE + FE + QA

## 1. Phase 7 status

Phase 7 is complete and Phase 8 is ready to execute.

## 2. What was delivered in Phase 7

- Hard cutover on active `/v3` contract:
  - `/v3` snapshot/event contract is now `threadRole`-only.
  - `lane` is no longer emitted on active `/v3` path.
- Transition-flag cleanup:
  - removed `PLANNINGTREE_V3_LANE_COMPAT_MODE`
  - removed `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED`
  - removed `PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL`
- Backend wiring cleanup:
  - removed dead V2->V3 relay adapter from production code path.
  - cleaned canonical workflow broker/publisher naming on active path.
- Frontend aggressive cleanup:
  - removed `lane` from `ThreadSnapshotV3` type.
  - removed active-path fallback reads from `snapshot.lane`.
  - removed dead V2 stores/bridge modules and related dead unit tests.
  - removed unused V2 API-client methods with no active consumers.
- Compatibility policy:
  - `/v2` routes remain mounted for temporary compatibility only.
  - deprecation policy is documented; no new feature scope on `/v2`.

## 3. Artifacts produced

- `docs/conversion/artifacts/phase-7/deletion-log.md`
- `docs/conversion/artifacts/phase-7/deprecation-notice.md`
- `docs/conversion/phase-7-hard-cutover-cleanup.md`
- `docs/conversion/progress.yaml` (Phase 7 completed, Phase 8 in progress)

## 4. Verification evidence

- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py` -> 21 passed
- `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py` -> 1 passed
- `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py backend/tests/unit/test_conversation_v3_migration.py backend/tests/unit/test_app_config.py` -> 32 passed
- `npm run typecheck --prefix frontend` -> passed
- `npm run test:unit --prefix frontend` -> 35 files passed, 203 tests passed

## 5. Known carry-over for Phase 8 (resolved at closeout)

- `/v2` compatibility routes were sunset and hard removed during Phase 8 closeout.
- Legacy language in some historical docs/tests may still say `lane`/`v2` as narrative context, not active contract behavior.
- Frontend test output includes non-blocking React Router/`act(...)` warnings; no failing assertions.

## 6. Phase 8 execution checklist

1. Stabilization soak:
   - monitor `/v3` active flows for regressions and error-rate drift.
   - rerun baseline gate bundle at agreed soak intervals.
2. `/v2` retirement prep:
   - finalize removal window and communication timeline.
   - list external/internal consumers still on `/v2` (if any).
3. Documentation closeout:
   - normalize remaining legacy wording where misleading.
   - publish final architecture snapshot (`native v3 end-to-end` state).
4. Program closeout decision:
   - confirm acceptance criteria in `phase-8-stabilization-closeout.md`.
   - mark migration complete when stabilization window passes.

## 7. Suggested Phase 8 gate bundle

- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py`
- `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py backend/tests/unit/test_conversation_v3_migration.py backend/tests/unit/test_app_config.py`
- `npm run typecheck --prefix frontend`
- `npm run test:unit --prefix frontend`
