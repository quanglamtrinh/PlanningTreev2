# PTM Render Optimization - Comprehensive Guide

Status: Baseline architecture and optimization backlog.

Last updated: 2026-04-11.

---

## 1. Document goal

This document is designed to:

1. Explain in detail why thread execution/ask rendering currently takes too long.
2. Compare PTM patterns with CodexMonitor and Goose.
3. List all meaningful improvement opportunities by system layer.
4. Provide clear before/after workflows for implementation.
5. Create a scoring framework so priorities can be chosen later.

---

## 2. Core problem (quick explanation)

Most chat/render latency follows this formula:

`Total latency = Event volume x (Backend apply cost + Persist cost + Frontend apply cost + Render cost)`

If a streamed turn produces many tiny deltas, and each delta runs through a full pipeline, total cost grows quickly.

### Simple example

Assume one response streams as 300 tiny deltas:

1. Backend handles 300 updates.
2. Store/stream publishes 300 updates.
3. Frontend applies state 300 times.
4. Feed re-renders repeatedly.

Result: visible UI jank, higher latency, and higher CPU.

---

## 3. Current PTM bottleneck map

### 3.1 Backend event/projection path

PTM currently tends to process raw events one by one:

- `thread_runtime_service_v3.py`:
  - calls `get_thread_snapshot(...)`
  - calls `apply_raw_event_v3(...)`
  - calls `persist_thread_mutation(...)`

Reference files:

- `backend/conversation/services/thread_runtime_service_v3.py`
- `backend/conversation/projector/thread_event_projector_runtime_v3.py`
- `backend/conversation/services/thread_query_service_v3.py`

Risk:

- many reads/writes per delta
- lock contention
- frequent snapshot writes in hot path

### 3.2 Persist path

- V3 snapshots are written via `atomic_write_json(...)`.
- Reference:
  - `backend/conversation/storage/thread_snapshot_store_v3.py`

Risk:

- high write amplification under heavy streaming
- serialization and file I/O in critical path

### 3.3 SSE path

- PTM has SSE route + heartbeat.
- It does not yet match Goose-level replay robustness with `Last-Event-ID` buffering.
- Reference:
  - `backend/routes/workflow_v3.py`
  - `backend/streaming/sse_broker.py`

Risk:

- slow subscribers can miss events
- reconnect can cause larger-than-needed reload behavior

### 3.4 Frontend state apply path

- `threadByIdStoreV3.ts` applies incoming events continuously.
- `applyThreadEventV3.ts` includes item patching and sorting behavior.
- Reference:
  - `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
  - `frontend/src/features/conversation/state/applyThreadEventV3.ts`

Risk:

- state churn
- broad invalidation in UI

### 3.5 Render path

- `MessagesV3.tsx` computes visible/grouped state and maps full feed render.
- Heavy rows include markdown, diff parse, and highlight.
- Reference:
  - `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
  - `frontend/src/features/conversation/components/FileChangeToolRow.tsx`
  - `frontend/src/features/conversation/components/ConversationMarkdown.tsx`

Risk:

- high main-thread cost
- worse behavior on long threads and large diffs

---

## 4. Comparison with CodexMonitor and Goose

### 4.1 CodexMonitor (key lessons)

1. Reducer split by slices with narrower actions:
   - `src/features/threads/hooks/useThreadsReducer.ts`
   - `src/features/threads/hooks/threadReducer/*`
2. Extensive `memo` usage for message rows:
   - `src/features/messages/components/MessageRows.tsx`
3. Data volume controls:
   - scrollback caps (`src/utils/chatScrollback.ts`)
   - normalize/truncate (`src/utils/threadItems.explore.ts`)
4. Queue send while thread is processing:
   - `src/features/threads/hooks/useQueuedSend.ts`
5. Centralized event hub:
   - `src/services/events.ts`

Why it matters:

- lower rerender fanout
- smaller active state volume
- more stable UX during heavy event streams

### 4.2 Goose (key lessons)

1. Robust SSE:
   - replay buffer + sequence IDs + `Last-Event-ID`
   - lagged subscriber handling via reconnect + replay
   - `crates/goose-server/src/session_event_bus.rs`
   - `crates/goose-server/src/routes/session_events.rs`
