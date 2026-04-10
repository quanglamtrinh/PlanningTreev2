# Phase 3 - `/v3` Route Native Cutover

Status: pending  
Estimate: 4-6 person-days (12%)

## 1. Goal

Move `/v3` routes to call native V3 services directly and remove V2 adapter dependence from route paths.

## 2. In scope

- Refactor `backend/routes/workflow_v3.py`:
  - snapshot by-id
  - events by-id
  - start turn by-id
  - resolve user input by-id
  - plan actions by-id
  - reset by-id policy
- Rewire app state usage from `*_v2` route dependencies to V3 services.
- Preserve all frozen behavior from Phase 0.

## 3. Out of scope

- Large workflow business-service refactor.
- Frontend migration work.

## 4. Work breakdown

- [ ] Switch route dependencies to:
  - `thread_query_service_v3`
  - `thread_runtime_service_v3`
  - workflow service may remain `_v2` temporarily until Phase 4
- [ ] Remove route-level adapters:
  - remove `project_v2_snapshot_to_v3`
  - remove `project_v2_envelope_to_v3` from stream route path
- [ ] Preserve by-id role resolution:
  - execution/audit via workflow state
  - ask via registry (with legacy-session seed only when bridge policy allows)
- [ ] Enforce naming contract:
  - responses/events use canonical `thread_role` (JSON key `threadRole`)
  - no `lane` exposure in new public contract
- [ ] Preserve error semantics:
  - `invalid_request` for mismatch/policy
  - `ask_v3_disabled` while ask gate remains enabled
  - `conversation_stream_mismatch` guard

## 5. Deliverables

- Native `/v3` route wiring to V3 services.
- Updated/passing integration tests.
- Artifact:
  - `docs/conversion/artifacts/phase-3/route-cutover-diff.md`

## 6. Exit criteria

- `/v3` routes no longer read/publish via V2 query/runtime services.
- `test_chat_v3_api_execution_audit.py` passes fully.
- Stream first-frame and reconnect guard behavior pass.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py`
- [ ] `python -m pytest -q backend/tests/unit/test_ask_v3_rollout_phase6_7.py`

## 8. Risks and mitigations

- Risk: SSE event ordering drift.
  - Mitigation: freeze explicit ordering assertions in integration tests.
- Risk: by-id role resolution regression.
  - Mitigation: add focused mismatch and registry-seed test cases.
