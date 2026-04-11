# PTM Render Optimization - Comprehensive Guide

Status: Baseline architecture and optimization backlog.

Last updated: 2026-04-11.

---

## 1. Muc tieu tai lieu

Tai lieu nay duoc viet de:

1. Mo ta day du vi sao render thread execution/ask dang ton thoi gian.
2. So sanh cach PTM dang lam voi CodexMonitor va Goose.
3. Liet ke toan bo cac diem co the cai thien theo tung lop he thong.
4. Dua workflow before/after de de hieu va de trien khai.
5. Tao khung de sau nay loc ra thu tu uu tien.

---

## 2. Van de cot loi (de hieu nhanh)

Do tre tong cua UI chat thuong den tu cong thuc:

`Total latency = Event volume x (Backend apply cost + Persist cost + Frontend apply cost + Render cost)`

Neu event stream la rat nhieu chunk nho, va moi chunk deu di qua full pipeline, tong chi phi se bi nhan len rat manh.

### Vi du don gian

Gia su 1 cau tra loi duoc stream thanh 300 delta:

1. Backend xu ly 300 lan.
2. Store/stream publish 300 lan.
3. Frontend apply state 300 lan.
4. Feed render lai nhieu lan.

=> Cam giac UI giat, tre, va CPU tang cao.

---

## 3. Hien trang PTM (bottleneck map)

## 3.1 Backend event/projection path

PTM hien tai co xu huong xu ly theo tung raw event:

- `thread_runtime_service_v3.py`:
  - goi `get_thread_snapshot(...)`
  - `apply_raw_event_v3(...)`
  - `persist_thread_mutation(...)`
- File tham chieu:
  - `backend/conversation/services/thread_runtime_service_v3.py`
  - `backend/conversation/projector/thread_event_projector_runtime_v3.py`
  - `backend/conversation/services/thread_query_service_v3.py`

Rui ro:

- Nhieu read/write cho moi delta.
- Nhieu lock contention.
- Snapshot ghi lai lien tuc.

## 3.2 Persist path

- Snapshot v3 dang duoc `atomic_write_json(...)` tren file snapshot.
- File tham chieu:
  - `backend/conversation/storage/thread_snapshot_store_v3.py`

Rui ro:

- Write amplification cao neu event nhieu.
- I/O + serialization cost dat vao hot path.

## 3.3 SSE path

- PTM co SSE route va heartbeat.
- Chua co mo hinh replay buffer + `Last-Event-ID` chuan robust nhu Goose.
- File tham chieu:
  - `backend/routes/workflow_v3.py`
  - `backend/streaming/sse_broker.py`

Rui ro:

- Subscriber cham co the bi mat event.
- Reconnect de dan den reload lon hon can thiet.

## 3.4 Frontend state apply path

- `threadByIdStoreV3.ts` nhan event va apply lien tuc.
- `applyThreadEventV3.ts` co branch patch item va sap xep lai items.
- File tham chieu:
  - `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
  - `frontend/src/features/conversation/state/applyThreadEventV3.ts`

Rui ro:

- State churn lon.
- Render invalidation lan rong.

## 3.5 Render path

- `MessagesV3.tsx` tinh toan visible/grouped va map render feed.
- Nhieu row nang: markdown, diff parse, syntax highlight.
- File tham chieu:
  - `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
  - `frontend/src/features/conversation/components/FileChangeToolRow.tsx`
  - `frontend/src/features/conversation/components/ConversationMarkdown.tsx`

Rui ro:

- Main-thread cost cao.
- Dac biet cham voi thread dai va file diff lon.

---

## 4. So sanh voi CodexMonitor va Goose

## 4.1 CodexMonitor (diem hoc hoi chinh)

1. Reducer theo slice, action hep scope:
   - `src/features/threads/hooks/useThreadsReducer.ts`
   - `src/features/threads/hooks/threadReducer/*`
2. Message rows duoc `memo` rat nhieu:
   - `src/features/messages/components/MessageRows.tsx`
3. Co control data volume:
   - scrollback cap (`src/utils/chatScrollback.ts`)
   - normalize/truncate (`src/utils/threadItems.explore.ts`)
