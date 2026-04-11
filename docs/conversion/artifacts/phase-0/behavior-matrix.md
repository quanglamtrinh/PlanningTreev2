# Phase 0 Behavior Matrix

Date: 2026-04-09  
Owner: PTM Core Team  
Status: frozen (phase-0 baseline)

Baseline evidence run:

- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py` -> `16 passed in 27.23s`
- `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py` -> `1 passed in 4.99s`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py` -> `11 passed in 0.12s`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_parity_fixtures.py` -> `1 passed in 0.08s`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_fixture_replay.py` -> `2 passed in 0.08s`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py` -> `1 passed in 0.09s`
- `python -m pytest -q backend/tests/unit/test_ask_v3_rollout_phase6_7.py` -> `5 passed in 0.94s`

| scenario_id | surface | endpoint | threadRole | request_shape | expected_status | expected_error_code | expected_event_first_frame | notes |
|---|---|---|---|---|---:|---|---|---|
| B001 | v3 thread by-id | `GET /v3/projects/{project_id}/threads/by-id/{thread_id}?node_id={node_id}` | execution | snapshot read | 200 | - | - | Wrapped `ok/data` snapshot; execution snapshot returns thread + items + `uiSignals.planReady` default. |
| B002 | v3 thread by-id | `GET /v3/projects/{project_id}/threads/by-id/{thread_id}?node_id={node_id}` | ask_planning | snapshot read | 200 | - | - | Ask snapshot by-id succeeds and maps ask thread state to V3 snapshot contract. |
| B003 | v3 thread by-id | `GET /v3/projects/{project_id}/threads/by-id/{thread_id}?node_id={node_id}` | mismatch | snapshot read | 400 | `invalid_request` | - | Unknown or mismatched thread id is rejected by by-id role resolution guard. |
| B004 | v2 workflow state | `GET /v2/projects/{project_id}/nodes/{node_id}/workflow-state` | ask_planning | state read | 200 | - | - | `askThreadId` is returned from registry when present. |
| B005 | v2 workflow state | `GET /v2/projects/{project_id}/nodes/{node_id}/workflow-state` | ask_planning | state read with legacy session seed | 200 | - | - | Registry can be seeded from legacy ask session and reflected in `askThreadId`. |
| B006 | v3 resolve by-id | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/requests/{request_id}/resolve?node_id={node_id}` | execution | answers list | 200 | - | - | Resolve response status is `answer_submitted`; follow-up snapshot shows user-input signal/item transitions to `answered`. |
| B007 | v3 turns by-id | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/turns?node_id={node_id}` | ask_planning | `{ text, metadata }` | 200 | - | - | Ask by-id turn dispatches to runtime with `threadRole=ask_planning`. |
| B008 | v3 resolve by-id | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/requests/{request_id}/resolve?node_id={node_id}` | ask_planning | answers list | 200 | - | - | Resolve response status is `answer_submitted`; snapshot signal converges to `answered`. |
| B009 | v3 plan actions | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions?node_id={node_id}` | execution | `implement_plan` + matching revision | 200 | - | - | Valid plan-ready action dispatches follow-up and returns accepted payload with action metadata. |
| B010 | v3 plan actions | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions?node_id={node_id}` | execution | stale revision | 400 | `invalid_request` | - | Stale plan revision is rejected. |
| B011 | v3 plan actions | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions?node_id={node_id}` | ask_planning | any plan action | 400 | `invalid_request` | - | Plan actions are execution-only. |
| B012 | v3 reset by-id | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/reset?node_id={node_id}` | ask_planning | reset | 200 | - | - | Ask reset clears thread id/items/pending requests and returns snapshot metadata. |
| B013 | v3 reset by-id | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/reset?node_id={node_id}` | execution | reset | 400 | `invalid_request` | - | Execution reset by-id is policy-rejected. |
| B014 | v3 reset by-id | `POST /v3/projects/{project_id}/threads/by-id/{thread_id}/reset?node_id={node_id}` | audit | reset | 400 | `invalid_request` | - | Audit reset by-id is policy-rejected. |
| B015 | v3 stream by-id | `GET /v3/projects/{project_id}/threads/by-id/{thread_id}/events?node_id={node_id}&after_snapshot_version={n}` | execution | SSE subscribe | 200 | - | `thread.snapshot.v3` | First non-heartbeat frame is snapshot; later mapped incremental V3 item events stream correctly. |
| B016 | v3 stream by-id | `GET /v3/projects/{project_id}/threads/by-id/{thread_id}/events?node_id={node_id}&after_snapshot_version={n}` | ask_planning | SSE subscribe | 200 | - | `thread.snapshot.v3` | Ask stream follows same first-frame snapshot rule and mapped incremental event behavior. |
| B017 | v3 stream by-id | `GET /v3/projects/{project_id}/threads/by-id/{thread_id}/events?node_id={node_id}&after_snapshot_version=999` | execution | reconnect guard | 409 | `conversation_stream_mismatch` | - | Snapshot-version mismatch is typed and enforced. |
| B018 | v1 legacy ask | `/v1/projects/{project_id}/nodes/{node_id}/chat/*` | ask_planning | session/message/reset/events | 400 | `invalid_request` | - | Legacy ask chat handlers are disabled on `/v1`. |
| B019 | v2 role route | `/v2/projects/{project_id}/nodes/{node_id}/threads/ask_planning*` | ask_planning | snapshot/turn | 400 | `invalid_request` | - | Role-based ask thread endpoints are rejected in favor of `/v3` by-id APIs. |
| B020 | v3 ask gate | `GET /v3/projects/{project_id}/threads/by-id/{thread_id}?node_id={node_id}` | ask_planning | snapshot read with backend gate off | 409 | `ask_v3_disabled` | - | Ask gate contract is preserved as typed 409 while gate exists. |
| B021 | v1 finish-task | `POST /v1/projects/{project_id}/nodes/{node_id}/finish-task` | execution/audit workflow | workflow action | 200 | - | - | Phase-6 integration verifies production cutover behavior: v2 execution/audit snapshots updated, no legacy execution/audit chat transcript writes. |

Source coverage:

- `backend/tests/integration/test_chat_v3_api_execution_audit.py`
- `backend/tests/integration/test_phase6_execution_audit_cutover.py`
- `backend/tests/unit/test_ask_v3_rollout_phase6_7.py`