2. Text chunk coalescing in storage:
   - avoid one row per token
   - `crates/goose/src/session/thread_manager.rs`
3. Progressive list rendering:
   - `ui/desktop/src/components/ProgressiveMessageList.tsx`
4. Markdown/code path performance tuning:
   - memoized code block
   - `ui/desktop/src/components/MarkdownContent.tsx`
5. Streaming markdown safety buffer:
   - flush only at markdown-safe boundaries
   - `crates/goose-cli/src/session/streaming_buffer.rs`

Why it matters:

- lower event churn
- stronger reconnect correctness
- smoother UX on long sessions

---

## 5. Full optimization catalog

This is the complete backlog for later prioritization. Each item includes:

- current issue
- optimization direction
- before/after workflow idea
- key metric
- risk notes

## Layer A - Backend ingest, projection, persistence

### A01. Delta coalescing window (30-100ms)

- Issue: every tiny delta runs full pipeline.
- Improve: coalesce by `thread_id + item_id + kind` in short windows.
- Before: 300 deltas -> 300 apply/persist.
- After: 300 deltas -> 20-40 apply/persist batches.
- Metric: `events_in`, `events_persisted`, `persist_calls_per_turn`.
- Risk: slight added latency (tens of ms), requires tuning.

### A02. In-memory thread actor

- Issue: repeated snapshot reads on hot path.
- Improve: keep live thread state in memory; patch there first.
- Before: read snapshot each event.
- After: read on bind; patch in memory; checkpoint by policy.
- Metric: `snapshot_reads_per_turn`, lock wait duration.
- Risk: requires eviction + recovery logic.

### A03. Checkpoint by boundary, not per event

- Issue: snapshot write frequency too high.
- Improve: checkpoint by timer and turn boundaries (`turn_completed`, `turn_failed`, `waiting_user_input`).
- Metric: `snapshot_writes_per_minute`, write bytes.
- Risk: recovery design must remain safe.

### A04. Item-level patch compaction

- Issue: many consecutive patches hit same item.
- Improve: merge append patches before persist/publish.
- Metric: `patches_in` vs `patches_out`.
- Risk: must preserve sequence correctness.

### A05. Hybrid persistence (event log + periodic snapshot)

- Issue: full snapshot rewrite per mutation is expensive.
- Improve: append-only event log with periodic compact snapshots.
- Metric: write amplification ratio.
- Risk: needs compaction and recovery path.

### A06. Reduce expensive deep-copy in broker

- Issue: deep-copy per subscriber increases CPU.
- Improve: immutable payload sharing or one-time serialization.
- Metric: broker publish CPU and allocation rate.
- Risk: must avoid mutable shared-state bugs.

### A07. Bounded queue + explicit backpressure

- Issue: unbounded queue behavior under load.
- Improve: max queue depth + clear strategy (`drop`, `close+replay`, `slow consumer`).
- Metric: queue depth p95/p99, lag incidents.
- Risk: reconnect contract must be explicit.

### A08. No-op lifecycle/event suppression

- Issue: identical state transitions still publish.
- Improve: dedupe no-op transitions before publish.
- Metric: no-op suppression count.
- Risk: do not suppress events with real side effects.

---

## Layer B - SSE reliability and reconnect

### B01. SSE event IDs + replay cursor

- Improve: all business events carry stable `id`, client tracks `last_event_id`.
- Metric: reconnect success rate without full reload.

### B02. Server replay buffer

- Improve: keep recent event history for replay.
- Before: reconnect often falls back to full snapshot reload.
- After: replay only missing range.
- Metric: full reload fallback count.

### B03. Gap detection with controlled resync

- Improve: if requested ID is outside replay window, return explicit mismatch path.
- Metric: replay gap count and recovery latency.

### B04. Heartbeat policy hygiene

- Improve: heartbeat does not pollute replay/event cursor semantics.
- Metric: false disconnect rate.

### B05. Retry policy tuning

- Improve: exponential backoff + jitter + caps.
- Metric: reconnect storm count, reconnect latency.

### B06. First meaningful frame optimization

- Improve: send critical stream metadata early (active request IDs, status).
- Metric: time-to-first-meaningful-frame.

---

## Layer C - Frontend state pipeline

### C01. Frame-batched event apply (RAF batching)