4. Co queue send khi thread dang processing:
   - `src/features/threads/hooks/useQueuedSend.ts`
5. Event subscription hub tap trung:
   - `src/services/events.ts`

Y nghia:

- Giam rerender lan rong.
- Giam kich thuoc state.
- UX on dinh hon khi luong su kien day.

## 4.2 Goose (diem hoc hoi chinh)

1. SSE robust:
   - replay buffer + sequence id + `Last-Event-ID`
   - detect lag subscriber va reconnect replay
   - `crates/goose-server/src/session_event_bus.rs`
   - `crates/goose-server/src/routes/session_events.rs`
2. Coalesce text chunk o storage:
   - tranh tao 1 row cho moi token
   - `crates/goose/src/session/thread_manager.rs`
3. Progressive render list:
   - `ui/desktop/src/components/ProgressiveMessageList.tsx`
4. Markdown/code performance tuning:
   - memoized code block
   - `ui/desktop/src/components/MarkdownContent.tsx`
5. Co streaming markdown buffer an toan:
   - flush o diem markdown "safe"
   - `crates/goose-cli/src/session/streaming_buffer.rs`

Y nghia:

- Giam event churn.
- Tang do ben stream/reconnect.
- Giam block UI khi thread dai.

---

## 5. Full optimization catalog

Muc nay la backlog tong hop "day du de loc uu tien sau". Moi item gom:

- Van de hien tai
- Huong cai thien
- Workflow before/after
- Metric can theo doi
- Rui ro/chu y

## Layer A - Backend ingest, projector, persist

### A01. Delta coalescing window (30-100ms)

- Van de: moi delta di full pipeline.
- Cai thien: gom delta theo `thread_id + item_id + kind` trong cua so ngan.
- Before: 300 delta -> 300 apply/persist.
- After: 300 delta -> 20-40 batch apply/persist.
- Metric: `events_in`, `events_persisted`, `persist_calls_per_turn`.
- Rui ro: tang do tre nho (vai chuc ms), can tuning cua so.

### A02. In-memory thread actor

- Van de: raw event thuong xuyen phai read snapshot hien tai.
- Cai thien: moi thread co actor state trong RAM, event patch truc tiep vao state nay.
- Before: read snapshot cho tung event.
- After: read 1 lan khi bind actor, sau do patch in-memory.
- Metric: `snapshot_reads_per_turn`, lock wait time.
- Rui ro: can co eviction policy va recovery strategy.

### A03. Checkpoint theo moc thay vi moi event

- Van de: write file snapshot qua day.
- Cai thien: checkpoint theo timer (vd 250ms) hoac boundary (`turn_completed`, `turn_failed`, `waiting_user_input`).
- Metric: `snapshot_writes_per_minute`, disk write bytes.
- Rui ro: can dam bao crash recovery du.

### A04. Event patch compaction theo item

- Van de: nhieu patch lien tiep tren cung item.
- Cai thien: merge patch append text/output truoc khi persist/publish.
- Metric: `patches_in` vs `patches_out`.
- Rui ro: logic merge can dung thu tu sequence.

### A05. Persist item-level delta (hybrid)

- Van de: snapshot full JSON cho moi mutation.
- Cai thien: luu event delta append-only + snapshot dinh ky.
- Metric: write amplification ratio.
- Rui ro: can them compaction job.

### A06. Avoid expensive deep copy in broker

- Van de: `copy.deepcopy(event)` moi subscriber.
- Cai thien: immutable payload + shallow copy metadata, hoac serialize once.
- Metric: CPU publish path, GC pressure.
- Rui ro: can dam bao no mutable shared bug.

### A07. Bounded queue + explicit backpressure

- Van de: queue growth khong kiem soat ro rang.
- Cai thien: set queue max size va strategy (`drop`, `close+replay`, `slow consumer`).
- Metric: queue depth p95/p99, lag count.
- Rui ro: can clear contract reconnect.

### A08. Skip no-op lifecycle/state updates

- Van de: event trung trang thai van publish.
- Cai thien: dedupe no-op truoc publish.
- Metric: no-op suppression count.
- Rui ro: phai tranh bo sot event co side effects.

---

## Layer B - SSE reliability and reconnect

### B01. Add SSE event `id` and replay cursor

