# Phase 5 Plan

## Summary
- Phase 5 extends the conversation-v2 path from the Phase 3/4 text-first baseline to richer semantics, interactive workflow state, and lineage-aware actions.
- Phase 5 is tracked as three subphases:
  - `Phase 5.1 - Rich Passive Semantics And Renderer Parity`
  - `Phase 5.2 - Interactive Request/Response Semantics`
  - `Phase 5.3 - Lineage-Aware Actions And Command Semantics`
- Current repo status:
  - `5.1` is in progress with shared renderer and replay support in place and backend live completeness limited to transport-supported passive semantics
  - `5.2` is in progress with execution-native runtime-input lifecycle semantics implemented and approval live parity still runtime-blocked
  - `5.3` has not started

## Positioning
- Phase 5 targets semantic parity on the shared conversation-v2 contract.
- Phase 5 does not target shell parity or pixel parity with CodexMonitor source UI.
- Execution remains the native v2 durable reference path.
- Ask and planning remain normalization-adapter hosts unless a later phase explicitly changes that.
- Host-specific outer framing and submit affordances may continue to differ.
- Planning composer policy remains whatever Phase 4 established unless later work explicitly revisits it.
- No Phase 5 subphase requires shell migration.

## Cross-Subphase Invariants
- Durable conversation state remains the replay source of truth.
- Live event application and durable replay must converge semantically.
- Unsupported, malformed, or partially populated state must degrade safely.
- Host wrappers may differ, but the shared conversation contract must remain consistent.
- `event_seq` remains a reconnect cursor, not the durable replay source of truth.
- Prompt-flushed terminal and workflow state must survive reconnect and restart.
- No Phase 5 subphase requires full ask/planning durable-model convergence.
- No Phase 5 subphase should pull Phase 6 cleanup or performance hardening into its exit criteria.

## Subphase Overview
| Subphase | Status | Purpose | Current Boundary |
| --- | --- | --- | --- |
| `5.1` | In progress | Passive rich semantics plus renderer/replay parity | Shared renderer and replay are in place; backend live completeness is currently limited to `tool_call` and `plan_block` |
| `5.2` | In progress | Interactive request/response lifecycle semantics | Execution runtime-input lifecycle is live + replay complete; `approval_request` is contract-ready but runtime-blocked for live parity |
| `5.3` | Not started | Lineage-aware actions and command semantics | Waiting on stable replay, terminal-state, and fallback-policy decisions |

## Dependencies Between 5.1 / 5.2 / 5.3
- `5.1` establishes passive-part normalization, deterministic attachment, and replay discipline.
- `5.2` builds on that replay discipline for active workflow state, request resolution, and reconnect behavior.
- `5.3` builds on stable replay, stable terminal-state handling, and explicit runtime fallback policy.
- Discovery may overlap across subphases, but:
  - `5.2` should not broaden ownership or lineage rules that belong to `5.3`
  - `5.3` should not exit until `5.1` and `5.2` replay and terminal-state behavior are stable

## Out Of Scope / Non-Goals
- shell migration
- pixel parity with CodexMonitor source UI
- broad host-wrapper redesign
- planning composer enablement
- artifact write-back into breadcrumb artifacts
- Phase 6 cleanup, dense-event optimization, or concurrency hardening work
- unrelated product redesign

## Rollback Boundaries
- Roll back Phase 5 work subphase-by-subphase whenever feasible.
- `5.1` rollback may fall back to safe unsupported rendering for semantics that are not yet supported on the shared surface.
- `5.2` rollback may disable shared interactive rendering and host request-actions while preserving durable historical request state.
- `5.3` rollback may disable lineage-aware actions while preserving `5.1` and `5.2` transcript semantics.
- Partial rollback must not invalidate the stable Phase 3/4 execution, ask, or planning host paths.

## Exit Criteria For The Whole Phase
Phase 5 is complete when:
- passive rich semantics render and replay correctly on the v2 path
- interactive request/response lifecycle state is durable, reconnect-safe, and replay-safe
- lineage-aware actions are durable, replayable, and governed by explicit fallback policy
- mixed text, passive, interactive, and lineage-bearing transcripts remain stable on the shared surface
- unsupported or malformed semantic state never crashes the UI
- no Phase 6 work is required to claim semantic completion

## Phase 5.1 - Rich Passive Semantics And Renderer Parity
### Status
- In progress

### Goal
- Extend the shared surface from the text-first baseline to passive rich semantics whose primary requirement is semantic parity between live delivery and durable replay.

### In Scope
- `reasoning`
- `tool_call`
- `tool_result`
- `plan_block`
- `plan_step_update`
- `diff_summary`
- `file_change_summary`

### Non-Goals
- approvals or runtime-input workflow state
- retry, continue, regenerate, or cancel semantics
- host-wrapper visual parity
- shell-level affordance changes

### Dependencies
- completed Phase 4 host reuse baseline
- stable text-first conversation-v2 contract
- deterministic message and part identity on the shared reducer path

### Current Repo Boundary
- shared passive renderers and durable replay support are in place
- backend live + replay is complete on the current path for:
  - `tool_call`
  - `plan_block`
- backend live-path semantics remain replay-only until native transport support exists for:
  - `reasoning`
  - `tool_result`
  - `plan_step_update`
  - `diff_summary`
  - `file_change_summary`

