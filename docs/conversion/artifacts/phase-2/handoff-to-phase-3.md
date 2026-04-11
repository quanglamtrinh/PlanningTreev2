# Phase 2 -> Phase 3 Handoff

## Completed in Phase 2
- `ThreadQueryServiceV3` implemented with V3-first read and V2 read-bridge policy.
- `ThreadRuntimeServiceV3` implemented with native V3 mutation/event projection path.
- Bridge policy controls implemented:
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE`
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST`
- Typed error implemented:
  - `conversation_v3_missing` (`409`, `error.details={}`)
- Parallel app wiring added in `backend/main.py`:
  - `thread_query_service_v3`
  - `thread_runtime_service_v3`
  - no `/v3` route cutover yet.

## Verification Evidence
- `python -m pytest -q backend/tests/unit/test_app_config.py backend/tests/unit/test_thread_query_service_v3.py backend/tests/unit/test_thread_runtime_service_v3.py`
  - `20 passed`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - `18 passed`

## Phase 3 Entry Scope
- Cut over `backend/routes/workflow_v3.py` dependencies from V2 query/runtime to V3 services.
- Keep route shape stable.
- Preserve stream-first snapshot + mismatch guard behavior parity.