- Issue: immediate apply per event causes render thrash.
- Improve: queue and apply in animation-frame batches.
- Before: burst of 30 events -> 30 applies.
- After: burst of 30 events -> 1-3 applies.
- Metric: `apply_calls_per_second`, long tasks.

### C02. Normalized conversation state

- Improve: move toward `itemsById + order + uiSignals`.
- Metric: allocations per event, apply duration.

### C03. Remove sort on patch hot path

- Issue: patch updates still pay list sort cost.
- Improve: sort only on insert/order change.
- Metric: patch apply p95/p99.

### C04. Strong structural sharing

- Improve: avoid new objects when values do not change.
- Metric: rerender count per event.

### C05. Split store concerns

- Improve: separate conversation snapshot from telemetry/transport/UI controls.
- Metric: invalidation fanout.

### C06. Narrow selectors

- Improve: subscribe components only to required slices.
- Metric: component updates per event.

### C07. Fast-path text append

- Improve: direct item slot append semantics for streaming text.
- Metric: event apply duration p95.

### C08. Smarter fallback reload policy

- Improve: only force reload for true stream mismatch/corruption.
- Metric: forced snapshot reload count.

---

## Layer D - Render and component performance

### D01. Memoize all V3 row components

- Issue: V3 row functions are not fully isolated from feed rerenders.
- Improve: `React.memo` + stable props.
- Metric: row rerender count.

### D02. Stable callback/prop identity

- Improve: avoid recreating heavy callbacks/objects each render.
- Metric: memo hit rate.

### D03. Progressive rendering for long history

- Improve: batch row mount for large threads.
- Metric: time-to-interactive when opening long thread.

### D04. Virtualization for very long feeds

- Improve: render viewport + overscan only.
- Metric: DOM node count, scroll FPS.

### D05. Lazy markdown rendering

- Improve: defer markdown parse for offscreen/collapsed rows.
- Metric: markdown parse time total.

### D06. Workerized diff parse/highlight

- Improve: move expensive parse/highlight off main thread.
- Metric: main-thread blocking time.

### D07. Incremental command output tail

- Improve: avoid full split/recompute on each output append.
- Metric: command row update cost p95.

### D08. Default-collapse heavy rows

- Improve: collapse large tool/diff rows by default.
- Metric: initial render duration.

### D09. Render budget guard

- Improve: dynamically degrade work if frame budget is exceeded.
- Metric: dropped frames.

### D10. Cache by `itemId + updatedAt`

- Improve: deterministic cache key for parse-heavy artifacts.
- Metric: cache hit ratio.

---

## Layer E - Data volume and UX flow

### E01. V3 conversation scrollback cap

- Issue: active in-memory item list can grow indefinitely.
- Improve: cap live list (e.g. 500/1000/2000) with load-more/archive path.
- Metric: heap size by active thread.

### E02. Large payload truncation policy

- Improve: preview + full artifact for very large outputs/diffs.
- Metric: max render-path payload size.

### E03. Coalesce consecutive assistant text chunks

- Improve: merge neighboring text chunks pre-storage (Goose pattern).
- Metric: rows created per turn.

### E04. Queue follow-up messages while processing

- Improve: enqueue when active turn is running.
- Metric: send failure during processing.

### E05. Queue pause on gated states

- Improve: pause flush during user-input/plan-ready waits; resume safely.
- Metric: accidental sends during gated phases.

### E06. Queue UX controls

- Improve: reorder, remove, send-now controls for clearer user intent.
- Metric: queue completion latency and manual interventions.

---

## Layer F - Observability, profiling, and tests

### F01. Stage timing spans

Capture timing for:

- backend ingest
- projection apply
- persist
- SSE publish
- frontend event apply
- React commit

Metric: p50/p95/p99 by stage.

### F02. Event-volume metrics

Track:

- raw events in
- compacted events out
- deduped/dropped events

### F03. Queue/lag metrics

Track:

- queue depth
- lagged subscriber count
- reconnect count

### F04. Render health metrics

Track:

- commit duration
- rows rendered per event
- long task count

### F05. Synthetic load scenarios

Add repeatable scenarios:

- 500 events
- 2000 events
- large diff
- large markdown

### F06. Replay/reconnect integration tests

Test:

- disconnect mid-turn
- reconnect with `Last-Event-ID`
- replay gap behavior

