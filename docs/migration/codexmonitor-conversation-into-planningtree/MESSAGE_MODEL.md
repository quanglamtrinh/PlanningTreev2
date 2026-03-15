# Message Model

## Durable Truth Model
- Persist normalized rich messages as the durable conversation record.
- Persist conversation metadata, lineage metadata, and reconnect cursor metadata alongside messages.
- Raw stream events are not the storage of truth.
- `event_seq` exists for reconnect and live continuation only.

## Canonical Durable Entities
### ConversationRecord
- `conversation_id`
- `project_id`
- `node_id`
- `thread_type`
- `app_server_thread_id`
- `current_runtime_mode`
- `status`
- `active_stream_id`
- `event_seq`
- `created_at`
- `updated_at`

### ConversationMessage
- `message_id`
- `conversation_id`
- `turn_id`
- `role`
- `runtime_mode`
- `status`
- `created_at`
- `updated_at`
- `lineage`
- `usage`
- `error`
- `parts`

### MessagePart
- `part_id`
- `part_type`
- `status`
- `order`
- `item_key`
- `created_at`
- `updated_at`
- `payload`

## Required Part Types
- `assistant_text`
- `reasoning`
- `tool_call`
- `tool_result`
- `plan_block`
- `plan_step_update`
- `approval_request`
- `user_input_request`
- `user_input_response`
- `diff_summary`
- `file_change_summary`
- `status_block`

## Compatibility Story
- Current PlanningTree simple `ChatMessage[]` arrays are transitional input formats only.
- Compatibility adapters may read current simple sessions during migration.
- New-path durable writes must target the normalized rich model.

## Ordering And Merge Rules
- Only the active `stream_id` may mutate the active turn for a conversation.
- Stale stream events are ignored once a stream is cancelled, superseded, or replaced.
- Assistant text deltas append to the active `assistant_text` part.
- Tool, reasoning, plan, approval, and runtime-input parts update by stable upstream identity when available.
- If no stable upstream identity exists, append by deterministic normalized part order.
- `message_id` upserts by exact identity.
- `turn_id` groups parts and lineage for one logical turn.
- Persisted ordering follows normalized message and part order, not raw transport arrival order when conflicts occur.

## Replay And Rebuild Requirements
- Replay after reload rebuilds from normalized rich messages.
- Replay must restore:
  - assistant text blocks
  - reasoning UI
  - tool and result cards
  - plan blocks and step status
  - approval and runtime input states
  - diff and file summaries
  - superseded and lineage-aware actions

## Lineage Model
- `cancel` does not create a new lineage node.
- `continue` creates a continuation node on the same conversation lineage.
- `retry` creates a branch linked to the prior user turn.
- `regenerate` creates a superseding assistant node and preserves the superseded answer.

## Raw Event To Message-Part Mapping
- `assistant_text_delta` -> append to `assistant_text`
- `assistant_text_final` -> finalize `assistant_text` and update message status
- `reasoning_state` -> create or update `reasoning`
- `tool_call_start/update/finish` -> create or update `tool_call`
- `tool_result` -> create `tool_result`
- `plan_block` -> create or replace `plan_block`
- `plan_step_status_change` -> create or update `plan_step_update`
- `approval_request` -> create `approval_request`
- `request_user_input` -> create `user_input_request`
- `user_input_resolved` -> create `user_input_response`
- `diff_summary` -> create `diff_summary`
- `file_change_summary` -> create `file_change_summary`
- `completion_status` -> create or update `status_block`
