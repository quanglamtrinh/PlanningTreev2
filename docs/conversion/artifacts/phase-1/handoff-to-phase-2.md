# Phase 1 -> Phase 2 Handoff

Date: 2026-04-10  
From: Conversion Phase 1 (V3 Domain/Store Foundation)  
To: Conversion Phase 2 (V3 Runtime/Query Native + Compatibility Read Bridge)

## 1. Phase 1 close summary

Phase 1 is closed with V3 domain/store foundation completed and verified.

- Implemented canonical V3 snapshot domain shape with `threadRole`.
- Added compatibility read normalization from legacy `lane` to canonical `threadRole`.
- Added dedicated V3 store:
  - `backend/conversation/storage/thread_snapshot_store_v3.py`
  - canonical path `.planningtree/conversation_v3/{node_id}/{thread_role}.json`
- Wired `Storage.thread_snapshot_store_v3` in parallel with existing V2 store wiring.
- Published Phase 1 schema artifact:
  - `docs/conversion/artifacts/phase-1/storage-schema.md`

Verification evidence:

- `python -m pytest -q backend/tests/unit/test_conversation_v3_stores.py backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py`
  - result: `17 passed`
- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - result: `16 passed`

## 2. Locked boundaries for Phase 2

1. Foundation-vs-route sequencing remains enforced:
- Phase 1 canonicalized domain/store internals.
- Route/output tightening (`threadRole`-primary route payload and lane cleanup) is deferred to Phase 3/5/7.

2. Compatibility bridge contract must be implemented as locked:
- Read order: V3 first, optional V2 read-through, then persist V3.
- No V2 back-write from new V3 path.
- Bridge mode is env-only: `enabled | allowlist | disabled`.
- `disabled` + missing V3 snapshot must return `409 conversation_v3_missing` with `error.details = {}`.

3. Thread registry identity remains source of truth:
- Keep role <-> threadId binding consistent with registry-first policy.

## 3. Phase 2 execution focus

- Build `ThreadQueryServiceV3` and `ThreadRuntimeServiceV3` as native V3 core for ask/execution/audit.
- Implement compatibility read bridge behavior per locked policy.
- Ensure stream/event payloads stay canonical V3 contract.
- Keep Phase 2 scoped to runtime/query; route cutover stays in Phase 3.

## 4. Entry checklist for Phase 2 PRs

1. Do not regress current `/v3` route behavior while runtime/query services are being introduced.
2. Do not add V2 back-write in bridge logic.
3. Ensure bridge mode behavior (`enabled`, `allowlist`, `disabled`) has explicit tests.
4. Preserve phased naming rollout (no hard lane removal on active route in Phase 2).
5. Add and run target suites:
   - `backend/tests/unit/test_thread_query_service_v3.py` (new)
   - `backend/tests/unit/test_thread_runtime_service_v3.py` (new)
   - `backend/tests/unit/test_conversation_v3_fixture_replay.py`
