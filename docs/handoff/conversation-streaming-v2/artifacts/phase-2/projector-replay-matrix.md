# Phase 2 Projector Replay Matrix

Status: completed. The Phase 0 corpus now contains adapter-captured `on_raw_event` payloads from a fixed `StdioTransport` harness, and the replay suite confirms deterministic projector behavior against that corpus with no spec drift observed.

## Corpus Source

- fixture file: `docs/handoff/conversation-streaming-v2/artifacts/phase-0/raw-event-samples.jsonl`
- capture mode: adapter-captured raw envelopes emitted by `backend/ai/codex_client.py`
- replay verification: `backend/tests/unit/test_conversation_v2_fixture_replay.py`

## Replay Results

| Raw event class | Fixture source | Expected projector behavior | Replay status | Final snapshot result | Spec drift |
| --- | --- | --- | --- | --- | --- |
| `item/agentMessage/delta` | `raw-event-samples.jsonl` (`agent_message_delta`) | patch assistant `message.text` by `itemId` | pass | `msg-1` text becomes `hello` and completes after terminal event | none |
| `item/plan/delta` | `raw-event-samples.jsonl` (`plan_delta`) | patch `plan.text`; replace steps only if structured steps exist | pass | `plan-1` text becomes `step 1` and completes | none |
| `item/reasoning/*` | `raw-event-samples.jsonl` (`reasoning_event`) | upsert or patch canonical `reasoning` item by stable identity | pass | `reason-1` summary text becomes `think` with stable id reuse | none |
| `item/commandExecution/outputDelta` | `raw-event-samples.jsonl` (`command_output_delta`) | append command output text on canonical `tool` item | pass | `cmd-1` output text becomes `stdout`, exit code preserved on completion | none |
| `item/fileChange/outputDelta` | `raw-event-samples.jsonl` (`file_change_delta`) | append preview output text and preview files | pass | preview file list is later overwritten by authoritative `outputFilesReplace` from completed payload | none |
| `item/tool/requestUserInput` | `raw-event-samples.jsonl` (`user_input_requested`) | upsert canonical `userInput` item and pending request entry | pass | `input-1` item and pending request `55` are created with requested state | none |
| `serverRequest/resolved` | `raw-event-samples.jsonl` (`user_input_resolved`) | patch `userInput` by `itemId` and ledger by `requestId` | pass | item and pending request both end in `answered` with normalized answers list | none |
| `thread/status/changed` | `raw-event-samples.jsonl` (`thread_status_changed`) | emit lifecycle change and optional user-visible status item | pass | thread processing state moves to `running` before terminal completion | none |
| `turn/completed` success | `raw-event-samples.jsonl` (`turn_completed_success`) | map to terminal success lifecycle | pass | thread ends `idle` with `activeTurnId = null` and `turn_completed` lifecycle | none |
| `turn/completed` waiting user input | `raw-event-samples.jsonl` (`turn_completed_waiting_user_input`) | map to waiting-user-input lifecycle | pass | thread ends `waiting_user_input` with `activeTurnId = turn_1` | none |
| `turn/completed` failed or interrupted | `raw-event-samples.jsonl` (`turn_completed_failed`) | map interrupted failure to terminal failure lifecycle | pass | thread ends `idle` with `turn_failed` lifecycle | none |

## Additional Observations

- `item/tool/call` is present in the Phase 0 corpus as a captured provisional-enrichment payload; the pure projector intentionally leaves canonical snapshot state unchanged for that event because provisional tool handling lives in runtime orchestration rather than direct projector mutation.
- No replayed payload required a spec adjustment. The active V2 schema, patch contract, API contract, and lifecycle rules remain aligned with the adapter-captured corpus.
