# Phase 1: Codex Client Event Expansion

Status: completed and verified on 2026-03-28. Phase 0 contract freeze remains the active sequencing phase, but Phase 1 implementation and regression verification are complete.

## Goal

Make upstream event intake lossless enough for the V2 projector so item identity, lifecycle, user-input resolution, and tool/file-change output no longer depend on guessed fields.

## In Scope

- expand `backend/ai/codex_client.py`
- add or expand tests for adapted raw event payloads
- preserve upstream identity fields and lifecycle result fields

## Out of Scope

- snapshot persistence
- frontend reducer changes
- runtime or projector implementation beyond temporary adapters

## Required Changes

- preserve `itemId` for every agent message delta
- expose raw reasoning events with stable identity
- expose command output deltas
- expose file-change output deltas
- expose `turn/completed` outcome details
- expose `serverRequest/resolved` with both `requestId` and `itemId`
- expose raw tool call metadata, including `callId`, tool name, arguments, thread id, and turn id when available

## File Targets

- `backend/ai/codex_client.py`
- related backend tests covering raw event adaptation

## Checklist

- add tests for delta events missing `itemId`
- add tests for `turn/completed` success, waiting-user-input, and failure outcomes
- add tests for `serverRequest/resolved` carrying both identity keys
- add tests for raw tool call metadata capture
- document any upstream gaps that cannot be fixed locally

## Verification

- targeted backend unit tests for adapted event payloads
- fixture replay confirms no projector-critical field is missing
- regression safety suites for chat, finish-task, review, and thread-lineage flows stay green after the adapter changes

Verified green on 2026-03-28:

- `backend/tests/unit/test_codex_client.py`
- `backend/tests/unit/test_codex_client_sandbox.py`
- `backend/tests/unit/test_chat_service.py`
- `backend/tests/unit/test_finish_task_service.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/unit/test_thread_lineage_service.py`

## Exit Criteria

- projector input no longer depends on pair assumptions or guessed identity
- all required raw event classes from Phase 0 are surfaced by `codex_client.py`
- `progress.yaml` updated with verification notes

Exit criteria status:

- satisfied: projector input no longer depends on pair assumptions or guessed identity
- satisfied: all required raw event classes from Phase 0 are surfaced by `codex_client.py`
- satisfied: `progress.yaml` updated with verification notes

## Artifacts To Produce

- `artifacts/phase-1/event-adapter-coverage.md`
- `artifacts/phase-1/payload-before-after.md`

## Implementation Notes

- added additive `on_raw_event` callback support through `CodexTransport`, `StdioTransport`, and `CodexAppClient`
- kept legacy callbacks unchanged and derived them from the same normalized raw-event dispatch path
- added raw-event buffering and replay through `_TurnState.raw_events`
- enriched runtime request resolution so resolved payloads carry both `request_id` and `item_id`
- added targeted unit coverage in `backend/tests/unit/test_codex_client.py`
- post-review hardening landed for request lifecycle edge cases:
  - `item/tool/requestUserInput` now materializes a turn state when needed so early request events are buffered instead of dropped
  - `serverRequest/resolved` now rehydrates the turn state from `record.turn_id` before emitting the enriched resolved payload
  - raw-event replay now drains the buffered queue in order, even if new events arrive while replay is in progress
  - `item/tool/call` raw events now preserve the original request payload alongside normalized convenience fields
- follow-up regression fixes landed outside the transport adapter where Phase 1 exposed coupling:
  - `ChatService.get_session()` now skips bootstrap-on-read while a live turn is still active, avoiding bootstrap races during background failure tests
  - `ThreadLineageService._materialize_thread_rollout()` now runs the rollout bootstrap prompt with `sandbox_profile=\"read_only\"`
  - service test fakes now treat the rollout bootstrap prompt as bootstrap-only setup rather than as the main turn under test