### Core Rules
- passive events must resolve deterministically to a target message and target part
- passive events attach only to deterministic assistant targets on the current path
- duplicate delivery must be idempotent by stable message identity plus stable part identity
- `tool_result` must preserve stable association to its originating `tool_call`
- `plan_block` converges as one current render item per stable `plan_id`
- replay-only means a semantic may appear through durable snapshot replay or guarded terminal snapshot refresh, but is not required to appear as a fine-grained live event on the current transport path

### Risks
- over-claiming backend live parity when a semantic is replay-only
- passive-event attachment drift when `message_id` is missing
- terminal reconciliation downgrading a richer live-normalized part

### Acceptance Criteria
- passive rich semantics render on the shared surface without unsupported fallback where a renderer exists
- passive events attach only to deterministic assistant targets
- backend live-path claims remain limited to semantics the transport can emit natively and deterministically
- replay-only semantics are explicitly documented as replay-only rather than silently implied as live-complete
- duplicate delivery and reconnect do not duplicate passive render items

### Rollback Note
- unsupported or transport-blocked semantics may fall back to replay-only or unsupported rendering without breaking the text-first baseline

### Open Issues
- `P5-OI-001`

## Phase 5.2 - Interactive Request/Response Semantics
### Status
- In progress

### Goal
- Add durable, reconnect-safe request/response lifecycle semantics to the shared conversation contract without requiring host-wrapper submit parity.

### In Scope
- `approval_request`
- `user_input_request`
- `user_input_response`
- request lifecycle, submit/resolve flow, reconnect, and replay semantics
- `request_resolved`

### Non-Goals
- retry, continue, regenerate, or cancel semantics
- shell migration
- wrapper visual parity
- planning composer changes

### Dependencies
- `5.1` deterministic replay and message/part attachment discipline
- prompt-flush rules already locked in `DECISION_LOG.md`
- stable terminal-state handling on the execution v2 path

### Current Repo Boundary
- interactive request and response semantics render on the shared conversation surface instead of degrading as unsupported content
- execution runtime-input lifecycle semantics are live + replay complete on the current backend path for:
  - `request_user_input`
  - `request_resolved`
  - `user_input_resolved`
- normalized shared parts in use:
  - `user_input_request`
  - `user_input_response`
- `approval_request` is contract-ready and replay-safe, but remains runtime-blocked for live parity while `approvalPolicy: never` remains
- ask and planning only participate where a clean normalized interactive source exists on the v2 path

### Core Rules
- the shared contract exposes at most one active visible unresolved request at a time on the current lineage
- the active visible request is the latest unresolved request in normalized durable message/part order on the currently visible lineage
- historical resolved requests remain replayable but must not reopen as active UI
- durable request state is conversation-owned even when submit controls remain host-owned
- guarded snapshot refresh is recovery only, not the primary lifecycle source

### Risks
- reopening historical requests as active UI after reconnect
- duplicated request ownership between host wrappers and the shared conversation contract
- implying approval live parity even while `approvalPolicy: never` blocks emission

### Acceptance Criteria
- `approval_request`, `user_input_request`, and `user_input_response` render on the shared contract without unsupported fallback
- the active visible request resolves to the latest unresolved request on the currently visible lineage
- execution runtime-input requests and responses persist durably, survive reconnect, and converge between live delivery and replay
- `request_resolved` updates durable lifecycle state without fabricating a separate approval response part
- approval semantics remain contract-ready and replay-safe, with any live-path runtime block documented explicitly

### Rollback Note
- shared request renderers and host request-actions may be disabled while preserving durable historical request state

### Open Issues
- `P5-OI-002`
- `P5-OI-003`

## Phase 5.3 - Lineage-Aware Actions And Command Semantics
### Status
- Not started

### Goal
- Add lineage-aware mutation semantics for `retry`, `continue`, `regenerate`, and `cancel` on top of the stable conversation-v2 contract.

### In Scope
- `retry`
- `continue`
- `regenerate`
- `cancel`
- lineage metadata and supersession semantics required to support those actions
- fallback policy when the runtime cannot provide true rollback or rewind

### Non-Goals
- shell migration
- replay-only passive semantics from `5.1`
- request/response lifecycle ownership from `5.2`
- hidden destructive deletion of superseded transcript history

### Dependencies
- stable replay discipline from `5.1`
- stable request and terminal-state handling from `5.2`
- explicit runtime capability assessment for rollback and rewind support

### Current Repo Boundary
- no lineage-aware actions are implemented yet on the shared conversation-v2 path
- runtime rollback/rewind capability is not yet locked for `retry` and `regenerate`
- cancel semantics are still pending explicit terminalization policy

### Core Rules
- action semantics must be lineage-aware and durable
- superseded answers and branches must remain replayable
- action availability must respect ownership, runtime capability, and terminal-state rules
- `cancel` is an active-operation control semantic, not a branch-creation semantic
- if true rewind is unavailable, fallback policy must be explicit rather than implied

### Risks
- hidden branch loss during replay
- cancel being implemented as pseudo-regenerate
- unclear fallback behavior when runtime rewind is unavailable

### Acceptance Criteria
- durable lineage metadata supports deterministic replay after lineage-changing actions
- retry, continue, regenerate, and cancel obey explicit ownership and terminal-state rules
- superseded branches remain replayable
- fallback policy is explicit when runtime rewind is unavailable

### Rollback Note
- lineage-aware actions may be disabled independently from passive and interactive semantics

### Open Issues
- `P5-OI-004`
- `P5-OI-005`
- `P5-OI-006`
- `P5-OI-007`