- Cai thien: moi event co `id`, client luu `last_event_id`.
- Metric: reconnect success rate.

### B02. Server replay buffer

- Cai thien: luu N events gan nhat de replay khi reconnect.
- Before: can reload lon.
- After: replay phan thieu.
- Metric: full reload fallback count.

### B03. Gap detection and controlled resync

- Cai thien: neu gap vuot replay window, tra ve mismatch ro rang.
- Metric: gap mismatch count.

### B04. Heartbeat policy clean

- Cai thien: heartbeat khong "chiem" id event replay, tach heartbeat voi business events.
- Metric: heartbeat timeout false positive.

### B05. Client reconnect policy tuning

- Cai thien: exponential backoff + jitter + max retry.
- Metric: reconnect latency, reconnect storm count.

### B06. First frame handshake optimization

- Cai thien: gui metadata can thiet som (active request ids, stream state).
- Metric: time-to-first-meaningful-frame.

---

## Layer C - Frontend state pipeline

### C01. Frame-batched apply queue (RAF batching)

- Van de: event den la apply ngay -> render thrash.
- Cai thien: push event vao queue, apply theo frame.
- Before: 30 event nhanh = 30 apply.
- After: 30 event nhanh = 1-3 apply/frame.
- Metric: `apply_calls_per_second`, main-thread long tasks.

### C02. Normalize conversation state

- Cai thien: `itemsById + order + signals` thay cho clone list lon.
- Metric: object allocations per event.

### C03. Remove global sort on patch path

- Van de: patch item van co cost sort list.
- Cai thien: sort chi khi them item moi hoac sequence thay doi.
- Metric: patch apply duration p95.

### C04. Structural sharing stricter

- Cai thien: khong tao object moi neu value khong doi.
- Metric: React rerender count.

### C05. Split store slices by concern

- Cai thien: tach `snapshot/items`, `telemetry`, `stream transport`, `UI controls`.
- Metric: invalidation fanout.

### C06. Selector narrowing

- Cai thien: component subscribe dung phan no can.
- Metric: rendered components per event.

### C07. Fast-path for text append

- Cai thien: item text append update theo direct slot thay vi clone full array.
- Metric: apply time p95/p99.

### C08. Smarter fallback reload

- Cai thien: chi fallback reload khi gap mismatch that su, khong reload voi parse noise nho.
- Metric: forced snapshot reload count.

---

## Layer D - Render and component performance

### D01. Memoize all V3 row components

- Van de: rows V3 dang la function thuong.
- Cai thien: `React.memo` + props on dinh.
- Metric: row rerender count.

### D02. Stable callback and props identity

- Cai thien: callback map theo id, tranh tao lai object props moi moi render.
- Metric: memo hit ratio.

### D03. Progressive rendering for long history

- Cai thien: mount theo batch (vd 20-50 rows / tick).
- Metric: time-to-interactive khi mo thread dai.

### D04. Virtualization for very long feeds

- Cai thien: chi render viewport + overscan.
- Metric: DOM node count, scroll FPS.

### D05. Lazy markdown rendering

- Cai thien: row collapsed/offscreen thi chua parse markdown.
- Metric: markdown parse time total.

### D06. Workerized diff parse/highlight

- Cai thien: parse diff chunk, stats, highlight trong worker.
- Metric: main-thread blocking time.

### D07. Incremental command output viewport

- Cai thien: append tail thay vi split full text moi lan.
- Metric: command row update cost p95.

### D08. Heavy row default collapsed

- Cai thien: diff/tool lon mac dinh collapse.
- Metric: initial render time.

### D09. Render budget guard

- Cai thien: neu frame budget bi vuot, giam quality tam thoi (defer syntax highlight, reduce batch).
- Metric: dropped frames.

### D10. Cache key by `itemId + updatedAt`

- Cai thien: cache parse result an toan va de invalidate.
- Metric: cache hit rate.

---

## Layer E - Data volume and UX flow

### E01. Conversation scrollback cap for V3

- Van de: item list co the phinh vo han.
- Cai thien: cap configurable (vd 500/1000/2000), van co archive/load more.
- Metric: heap size per active thread.

### E02. Truncate policy for huge payload

