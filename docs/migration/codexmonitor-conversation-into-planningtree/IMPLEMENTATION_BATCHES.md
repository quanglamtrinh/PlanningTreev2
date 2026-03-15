# Implementation Batches

## Batch Sequencing Rules
- Keep the target runnable after every batch.
- Do not start broad UI migration before Phase 0 artifacts and Phase 1 foundations are in place.
- Do not start Phase 2 before Batch `P1.2` is complete.

## P0.1
- Create the migration docs directory and all required files.
- Write `MASTER_PLAN.md`.
- Populate source audit, target audit, module mapping, dependency map, phase plan, validation checklist, and changelog.
- Blast radius: docs only.

## P1.1
- Define shared backend and frontend conversation types.
- Define phase-1 event schema skeleton.
- Define canonical identity and lineage types.
- Define normalized rich message schema skeleton.
- Blast radius: low, new files only.

## P1.2
- Add keyed frontend conversation store skeleton.
- Add backend conversation persistence contract skeleton.
- Add compatibility adapters from current simple sessions.
- Blast radius: low, additive only.

## P2.1
- Add session manager skeleton.
- Define `RuntimeThreadState` with:
  - `thread_id`
  - `last_used_at`
  - `active_turn_id`
  - `status`
- Define `ProjectCodexSession` with:
  - `project_id`
  - `workspace_root`
  - `client`
  - `loaded_runtime_threads`
  - `active_streams`
  - `active_turns`
  - `runtime_request_registry`
  - `health`
  - `lock`
- Lock project-scoped session identity rules.
- Require all ownership reads and writes under the project session lock.
- Add health and ownership interfaces.
- Blast radius: medium, backend infrastructure only.

## P2.2
- Add execution-only gateway route and service skeleton.
- Add execution-only context builder.
- Add one execution-thread end-to-end stream on the conversation-v2 path.
- Use durable-store-first `GET` snapshots with optional live ownership enrichment.
- Create a stable assistant placeholder message and stable `assistant_text` part at send-start.
- Keep the hot path forward-first and persist-after.
- Persist normalized message updates in parallel with prompt terminal flush behavior.
- Lock send-start `event_seq` allocation to:
  - user `message_created = n + 1`
  - assistant `message_created = n + 2`
- Emit `assistant_text_final` only on the successful path.
- Add a gateway-owned persistence worker with `flush_and_stop()`.
- Validate same-project reuse, cross-project isolation, reconnect safety, stale-stream rejection, and non-execution-eligible send rejection.
- Blast radius: medium, backend runtime path.

## P2.2a
- Add `ConversationStore` grouped mutation helper.
- Add `ConversationEventBroker`.
- Add `ConversationContextBuilder`.
- Add `ConversationGateway.get_execution_conversation`.
- Add `GET /v2/.../conversations/execution`.
- Add unit coverage for canonical snapshot creation and pre-send `GET`.

## P2.2b
- Add `POST /v2/.../conversations/execution/send`.
- Add setup-path seeding for stable user and assistant placeholder messages.
- Add gateway-owned `event_seq` allocation under the project session lock.
- Add stale-callback rejection and terminal flush-before-clear ownership behavior.
- Add unit coverage for placeholder identity, exact send-start sequence allocation, stale-stream rejection, and early-failure cleanup.

## P2.2c
- Add `GET /v2/.../conversations/execution/events`.
- Add reconnect mismatch handling with structured `409 conversation_stream_mismatch`.
- Add worker flush hook coverage and shutdown ordering checks.
- Add integration coverage for `GET -> POST send -> GET again`, successful and errored streaming, same-project reuse, cross-project isolation, same-conversation rejection, and non-execution-eligible rejection.

## Phase 3 Tracking Rule
- For now, `Phase 3.1`, `Phase 3.2`, and `Phase 3.3` map 1:1 to tracked implementation batches.
- If a later sub-batch split is needed, the phase goal and acceptance criteria must remain unchanged.

## P3.1
- Tracks `Phase 3.1 - Execution Conversation Data Plumbing`.
- Non-visible execution-only frontend plumbing on top of the existing v2 backend path.
- Covers snapshot hydration, keyed state, SSE subscription, reconnect model, and send-path wiring.
- Visible execution UI cutover is out of scope.
- Blast radius: medium, frontend data plumbing only.

## P3.2
- Tracks `Phase 3.2 - Shared Conversation Surface Presentation`.
- Presentational shared conversation surface and minimal render contract only.
- Covers user and assistant text rendering, streaming text, loading/error/empty states, and safe unsupported-part degradation.
- Visible execution transcript switch remains out of scope.
- Blast radius: medium, shared presentation layer only.

## P3.3
- Tracks `Phase 3.3 - Execution Tab Visible Cutover`.
- Visible execution-tab cutover and execution-wrapper integration only as needed for that cutover.
- Covers execution host integration while preserving current execution framing and rollback safety.
- Ask, planning, and shell work remain out of scope.
- Blast radius: medium, execution tab host integration only.

## P4.1
- Embed the shared surface in ask thread.
- Preserve ask packet sidecar behavior.
- Blast radius: medium, ask UI only.

## P4.2
- Embed the shared surface in planning thread.
- Preserve planning split wrappers and framing.
- Blast radius: medium, planning UI only.

## P5.1
- Add reasoning, tool, result, and plan block rendering.
- Blast radius: medium, shared renderer and adapters.

## P5.2
- Add approvals, runtime input, diff summaries, file summaries, and lineage-aware controls.
- Blast radius: medium to high, shared renderer and command layer.

## P6.1
- Harden latency, dense-event rendering, concurrency, replay, and reconnect behavior.
- Blast radius: medium, optimization and stabilization.

## P6.2
- Remove compatibility layers only after cleanup gates pass.
- Finalize docs and changelog.
- Blast radius: medium, cleanup only.
