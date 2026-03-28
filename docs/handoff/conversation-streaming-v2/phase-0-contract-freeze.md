# Phase 0: Contract Freeze and Fixture Capture

Status: in progress. Started on 2026-03-28.

## Goal

Freeze the V2 conversation contract before implementation starts so backend and frontend can build against the same schema, patch rules, lifecycle rules, and event payloads.

## In Scope

- finalize `ConversationItem` and `ThreadSnapshotV2`
- finalize `ItemPatch`
- finalize REST and SSE payloads
- finalize metadata synchronization rules
- finalize raw event mapping rules
- capture raw upstream fixtures for every required event class

## Out of Scope

- production code changes beyond fixture capture and low-risk instrumentation
- frontend reducer implementation
- backend projector implementation

## Required Inputs

- `docs/specs/conversation-streaming-v2.md`
- current raw event behavior from `backend/ai/codex_client.py`
- example sessions from `chat_service.py`, `review_service.py`, and `finish_task_service.py`

## Checklist

- review every item kind and confirm required vs optional fields
- confirm patch semantics for append vs replace fields
- confirm exact payloads for `thread.snapshot`, `conversation.item.upsert`, `conversation.item.patch`, `thread.lifecycle`, `conversation.request.user_input.requested`, `conversation.request.user_input.resolved`, `thread.error`, and `thread.reset`
- confirm public `GET /threads/{role}` remains ensure-and-read
- confirm `turn/completed` lifecycle mapping policy
- confirm `fileChange` authoritative final list rule uses `outputFilesReplace`
- capture fixtures for:
  - agent message start, delta, completed
  - plan start, delta, completed
  - reasoning events
  - command execution start, output delta, completed
  - file change start, delta, completed
  - user input requested and resolved
  - thread status changed
  - turn completed

## Expected Code Touches

- docs only, plus optional temporary instrumentation in `backend/ai/codex_client.py`

## Verification

- reviewer sign-off on the active spec
- fixture manifest exists under `artifacts/phase-0/`
- no unresolved field ambiguity remains for backend projector or frontend reducer

## Exit Criteria

- sections covering schema, patch contract, API contract, lifecycle, and raw mapping are frozen in the active spec
- fixture corpus exists for every event class listed above
- `progress.yaml` updated to move Phase 0 to completed

## Artifacts To Produce

- `artifacts/phase-0/fixture-manifest.md`
- `artifacts/phase-0/raw-event-samples.jsonl`
- `artifacts/phase-0/contract-review-checklist.md`
- optional `artifacts/phase-0/open-questions.md` if any unresolved upstream gaps remain

## Phase Start Notes

- starter artifact templates have been created under `artifacts/phase-0/`
- the next concrete step is to replace placeholder payloads in `raw-event-samples.jsonl` with captured upstream frames from `backend/ai/codex_client.py`