- Cai thien: max chars cho output/diff preview; full content dua vao artifact.
- Metric: max payload size in render path.

### E03. Coalesce consecutive assistant text chunks

- Cai thien: hoc Goose, merge text chunk lien tiep truoc khi luu.
- Metric: rows created per turn.

### E04. Message queue when processing

- Cai thien: khi thread dang busy, message tiep theo vao queue.
- Metric: failed send while processing.

### E05. Queue pause on user-input/plan-ready

- Cai thien: queue flush tam dung khi can user action, resume sau.
- Metric: accidental send count during gated states.

### E06. User controls for queue reorder/send-now

- Cai thien: UX ro rang de giam stress va giam race.
- Metric: queue completion latency.

---

## Layer F - Observability, profiling, test

### F01. Stage timing spans

- Them span cho:
  - backend ingest
  - projector apply
  - persist
  - SSE publish
  - frontend apply
  - render commit
- Metric: p50/p95/p99 tung stage.

### F02. Event volume metrics

- Theo doi:
  - raw events in
  - compacted events out
  - events dropped/deduped

### F03. Queue and lag metrics

- Theo doi:
  - SSE queue depth
  - lagged subscriber count
  - reconnect count

### F04. Render metrics

- Theo doi:
  - commit duration
  - row rerender count
  - long task count

### F05. Synthetic load scenarios

- Tao test profile:
  - 500 event
  - 2000 event
  - diff lon
  - markdown lon

### F06. Replay/reconnect integration tests

- Test:
  - disconnect giua turn
  - reconnect voi `Last-Event-ID`
  - replay gap handling

### F07. Perf budget gates in CI

- Dat budget:
  - max apply p95
  - max render p95
  - max forced reload count

### F08. Regression dashboard

- Dashboard theo release:
  - stream health
  - render health
  - user-perceived latency

---

## Layer G - Rollout and safety

### G01. Feature flags theo lop

- Flag rieng cho:
  - backend coalescing
  - replay SSE
  - frontend frame batching
  - progressive render/virtualization

### G02. Canary rollout

- Bat theo % project/workspace.
- So sanh metric control vs treatment.

### G03. Fallback strategy

- Neu loi:
  - tat flag lop do
  - quay lai behavior cu
  - giu stream song

### G04. Data migration safety

- Neu doi persistence model:
  - write dual mode trong giai doan transition
  - verify parity truoc cutover

### G05. Contract freeze for event schema

- Chot schema truoc khi toi uu lon.
- Them contract tests producer/consumer.

### G06. Runbook for incident

- Incident playbook:
  - stream lag
  - queue overflow
  - reconnect storm
  - render freeze

---

## 6. Workflow examples (before/after)

## Example 1 - Streaming text append

Before:

1. Delta den.
2. Backend read snapshot.
3. Patch.
4. Persist full snapshot.
5. Publish event.
6. Frontend apply + re-render nhieu row.

After (A01 + A02 + C01 + D01):

1. Delta vao coalescing buffer 50ms.
2. Batch patch vao in-memory actor.
3. Checkpoint theo moc.
4. Publish event compact.
5. Frontend apply theo frame batch.
6. Chi row item vua doi render lai.

## Example 2 - Network disconnect while stream

Before:

1. Client mat ket noi.
2. Reconnect.
3. Co the phai reload snapshot lon.

After (B01 + B02 + B03):

1. Client reconnect gui `Last-Event-ID`.
2. Server replay phan event thieu.
3. Neu vuot replay window -> mismatch response co kiem soat + targeted resync.

## Example 3 - Open thread with 2000 messages

Before:

1. Mount all rows ngay.
2. Main thread block.
3. Scroll va input lag.

After (D03 + D04):

1. Render progressive theo batch.
2. Virtualize offscreen rows.
3. UI interactive som hon.

## Example 4 - Large diff tool output

Before:

1. Parse diff/hightlight tren main thread.
2. Moi update co the parse lai.

After (D06 + D10 + E02):

1. Parse nang sang worker.
2. Cache theo `itemId+updatedAt`.
3. Preview truncate + full artifact.

## Example 5 - User gui tiep khi thread dang processing

Before:

1. Send tiep de gay race/that bai.

After (E04 + E05 + E06):

