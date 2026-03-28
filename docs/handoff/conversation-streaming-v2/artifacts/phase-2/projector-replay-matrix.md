# Phase 2 Projector Replay Matrix

Status: pending fixture-driven completion.

## Implemented Coverage

- unit coverage exists for missing-item patch mismatch
- unit coverage exists for `outputFilesReplace` overriding preview `outputFilesAppend`
- integration coverage exists for:
  - first-frame `thread.snapshot`
  - start-turn persistence through `/v2`
  - wrapped `conversation_stream_mismatch` response on invalid `after_snapshot_version`
  - user-input resolve path through `/v2`

## Remaining Fixture Replay Work

- replay Phase 0 captured raw payloads from `artifacts/phase-0/raw-event-samples.jsonl`
- confirm deterministic final snapshots for:
  - `item/agentMessage/delta`
  - `item/plan/delta`
  - `item/reasoning/*`
  - `item/commandExecution/outputDelta`
  - `item/fileChange/outputDelta`
  - `item/tool/requestUserInput`
  - `serverRequest/resolved`
  - `thread/status/changed`
  - `turn/completed`
- record any spec drift before marking Phase 2 completed

