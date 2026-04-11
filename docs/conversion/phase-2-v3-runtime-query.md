# Phase 2 - V3 Runtime/Query Native + Compatibility Read Bridge

Status: completed  
Estimate: 6-8 person-days (14%)

## 1. Goal

Build native V3 query/runtime for ask/execution/audit without V2 snapshot/item dependencies.

## 2. In scope

- `ThreadQueryServiceV3`:
  - get snapshot
  - build stream snapshot
  - persist mutation
  - reset thread (ask policy enforced at route/service layer)
- `ThreadRuntimeServiceV3`:
  - start turn
  - resolve user input
  - begin/complete turn
  - stream agent turns into canonical V3 items/events
- Canonical V3 payload naming:
  - emit `threadRole` as canonical field
  - keep optional temporary `lane` dual-emit capability for Phase 3-5 migration safety; remove in Phase 7
- Remove legacy ask mirroring from the new runtime path.
- Compatibility read bridge:
  - read `conversation_v3` first
  - if missing, read-through from V2, convert, then persist to V3
  - no V2 back-write on new path
  - explicit mode: `enabled | allowlist | disabled`
  - `disabled` returns typed `conversation_v3_missing` (`409`, `error.details` remains `{}`) on missing V3 snapshot
  - env-only bridge controls:
    - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE`
    - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST` (comma-separated project ids)

## 2.1 Bridge workflow examples (locked behavior)

Example A - Legacy project when bridge is enabled:

1. Request arrives on `/v3` query path.
2. Query reads `conversation_v3/{node_id}/{thread_role}.json`.
3. If missing, query reads legacy V2 source, converts to canonical V3 (`threadRole`), and persists into `conversation_v3`.
4. Response returns canonical V3 payload.
5. Next read for the same thread is served directly from V3.

Example B - After bridge sunset (disabled):

1. Request arrives on `/v3` query path.
2. Query reads `conversation_v3` and finds no snapshot.
3. Query must not read V2 fallback.
4. Query returns typed `conversation_v3_missing`.
5. Operator runs migration, then retry succeeds from V3.

Example C - Controlled rollback with allowlist:

1. Bridge global mode is `disabled`, but a temporary project allowlist is enabled.
2. A listed project can use V2 read-through once, then persists to V3.
3. Non-listed projects still receive `conversation_v3_missing`.
4. After canary fix/migration validation, allowlist is cleared and system returns to strict disabled mode.

## 3. Out of scope

- Production route cutover to V3 services.
- Workflow service cutover (`finish_task`, `execution_audit_workflow`, `review_service`).

## 4. Work breakdown

- [x] Add new query service:
  - `backend/conversation/services/thread_query_service_v3.py`
- [x] Add new runtime service:
  - `backend/conversation/services/thread_runtime_service_v3.py`
- [x] Define canonical V3 event envelope for persist/publish:
  - snapshot
  - item upsert/patch
  - lifecycle
  - user-input signal
  - thread error
- [x] Integrate request ledger for V3 pending requests.
- [x] Implement compatibility read bridge in query path.
- [x] Implement bridge mode switch:
  - `enabled`: fallback for all projects
  - `allowlist`: fallback only for listed project ids
  - `disabled`: no fallback; return `conversation_v3_missing`
- [x] Do not call `sync_legacy_turn_state` on V3 path.
- [x] Add runtime/query V3 unit tests.

## 5. Deliverables

- V3 runtime/query services plus tests.
- Artifacts:
  - `docs/conversion/artifacts/phase-2/runtime-sequence.md`
  - `docs/conversion/artifacts/phase-2/event-contract-v3.md`
  - `docs/conversion/artifacts/phase-2/bridge-policy.md`

## 6. Exit criteria

- Start turn and resolve user input work on V3 runtime/query in isolated tests.
- Stream payload format is canonical V3.
- No required data dependency on `ThreadSnapshotV2`.
- Legacy projects with only V2 snapshots can still be read safely through bridge.
- Disabled bridge behavior and typed error path are covered by tests.

## 7. Verification

- [x] `python -m pytest -q backend/tests/unit/test_thread_query_service_v3.py` (new)
- [x] `python -m pytest -q backend/tests/unit/test_thread_runtime_service_v3.py` (new)
- [x] `python -m pytest -q backend/tests/unit/test_conversation_v3_fixture_replay.py`

## 8. Risks and mitigations

- Risk: drift in raw Codex event -> V3 semantic mapping.
  - Mitigation: replay fixtures and parity fixture gates.
- Risk: request-ledger mismatch for user input lifecycle.
  - Mitigation: add deterministic state transition tests.
- Risk: bridge sunset causes rare legacy projects to fail unexpectedly.
  - Mitigation: allowlist rollback mode plus explicit canary and report-first rollout.
