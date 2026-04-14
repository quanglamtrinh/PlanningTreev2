# Phase 03 Coalescing Rules Freeze v1

Status: Frozen for Phase 03 implementation.

Last updated: 2026-04-12.

Owner: backend conversation runtime maintainers.

## Purpose

Freeze deterministic backend-owned compaction and no-op suppression behavior for:

- A01 (delta coalescing window)
- A04 (item-level patch compaction)
- A08 (no-op lifecycle/event suppression)

This document is the source of truth for implementation and tests in Phase 03.

## Authority and Contract Alignment

Decision source:

- `docs/render/decision-pack-v1.md`

Contract sources:

- `docs/render/system-freeze/contracts/c1-event-stream-contract-v1.md`
- `docs/render/system-freeze/contracts/c3-lifecycle-gating-contract-v1.md`
- `docs/render/system-freeze/contracts/c4-durability-contract-v1.md`

## Balanced Policy (approved profile)

Default runtime policy:

- `window_ms = 50`
- allowed range: `40 <= window_ms <= 60`
- `max_batch_size = 64`

Boundary flush rules (flush immediately, do not wait for timer):

- `item/completed`
- `turn/completed`
- `item/tool/requestUserInput`
- `serverRequest/resolved`
- any lifecycle/raw event that can terminate or gate the turn

Safety fallback:

- if timer/scheduler path fails, flush immediately and continue without dropping events

## Compaction Scope

Compaction applies only to merge-safe raw delta methods in the same thread turn window.

Merge-safe methods:

- `item/agentMessage/delta`
- `item/plan/delta`
- `item/reasoning/summaryDelta`
- `item/reasoning/detailDelta`
- `item/commandExecution/outputDelta`
- `item/fileChange/outputDelta`

Compaction key (all must match):

- `thread_id`
- `turn_id`
- `item_id`
- `method`

Non-mergeable methods (always pass-through in order):

- `item/started`
- `item/completed`
- `item/commandExecution/terminalInteraction`
- `item/tool/requestUserInput`
- `serverRequest/resolved`
- `thread/status/changed`
- `turn/completed`

## Deterministic Merge Rules

### R1. Text-delta concatenation

For merge-safe methods that use `params.delta`:

- concatenate in arrival order
- preserve exact byte order of deltas
- do not trim or normalize whitespace

### R2. File-change metadata append

For `item/fileChange/outputDelta`:

- merge `params.delta` by ordered concatenation
- merge `params.files` by stable append
- do not deduplicate or reorder file entries in Phase 03

### R3. Cross-method isolation

Never merge across different `method` values, even if `item_id` matches.

### R4. Turn isolation

Never merge across different `turn_id` values.

### R5. Item isolation

Never merge across different `item_id` values.

## No-op Suppression Rules (A08)

Suppress only when semantics are unchanged and no consumer-visible side effect is lost.

### S1. Lifecycle no-op suppression

For `thread.lifecycle.v3`, suppress publication if this tuple is unchanged:

- `state`
- `processingState`
- `activeTurnId`
- `detail`

### S2. Terminal duplicate suppression

If a terminal lifecycle event has already been emitted for the same turn with equivalent tuple, suppress duplicate emission.

### S3. Never suppress these event types

Even if payload appears similar, never suppress:

- `thread.snapshot.v3`
- `conversation.item.upsert.v3`
- `conversation.item.patch.v3`
- `conversation.ui.user_input.v3`
- `conversation.ui.plan_ready.v3`
- `thread.error.v3`

## Ordering and Cursor Guarantees (must hold)

1. Event ordering seen by frontend remains monotonic by canonical `event_id`.
2. Compaction must not introduce non-monotonic publish order.
3. Replay contract remains unchanged:
   - replay uses `event_id > last_event_id`
   - header/query cursor precedence is unchanged
   - replay/live handoff dedupe behavior is unchanged
4. Control-frame rules remain unchanged:
   - control events are non-replayable
   - heartbeat does not advance cursor

## Forbidden Behaviors

- frontend semantic compaction ownership
- broad suppression of non-lifecycle business events
- merging events that cross turn boundaries
- implicit reorder during merge
- any compaction path that can emit partial order inversion

## Required Test Evidence

Phase 03 implementation must include:

1. Merge matrix unit tests from `coalescing-rules-matrix-v1.json`.
2. Golden equivalence tests proving same final snapshot vs non-compacted baseline.
3. Lifecycle no-op suppression tests for S1/S2.
4. Reconnect/replay regression tests confirming unchanged C1/C2 behavior.

## Machine-Readable Companion Artifacts

- `coalescing-rules-matrix-v1.json`
- `fixtures/phase03-coalescing-cases-v1.json`

