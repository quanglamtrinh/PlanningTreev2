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
- Validate same-project reuse, cross-project isolation, reconnect safety, stale-stream rejection, and non-execution-eligible send rejection.
- Blast radius: medium, backend runtime path.

## P3.1
- Embed the shared conversation surface into execution thread.
- Support basic assistant text streaming first.
- Preserve rollback path to the old execution flow.
- Blast radius: medium, execution UI only.

## P3.2
- Load execution history from normalized rich messages.
- Replay from durable conversation records after reload.
- Blast radius: medium, execution UI and load path.

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
