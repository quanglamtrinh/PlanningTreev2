# Phase 1 Payload Before/After Notes

Status: implemented on 2026-03-28.

## Before

Legacy callback surface was narrow:

- `on_delta(str)`
- `on_plan_delta(str, item)`
- `on_tool_call(tool_name, arguments)`
- `on_request_user_input(dict)`
- `on_request_resolved(dict)`
- `on_thread_status(dict)`
- `on_item_event(phase, item)`

Gaps:

- no unified raw-event callback for V2
- no stable raw-event buffering beyond stdout text
- no guaranteed `item_id` surface for all callback consumers
- resolved request payload did not carry both `request_id` and `item_id`

## After

Additive raw callback:

- `on_raw_event(dict)`

Raw event envelope:

```python
{
    "method": str,
    "received_at": str,
    "thread_id": str | None,
    "turn_id": str | None,
    "item_id": str | None,
    "request_id": str | None,
    "call_id": str | None,
    "params": dict[str, Any],
}
```

Behavior changes:

- raw events are buffered before callback attachment and replayed in original observed order for that turn state
- legacy callbacks are now derived from the normalized raw-event dispatch path
- request resolution now emits enriched payloads containing:
  - `request_id`
  - `item_id`
  - `thread_id`
  - `turn_id`
  - `status`
  - `answers`
  - `submitted_at`
  - `resolved_at`
- request and resolved events no longer depend on a preexisting turn state; they materialize or recover state by `turn_id` before buffering
- raw tool-call events retain the original request payload and add normalized helper fields:
  - `tool_name`
  - `arguments`
  - `call_id`
  - `turn_id`
  - `thread_id`
  - `raw_request`

Non-changes:

- legacy callback signatures remain unchanged
- `run_turn_streaming()` return shape remains unchanged