### F07. CI performance budgets

Set gates for:

- max apply p95
- max render p95
- max forced reload count

### F08. Regression dashboard

Release-over-release dashboard:

- stream health
- render health
- user-perceived latency

---

## Layer G - Rollout and safety

### G01. Feature flags per layer

Flags for:

- backend coalescing
- SSE replay
- frontend frame batching
- progressive render/virtualization

### G02. Canary rollout

Enable by project/workspace cohort and compare control vs treatment metrics.

### G03. Fallback strategy

If an optimization fails:

- disable layer-specific flag
- revert to previous behavior
- keep stream alive

### G04. Migration safety

If persistence model changes:

- dual-write transition period
- parity verification before cutover

### G05. Contract freeze for event schemas

Freeze schemas before large pipeline optimization; enforce producer/consumer contract tests.

### G06. Incident runbook

Runbooks for:

- stream lag
- queue overflow
- reconnect storms
- render freeze

---

## 6. Workflow examples (before/after)

### Example 1 - Streaming text append

Before:

1. Delta arrives.
2. Backend reads snapshot.
3. Backend patches.
4. Backend persists full snapshot.
5. Backend publishes event.
6. Frontend applies and re-renders broadly.

After (A01 + A02 + C01 + D01):

1. Delta enters 50ms coalescing buffer.
2. Batch patch applies to in-memory actor.
3. Checkpoint policy handles persistence.
4. Compact event is published.
5. Frontend applies events per frame.
6. Only the changed row re-renders.

### Example 2 - Network disconnect mid-stream

Before:

1. Client disconnects.
2. Reconnect may force larger snapshot reload.

After (B01 + B02 + B03):

1. Client reconnects with `Last-Event-ID`.
2. Server replays missing events.
3. If replay window is exceeded, server returns explicit mismatch and targeted resync path.

### Example 3 - Opening a 2000-message thread

Before:

1. UI mounts all rows immediately.
2. Main thread blocks.
3. Input and scrolling feel slow.

After (D03 + D04):

1. Progressive row mount in batches.
2. Virtualized offscreen rows.
3. Faster interactivity and smoother scroll.

### Example 4 - Large diff output

Before:

1. Diff parse/highlight runs on main thread.
2. Repeated updates trigger repeated heavy compute.

After (D06 + D10 + E02):

1. Heavy parse runs in worker.
2. Parse results cached by `itemId + updatedAt`.
3. UI shows preview and links to full artifact.

### Example 5 - User sends follow-up while active turn is running

Before:

1. Follow-up sends can race with active processing.

After (E04 + E05 + E06):

1. Follow-up is queued.
2. Queue pauses during gated states.
3. Queue resumes and flushes safely.

---

## 7. Metrics framework

### 7.1 Backend metrics

- `raw_events_per_turn`
- `compacted_events_per_turn`
- `snapshot_reads_per_turn`
- `snapshot_writes_per_turn`
- `persist_duration_ms_p95`
- `broker_publish_duration_ms_p95`

### 7.2 Transport/SSE metrics

- `sse_reconnect_count`
- `replay_events_count`
- `replay_miss_count`
- `lagged_subscriber_count`
- `full_reload_fallback_count`

### 7.3 Frontend state metrics

- `event_apply_duration_ms_p95`
- `state_alloc_bytes_per_sec`
- `forced_snapshot_reload_count`

### 7.4 Render metrics

- `render_commit_duration_ms_p95`
- `rows_rendered_per_event`
- `long_task_count`
- `scroll_fps_p50_p95`

### 7.5 UX metrics

- `time_to_first_interactive_thread_ms`
- `time_to_first_delta_visible_ms`
- `queue_wait_ms`

---

## 8. High-level dependency graph

1. Start with observability (`F01-F04`) to establish baseline.
2. Add stream reliability (`B01-B03`) to reduce expensive fallback reloads.
3. Reduce backend load (`A01-A04`) and frontend apply churn (`C01-C04`).
4. Improve rendering (`D01-D05`) for long-thread user experience.
5. Harden heavy-payload cases (`D06-D07`, `E01-E03`).

---

## 9. Prioritization template (for later filtering)

Use this scoring model:

`PriorityScore = (Impact x Confidence) / (Effort + Risk + RolloutComplexity)`

