# Phase 8 Smoke Results

Date: 2026-04-10  
Owner: BE + FE + QA

## Run A (T0)

- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py` -> `19 passed in 16.97s`
- `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py` -> `1 passed in 8.68s`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py backend/tests/unit/test_conversation_v3_migration.py backend/tests/unit/test_app_config.py backend/tests/unit/test_phase8_v2_retirement_guards.py` -> `33 passed in 7.52s`
- `npm run typecheck --prefix frontend` -> passed
- `npm run test:unit --prefix frontend` -> `35 files passed, 203 tests passed`

## Run B (verification rerun)

- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py` -> `19 passed in 16.09s`
- `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py` -> `1 passed in 8.75s`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py backend/tests/unit/test_conversation_v3_migration.py backend/tests/unit/test_app_config.py backend/tests/unit/test_phase8_v2_retirement_guards.py` -> `33 passed in 4.32s`
- `npm run typecheck --prefix frontend` -> passed
- `npm run test:unit --prefix frontend` -> `35 files passed, 203 tests passed`

## Spot Checks

- Representative `/v2` endpoints now return `404`:
  - `GET /v2/projects/p/nodes/n/threads/ask_planning` -> `404`
  - `GET /v2/projects/p/nodes/n/workflow-state` -> `404`
- Active `/v3` conversation and workflow paths remain green through both runs.
