# Phase 0 Policy Matrix

Date: 2026-04-10  
Owner: PTM Core Team  
Status: frozen (phase-0 policy baseline)

This matrix freezes policy semantics across `/v1`, `/v2`, and `/v3` for the conversion window.

| policy_id | surface | route pattern | method | policy expectation | expected_status | expected_error_code | evidence |
|---|---|---|---|---|---:|---|---|
| P001 | v1 | `/v1/projects/{project_id}/nodes/{node_id}/chat/session` | GET | Ask legacy chat handler is disabled on v1. | 400 | `invalid_request` | `test_v1_legacy_chat_ask_handlers_are_disabled` |
| P002 | v1 | `/v1/projects/{project_id}/nodes/{node_id}/chat/message` | POST | Ask legacy chat handler is disabled on v1. | 400 | `invalid_request` | `test_v1_legacy_chat_ask_handlers_are_disabled` |
| P003 | v1 | `/v1/projects/{project_id}/nodes/{node_id}/chat/reset` | POST | Ask legacy chat handler is disabled on v1. | 400 | `invalid_request` | `test_v1_legacy_chat_ask_handlers_are_disabled` |
| P004 | v1 | `/v1/projects/{project_id}/nodes/{node_id}/chat/events` | GET | Ask legacy chat handler is disabled on v1. | 400 | `invalid_request` | `test_v1_legacy_chat_ask_handlers_are_disabled` |
| P005 | v2 | `/v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}` | GET | Role-based ask/execution/audit thread routes are rejected; use `/v3` by-id APIs. | 400 | `invalid_request` | ask path validated in `test_v2_ask_thread_role_is_rejected`; same route guard applies to execution/audit. |
| P006 | v2 | `/v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}/turns` | POST | Role-based ask/execution/audit thread routes are rejected; use `/v3` by-id APIs. | 400 | `invalid_request` | ask path validated in `test_v2_ask_thread_role_is_rejected`; same route guard applies to execution/audit. |
| P007 | v2 | `/v2/projects/{project_id}/nodes/{node_id}/workflow-state` | GET | Workflow state endpoint remains available during conversion. | 200 | - | `test_v2_workflow_state_includes_ask_thread_id_from_registry`, `test_v2_workflow_state_seeds_ask_thread_id_from_legacy_session` |
| P008 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}` | GET | By-id snapshot is wrapped in `{ ok, data }` on success. | 200 | - | `test_v3_execution_snapshot_by_id_returns_wrapped_snapshot`, `test_v3_ask_snapshot_by_id_returns_wrapped_snapshot` |
| P009 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}` | GET | Thread id mismatch is rejected by route guard. | 400 | `invalid_request` | `test_v3_by_id_snapshot_rejects_thread_id_mismatch` |
| P010 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}` | GET | Ask by-id path must return typed gate error when ask backend gate is off. | 409 | `ask_v3_disabled` | `test_v3_ask_by_id_returns_typed_error_when_backend_gate_off` |
| P011 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}/events` | GET | First non-heartbeat event frame is `thread.snapshot.v3`. | 200 | - | `test_v3_execution_stream_emits_snapshot_and_incremental_events`, `test_v3_ask_stream_emits_snapshot_and_incremental_events` |
| P012 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}/events` | GET | Reconnect guard mismatch returns typed stream mismatch error. | 409 | `conversation_stream_mismatch` | `test_v3_execution_stream_reconnect_by_version_and_guard` |
| P013 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}/requests/{request_id}/resolve` | POST | Resolve response status remains `answer_submitted`; signal converges through snapshot updates. | 200 | - | `test_v3_execution_resolve_user_input_by_id_updates_snapshot_and_signal`, `test_v3_ask_resolve_user_input_by_id_updates_snapshot_and_signal` |
| P014 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}/reset` | POST | Reset by-id is ask-only. | 200 (ask) / 400 (execution,audit) | `invalid_request` (non-ask) | `test_v3_ask_reset_by_id_clears_thread_snapshot`, `test_v3_reset_policy_rejects_execution_and_audit_threads` |
| P015 | v3 | `/v3/projects/{project_id}/threads/by-id/{thread_id}/plan-actions` | POST | Plan-ready actions are execution-only and enforce stale-revision guards. | 200 (valid execution) / 400 (invalid policy or stale revision) | `invalid_request` (invalid/stale) | `test_v3_execution_plan_actions_by_id_validate_stale_and_dispatch_followup`, `test_v3_plan_actions_on_ask_thread_reject_policy` |
| P016 | target active path | `/v3/projects/{project_id}/nodes/{node_id}/workflow-state`, `/v3/projects/{project_id}/nodes/{node_id}/workflow/*`, `/v3/projects/{project_id}/events` | GET/POST | Frontend primary workflow control-plane path must be v3-only (contract lock). | contract lock | - | `docs/conversion/workflow-v3-control-plane-contract.md`, `docs/conversion/progress.yaml` |
| P017 | v3 bridge disabled | `/v3` thread snapshot/query path (Phase 2 target behavior) | GET | If V3 snapshot is missing and bridge mode is `disabled`, return typed missing-snapshot gate error. | 409 | `conversation_v3_missing` | phase-0 lock in `decision-log.md`; implementation/test in Phase 2 |

## Naming and contract locks

- Canonical naming target is `thread_role` (JSON key `threadRole`) for V3 APIs.
- While `/v3` still runs through adapter-based route paths (Phase 0-2 baseline), legacy `lane` may appear as compatibility payload shape.
- Enforced transition gates:
  - Phase 3: threadRole-primary route output on native `/v3` stack (temporary lane dual-emit allowed only for migration safety).
  - Phase 5: frontend active path no longer reads `lane`.
  - Phase 7: `lane` emission and lane-based types/tests removed.

## Bridge policy locks

- Bridge timing: Phase 2 start.
- Read order: V3 first, optional V2 read-through fallback, then persist V3.
- New V3 path does not write back to V2.
- Mode contract: `enabled | allowlist | disabled`.
- Disabled mode contract: missing V3 snapshot returns typed `conversation_v3_missing`.
- Disabled mode HTTP contract: `409` with envelope `error.details` as `{}`.
