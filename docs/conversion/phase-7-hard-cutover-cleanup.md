# Phase 7 - Hard Cutover Cleanup

Status: completed  
Estimate: 4-5 person-days (8%)

## 1. Objective

Complete hard cutover to V3 canonical on active paths, remove `lane` from `/v3` contract,
clean dead V2 frontend modules, and keep `/v2` routes in compatibility + deprecated mode.

## 2. In Scope (Completed)

- Removed `/v3` `lane` emission and legacy compat branch in route contract handling.
- Removed V3 `lane` field/type aliases from backend and frontend `ThreadSnapshotV3` types.
- Removed transition env flags from runtime/config:
  - `PLANNINGTREE_V3_LANE_COMPAT_MODE`
  - `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED`
  - `PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL`
- Removed dead adapter production file:
  - `backend/streaming/conversation_v2_to_v3_event_relay.py`
- Removed dead frontend V2 active-path modules and V2-only API client calls.
- Retained `/v2` routes in compatibility mode and documented deprecation policy.

## 3. Deliverables

- `docs/conversion/artifacts/phase-7/deletion-log.md`
- `docs/conversion/artifacts/phase-7/deprecation-notice.md`
- `docs/conversion/artifacts/phase-7/handoff-to-phase-8.md`

## 4. Exit Criteria

- Code search confirms no V2 adapter dependencies on `/v3` active route path.
- `/v3` snapshot/event contract is `threadRole`-only.
- Frontend active path no longer reads `snapshot.lane`.
- Required backend/frontend verification gates pass.

## 5. Verification

- [x] `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py` (21 passed)
- [x] `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py` (1 passed)
- [x] `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py backend/tests/unit/test_conversation_v3_migration.py backend/tests/unit/test_app_config.py` (32 passed)
- [x] `npm run typecheck --prefix frontend`
- [x] `npm run test:unit --prefix frontend` (35 files, 203 tests passed)
- [x] Search gates:
  - backend runtime has no removed env-flag refs
  - frontend active path has no `ThreadSnapshotV3.lane` usage
  - removed V2 FE store/API references have no active consumers

## 6. Risks And Follow-Up (Phase 8)

- `/v2` compatibility routes remain mounted and must be retired in closeout phase.
- Some legacy test narratives still include "lane/v2" wording and should be normalized during final documentation cleanup.
