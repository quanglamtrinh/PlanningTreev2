# Phase 1: Codex Client Event Expansion

Status: not started.

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

## Exit Criteria

- projector input no longer depends on pair assumptions or guessed identity
- all required raw event classes from Phase 0 are surfaced by `codex_client.py`
- `progress.yaml` updated with verification notes

## Artifacts To Produce

- `artifacts/phase-1/event-adapter-coverage.md`
- `artifacts/phase-1/payload-before-after.md`