1. Message vao queue.
2. Pause queue neu user-input gating.
3. Resume va flush tu dong khi an toan.

---

## 7. Metrics framework (de do hieu qua)

## 7.1 Backend

- `raw_events_per_turn`
- `compacted_events_per_turn`
- `snapshot_reads_per_turn`
- `snapshot_writes_per_turn`
- `persist_duration_ms_p95`
- `broker_publish_duration_ms_p95`

## 7.2 Transport/SSE

- `sse_reconnect_count`
- `replay_events_count`
- `replay_miss_count`
- `lagged_subscriber_count`
- `full_reload_fallback_count`

## 7.3 Frontend state

- `event_apply_duration_ms_p95`
- `state_alloc_bytes_per_sec`
- `forced_snapshot_reload_count`

## 7.4 Render

- `render_commit_duration_ms_p95`
- `rows_rendered_per_event`
- `long_task_count`
- `scroll_fps_p50/p95`

## 7.5 UX

- `time_to_first_interactive_thread_ms`
- `time_to_first_delta_visible_ms`
- `queue_wait_ms`

---

## 8. Dependency graph (high-level)

1. F01/F02/F03 (metrics) can lam som nhat.
2. B01/B02/B03 (replay/reconnect) nen di truoc de giam fallback.
3. A01/A03 + C01/C03 tao giam tai ro rang nhat.
4. D01/D03/D04 danh vao UX render thread dai.
5. D06/E02 xu ly case diff/output rat lon.

---

## 9. Prioritization template (de loc sau)

Su dung score:

`PriorityScore = (Impact x Confidence) / (Effort + Risk + RolloutComplexity)`

Thang diem de xuat:

- Impact: 1-5
- Confidence: 1-5
- Effort: 1-5
- Risk: 1-5
- RolloutComplexity: 1-5

Bang mau:

| ID | Impact | Confidence | Effort | Risk | RolloutComplexity | Score | Owner | Notes |
|---|---:|---:|---:|---:|---:|---:|---|---|
| A01 |  |  |  |  |  |  |  |  |
| B01 |  |  |  |  |  |  |  |  |
| C01 |  |  |  |  |  |  |  |  |
| D03 |  |  |  |  |  |  |  |  |

---

## 10. Suggested implementation phases (full-system path)

### Phase 0 - Instrument first

- F01-F04
- Baseline benchmark and dashboard

Exit criteria:

- Co baseline p50/p95 tung stage.

### Phase 1 - Stream reliability foundation

- B01-B03-B05
- mot phan G01/G02

Exit criteria:

- reconnect replay hoat dong on dinh, fallback giam ro.

### Phase 2 - Backend load reduction

- A01-A03-A04-A08

Exit criteria:

- persist calls/event volume giam manh.

### Phase 3 - Frontend apply optimization

- C01-C03-C04-C05

Exit criteria:

- event apply p95 giam ro, rerender fanout giam.

### Phase 4 - Render optimization

- D01-D03-D04-D05-D08

Exit criteria:

- mo thread dai khong block, scroll on dinh.

### Phase 5 - Heavy payload hardening

- D06-D07-E01-E02-E03

Exit criteria:

- case diff/output lon van smooth.

### Phase 6 - UX queue + hardening

- E04-E05-E06 + F05-F08 + G03-G06

Exit criteria:

- flow user thong suot, perf regression guard day du.

---

## 11. Non-goals and caution notes

1. Khong optimize mu quang khi chua co metrics baseline.
2. Khong thay doi nhieu lop cung luc ma khong co feature flag.
3. Khong mix data migration lon voi UI refactor trong cung 1 release window.
4. Khong bo qua reconnect/replay contract khi sua SSE.

---

## 12. Checklist de xac nhan "optimized system"

- [ ] Stream reconnect khong can full reload trong da so truong hop.
- [ ] Event/apply/render p95 dat budget da chot.
- [ ] Thread dai van interactive.
- [ ] Diff/output lon khong freeze main thread.
- [ ] Queue follow-up khong tao race loan trang thai.
- [ ] CI co perf regression gates.
- [ ] Rollout co canary va rollback nhanh.

---

## Appendix A - File map tham chieu nhanh

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