Suggested scale:

- Impact: 1-5
- Confidence: 1-5
- Effort: 1-5
- Risk: 1-5
- RolloutComplexity: 1-5

Template table:

| ID | Impact | Confidence | Effort | Risk | RolloutComplexity | Score | Owner | Notes |
|---|---:|---:|---:|---:|---:|---:|---|---|
| A01 |  |  |  |  |  |  |  |  |
| B01 |  |  |  |  |  |  |  |  |
| C01 |  |  |  |  |  |  |  |  |
| D03 |  |  |  |  |  |  |  |  |

---

## 10. Suggested full-system implementation phases

Note:

- The detailed execution plan currently approved for implementation is documented in `docs/render/phases/`.
- That plan intentionally excludes Layer F and Layer G for this wave.

### Phase 0 - Instrument first

- Implement `F01-F04`.
- Capture benchmark baseline.

Exit criteria:

- stable p50/p95 baseline by stage.

### Phase 1 - Stream reliability foundation

- Implement `B01-B03-B05`.
- Add base feature flags (`G01`).

Exit criteria:

- replay reconnect works and fallback reloads decrease.

### Phase 2 - Backend load reduction

- Implement `A01-A04-A08`.

Exit criteria:

- persist frequency and event output decrease significantly.

### Phase 3 - Frontend apply optimization

- Implement `C01-C05`.

Exit criteria:

- apply p95 decreases and rerender fanout improves.

### Phase 4 - Render optimization

- Implement `D01-D05-D08`.

Exit criteria:

- long-thread open and scrolling stay responsive.

### Phase 5 - Heavy payload hardening

- Implement `D06-D07-E01-E03`.

Exit criteria:

- large diff/output scenarios avoid UI freezes.

### Phase 6 - UX queue + final hardening

- Implement `E04-E06`, `F05-F08`, `G02-G06`.

Exit criteria:

- queue behavior is reliable and perf regressions are gated.

---

## 11. Non-goals and caution notes

1. Do not optimize blindly before baseline metrics exist.
2. Do not change too many layers at once without feature flags.
3. Do not combine large persistence migration and major UI refactor in the same release window.
4. Do not modify SSE behavior without preserving reconnect/replay contract.

---

## 12. "Optimized system" validation checklist

- [ ] Reconnect usually recovers via replay without full snapshot reload.
- [ ] Event/apply/render p95 values meet agreed budgets.
- [ ] Long threads remain interactive.
- [ ] Large diff/output cases do not freeze main thread.
- [ ] Follow-up queue behavior avoids race conditions.
- [ ] CI has performance regression gates.
- [ ] Rollout has canary and fast rollback.

---

## Appendix A - Quick file reference map

PTM:

- `backend/conversation/services/thread_runtime_service_v3.py`
- `backend/conversation/services/thread_query_service_v3.py`
- `backend/conversation/projector/thread_event_projector_runtime_v3.py`
- `backend/conversation/storage/thread_snapshot_store_v3.py`
- `backend/routes/workflow_v3.py`
- `backend/streaming/sse_broker.py`
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/conversation/state/applyThreadEventV3.ts`
- `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
- `frontend/src/features/conversation/components/FileChangeToolRow.tsx`
- `frontend/src/features/conversation/components/ConversationMarkdown.tsx`

CodexMonitor:

- `src/features/threads/hooks/useThreadsReducer.ts`
- `src/features/threads/hooks/threadReducer/threadItemsSlice.ts`
- `src/features/messages/components/Messages.tsx`
- `src/features/messages/components/MessageRows.tsx`
- `src/features/messages/components/useMessagesViewState.ts`
- `src/utils/chatScrollback.ts`
- `src/utils/threadItems.explore.ts`
- `src/features/threads/hooks/useQueuedSend.ts`
- `src/services/events.ts`

Goose:

- `crates/goose-server/src/session_event_bus.rs`
- `crates/goose-server/src/routes/session_events.rs`
- `crates/goose/src/session/thread_manager.rs`
- `crates/goose/tests/thread_message_coalescing_test.rs`
- `ui/desktop/src/components/ProgressiveMessageList.tsx`
- `ui/desktop/src/components/MarkdownContent.tsx`
- `crates/goose-cli/src/session/streaming_buffer.rs`
