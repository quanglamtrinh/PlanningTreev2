# Ask Thread V3 - Phase 0-1 Handoff (Implemented Foundation)

Status: implemented.

Date: 2026-04-03.

Owner scope: backend V3 ask-lane foundation + contract freeze artifacts for Phase 0-1.

## 1. Goal and boundary recap

This handoff confirms delivery of:

- Phase 0 objective (contract freeze): architecture/contract decisions locked so Phase 1 implementation does not re-decide semantics.
- Phase 1 objective (backend foundation): ask lane works on shared V3 by-id route + thread registry.

Out of scope intentionally kept:

- No ask UI route cutover in this phase (ask default UI path remains legacy).
- No write-scope enforcement detail in this phase (deferred to Phase 2).
- No post-FinishTask ask policy flip in this phase (deferred to Phase 2).

## 2. Contract decisions frozen in code/docs

### 2.1 Lane and naming mapping

- Internal role remains `ask_planning`.
- Public V3 lane now includes `ask | execution | audit`.
- Fixed mapping:
  - `ask_planning -> ask`
  - `execution -> execution`
  - `audit -> audit`

### 2.2 V3 by-id lane matrix (effective behavior)

- `GET snapshot`: ask/execution/audit supported.
- `GET events`: ask/execution/audit supported.
- `POST turns`: ask/execution supported, audit rejected (read-only).
- `POST requests/{id}/resolve`: ask/execution/audit supported when request exists for resolved thread.
- `POST plan-actions`: execution-only.
- `POST reset`: ask-only (new endpoint).

### 2.3 Thread resolution policy (implemented)

- Resolver validates node existence first.
- Resolution order:
  1. execution/audit from workflow state active thread ids.
  2. ask from thread registry (`ask_planning` entry).
  3. migration-compatible seed for ask from legacy ask session if registry entry is empty.
- URL `thread_id` must match resolved thread id exactly; mismatch returns `InvalidRequest`.

## 3. Implemented changes

### 3.1 Backend contract/type/projector

- Added `ask` to V3 lane type and lane constants.
- Updated V3 projector lane mapping for `ask_planning -> ask`.

### 3.2 Backend route behavior (shared by-id V3)

- Replaced execution/audit-only resolution path with generalized resolver for ask/execution/audit.
- Snapshot/events now consume resolved lane through V2 query/runtime pipeline.
- `turns` handler dispatch:
  - execution: existing execution follow-up flow.
  - ask: `thread_runtime_service_v2.start_turn(...)`.
  - audit: reject.
- `resolve` handler dispatches via resolved role (includes ask).
- Added `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/reset?node_id=...`:
  - ask: `thread_query_service_v2.reset_thread(...)`.
  - execution/audit: reject.
- `plan-actions` unchanged as execution-only.

### 3.3 Frontend API surface (contract readiness)

- Added `ask` to `ThreadLaneV3`.
- Added `ResetThreadV3Response`.
- Added API client method `resetThreadByIdV3(...)`.

Note: no routing or UI behavior switch was made for ask in this phase.

## 4. Test evidence

Executed:

- `python -m pytest backend/tests/unit/test_conversation_v3_projector.py backend/tests/integration/test_chat_v3_api_execution_audit.py -q`

Result:

- `20 passed`

Added/extended coverage:

- Unit: ask lane projection mapping.
- Integration:
  - ask by-id snapshot (`lane=ask`)
  - ask by-id snapshot with registry seed from legacy session
  - thread id mismatch rejection
  - ask by-id events snapshot + incremental event mapping
  - ask by-id turns dispatch to runtime
  - ask by-id resolve updates user-input signal
  - ask by-id reset clears ask thread state
  - policy rejection:
    - plan-actions on ask
    - reset on execution/audit

## 5. Decision log (explicit defer to Phase 2)

Still deferred by design:

- Ask post-FinishTask strict read-only policy shift.
- Artifact write-scope enforcement (frame/clarify/spec-only write boundary).
- Rollout gate wiring (`ask_v3_backend_enabled`, `ask_v3_frontend_enabled`) beyond naming/semantics freeze.

## 6. Changed file index (Phase 0-1 implementation)

- `backend/conversation/domain/types_v3.py`
- `backend/conversation/projector/thread_event_projector_v3.py`
- `backend/routes/workflow_v3.py`
- `backend/tests/unit/test_conversation_v3_projector.py`
- `backend/tests/integration/test_chat_v3_api_execution_audit.py`
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`

## 7. Recommended immediate next step (Phase 2 start)

1. Add ask runtime guard policy for strict read-only post-FinishTask.
2. Add server-side artifact write-scope enforcement (`frame.md`, `clarify`, `spec` + required metadata sidecars only).
3. Add dedicated guard tests (unit + integration) before any UI ask cutover work.
