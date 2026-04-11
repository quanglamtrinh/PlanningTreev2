# Phase 8 - Stabilization And Closeout

Status: completed  
Estimate: 2-3 person-days (4%)

## 1. Objective

Stabilize after hard cutover, validate final active-path behavior, and close the native V3 conversion track.

## 2. Implemented Outcomes

- Hard removed backend `/v2` APIs:
  - `/v2` routers are unmounted from app bootstrap.
  - Legacy `/v2` route modules are removed from the backend route tree.
  - Requests to representative `/v2` endpoints now return `404`.
- Removed backend production aliases dedicated to `/v2` conversation path:
  - `app.state.thread_query_service_v2`
  - `app.state.thread_runtime_service_v2`
  - `app.state.conversation_event_broker_v2`
  - `app.state.request_ledger_service_v2`
- Removed dedicated `/v2` integration tests and retained only V3/canonical checks.
- Added static guard coverage to prevent accidental `/v2` remount or alias reintroduction.

## 3. Deliverables

- `docs/conversion/artifacts/phase-8/smoke-results.md`
- `docs/conversion/artifacts/phase-8/stabilization-notes.md`
- `docs/conversion/artifacts/phase-8/closeout-summary.md`

## 4. Exit Criteria (Met)

- No open conversion blockers on active `/v3` path.
- Full gate bundle executed in Run A and Run B without failures.
- `/v2` hard removal behavior validated (`404` spot checks).
- BE/FE/QA closeout sign-off recorded in phase-8 artifacts.
- Tracker moved to completed.

## 5. Verification

- [x] `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py` (19 passed)
- [x] `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py` (1 passed)
- [x] `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py backend/tests/unit/test_conversation_v3_migration.py backend/tests/unit/test_app_config.py backend/tests/unit/test_phase8_v2_retirement_guards.py` (33 passed)
- [x] `npm run typecheck --prefix frontend`
- [x] `npm run test:unit --prefix frontend` (35 files, 203 tests passed)
- [x] Spot-check `/v2` hard removal:
  - `GET /v2/projects/{project_id}/nodes/{node_id}/threads/ask_planning` -> `404`
  - `GET /v2/projects/{project_id}/nodes/{node_id}/workflow-state` -> `404`
