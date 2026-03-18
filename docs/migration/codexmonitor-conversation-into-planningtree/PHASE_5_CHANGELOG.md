# Phase 5 Changelog

## Entry Format
- Date: `YYYY-MM-DD`
- Change summary:
  - short factual bullets only
- Affected subphases:
  - list one or more of `5.1`, `5.2`, `5.3`
- Reason for update:
  - why the plan, progress, or tracking state changed

## 2026-03-16
- Change summary:
  - implemented execution-first lineage-aware actions on the conversation-v2 path for `continue`, `retry`, `regenerate`, and `cancel`
  - seeded durable execution lineage for ordinary sends, added lazy idempotent lineage backfill for legacy execution transcripts, and added collapsed inline replay plus `status_block` support on the shared execution surface
  - updated Phase 5 tracking so `5.3` is now in progress with execution-first implementation landed, no open lineage-policy blockers, and remaining closeout work limited to replay/reconnect validation and manual QA
- Affected subphases:
  - `5.3`
- Reason for update:
  - record the execution-first 5.3 implementation boundary without overstating replay/reconnect closeout as fully validated

## 2026-03-16
- Change summary:
  - hardened `5.2` execution request resolution so locally initiated resolve no longer double-publishes terminal lifecycle events when native callbacks arrive later
  - converged planning runtime-input lifecycle semantics on the shared conversation-v2 contract through planning snapshot normalization, lifecycle event translation, and a planning v2 resolve route
  - moved `5.2` tracking to complete while keeping `approval_request` explicitly runtime-blocked and narrowing the remaining non-blocking interactive source gap to ask only
- Affected subphases:
  - `5.2`
- Reason for update:
  - record the Phase 5.2 closeout work that finished execution hardening and planning-v2 convergence without overstating approval live parity

## 2026-03-16
- Change summary:
  - created the dedicated `PHASE_5_*` artifact package under the migration docs directory
  - aligned the new package with the actual repo state after the `5.1` hardening pass and `5.2` execution-native runtime-input implementation
  - linked the dedicated package from the existing migration overview and umbrella phase plan
- Affected subphases:
  - `5.1`
  - `5.2`
  - `5.3`
- Reason for update:
  - create a durable Phase 5 source-of-truth package instead of keeping the fuller tracking format only in chat history

## 2026-03-16
- Change summary:
  - implemented `5.2` interactive request lifecycle support on the shared conversation-v2 contract for `approval_request`, `user_input_request`, `user_input_response`, and `request_resolved`
  - wired the execution backend path to persist and stream runtime-input request creation and resolution through durable request and response messages
  - documented the Phase 5.2 runtime boundary explicitly:
    - live + replay on the execution backend path: `request_user_input`, `request_resolved`, `user_input_resolved`
    - contract-ready and replay-safe but runtime-blocked for live parity: `approval_request`
- Affected subphases:
  - `5.2`
- Reason for update:
  - record the current execution-native Phase 5.2 implementation boundary and keep approval runtime limits explicit

## 2026-03-16
- Change summary:
  - hardened `5.1` passive-event targeting so updates attach only to deterministic assistant messages
  - extended the execution streaming path to emit and persist native `plan_block` events using the existing transport signal and final-plan reconciliation
  - documented the current Phase 5.1 backend live-path support matrix explicitly:
    - live + replay: `tool_call`, `plan_block`
    - replay-only on the backend live path: `reasoning`, `tool_result`, `plan_step_update`, `diff_summary`, `file_change_summary`
- Affected subphases:
  - `5.1`
- Reason for update:
  - keep backend live-path claims aligned with the actual transport and replay boundary
