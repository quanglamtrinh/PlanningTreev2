# Phase 1 Event Adapter Coverage

Status: implemented on 2026-03-28.

## Landed

- additive `on_raw_event` callback on:
  - `CodexTransport.send_prompt_streaming(...)`
  - `StdioTransport.send_prompt_streaming(...)`
  - `StdioTransport._send_prompt_modern(...)`
  - `StdioTransport._run_turn_streaming_unlocked(...)`
  - `CodexAppClient.send_prompt_streaming(...)`
  - `CodexAppClient.run_turn_streaming(...)`
- normalized raw event envelope with:
  - `method`
  - `received_at`
  - `thread_id`
  - `turn_id`
  - `item_id`
  - `request_id`
  - `call_id`
  - `params`
- early-event buffering and replay through `_TurnState.raw_events`
- user-input resolve enrichment with `item_id`, `answers`, `submitted_at`, and `resolved_at`

## Verified Raw Event Coverage

- `thread/status/changed`
- `item/agentMessage/delta`
- `item/plan/delta`
- `item/started`
- `item/completed`
- `turn/completed`
- `serverRequest/resolved`
- `error`
- `item/reasoning/*`
- `item/commandExecution/outputDelta`
- `item/commandExecution/terminalInteraction`
- `item/fileChange/outputDelta`
- `item/tool/requestUserInput`
- `item/tool/call`

## Verification

Passed:

- `backend/tests/unit/test_codex_client.py`
- `backend/tests/unit/test_codex_client_sandbox.py`
- `backend/tests/unit/test_chat_service.py`
- `backend/tests/unit/test_finish_task_service.py`
- `backend/tests/unit/test_review_service.py`
- `backend/tests/unit/test_thread_lineage_service.py`

Additional hardening verified:

- `item/tool/requestUserInput` buffers correctly even when it is the first turn-scoped event and no turn state exists yet
- `serverRequest/resolved` emits the enriched payload through the recovered turn state instead of requiring a preexisting attached state
- buffered raw events preserve observed order when a new live event arrives during replay
- raw `item/tool/call` payloads keep original request fields while also exposing normalized `tool_name`, `arguments`, and `call_id`

Notes:

- the first regression sample exposed two real integration gaps and one fixture-coupling issue:
  - bootstrap-on-read during active chat turns
  - rollout bootstrap missing `read_only` sandbox profile
  - fake service clients treating the rollout bootstrap prompt as if it were the main turn under test
- those follow-ups were fixed and the broader regression sample is now green
