# Phase 14 Roadmap — Goose-like Streaming Smoothness for Ask/Execution Threads

Status: Draft  
Owner: Frontend + Backend Conversation Team  
Scope: `workflow_v3` thread-by-id stream, ask thread, execution thread, message rendering pipeline

---

## 0) Problem Statement

PlanningTreeMain currently feels “chunky/batchy” in long streaming turns, especially for execution threads.

Observed symptoms:
- text appears in bursts (not smooth incremental flow)
- render updates feel “whole block” instead of lightweight append
- heavy markdown/tool rows increase perceived jitter
- reconnect/reload paths can interrupt visual continuity

Target outcome:
- visual experience closer to Goose: responsive after user send + stable incremental stream
- keep correctness guarantees (replay, cursor monotonicity, mismatch protection)
- no regression in reliability or long-thread performance

---

## 1) Guiding Principles (from Goose patterns)

1. **Correctness first**: sequence ID + replay + Last-Event-ID handling must remain strict.
2. **Incremental append path**: text deltas should update only active streaming row whenever possible.
3. **Separate lanes**:
   - low-latency lane for text append
   - throughput lane for heavy payload (tool/diff/review)
4. **Progressive rendering** for large histories.
5. **Markdown-safe rendering strategy** to avoid re-parse churn and malformed partial markdown artifacts.
6. **Feature-flagged rollout** with fast rollback switches.

---

## 2) Non-goals (for this phase set)

- redesigning conversation UX layout
- changing domain event contracts
- removing existing replay/reload safeguards
- replacing virtualization system completely

---

## 3) Success Metrics & SLO

Measure separately for ask and execution.

### Core UX metrics
- `firstMeaningfulFrameLatencyMs` p95
- `interUpdateGapMs` p95/p99 (time between visible text updates)
- `framesPerSecondDuringStreaming` median during active turn
- `% turns perceived smooth` from internal QA checklist

### Correctness/reliability
- reconnect/session rate
- forced snapshot reload rate by reason:
  - `REPLAY_MISS`
  - `CONTRACT_*`
  - `APPLY_EVENT_FAILED`
- duplicate/non-monotonic event_id incidents

### Render cost
- row render count per second (active streaming row)
- total commit duration per second during stream
- markdown parse time per flush

### Target gates (initial)
- ask: inter-update gap p95 < 80ms
- execution: inter-update gap p95 < 120ms
- no >10% reconnect regression
- no >5% forced reload regression

---

## 4) Architecture Delta (high-level)

Current:
- backend compaction window + frontend queue batching
- apply events into snapshot-centric store
- message list and row rendering share same cadence

Proposed:
- keep existing correctness path
- add **Streaming Text Lane** in frontend:
  - detect text append events
  - apply lightweight row-local patch path first
  - periodically reconcile full snapshot state
- add **Markdown Render Staging**:
  - plain text rendering during active stream
  - markdown compile in idle/safe boundaries
- keep heavy content in throughput lane

---

## 5) Phase Plan

## Phase 14.1 — Observability & Baseline Freeze (2–3 days)

### Goal
Establish reliable before/after measurement to avoid subjective tuning.

### Deliverables
1. Telemetry additions in conversation store:
   - `interUpdateGapMs` histogram buckets
   - `streamingRowRenderCount`
   - `markdownParseDurationMs`
2. profiling scripts update:
   - extend `scripts/phase09_row_render_profile.py`
   - extend `scripts/phase10_scroll_smoothness_profile.py`
3. baseline report (ask + execution workloads)

### Files (expected)
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/conversation/components/*`
- `scripts/phase09_row_render_profile.py`
- `scripts/phase10_scroll_smoothness_profile.py`

### Exit criteria
- reproducible benchmark scenarios and baseline JSON artifacts committed.

---

## Phase 14.2 — Transport Cadence Tuning (safe knobs) (2 days)

### Goal
Reduce burst perception without semantic behavior changes.

### Deliverables
1. Frontend low-latency knobs finalized:
   - max queue age
   - fallback flush delay
   - priority micro-flush delay for text append
2. Backend compaction window env documented and tuned per environment.
3. Config matrix for low/standard/high devices.

### Files
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `backend/config/app_config.py`
- `backend/main.py`
- docs: env configuration section

### Risks
- too low window -> high CPU / render churn

### Mitigation
- keep feature flags + guardrails
- clamp min/max values

### Exit criteria
- inter-update gap improves at least 20% in execution baseline scenario.

---

## Phase 14.3 — Streaming Text Lane (core) (4–6 days)

### Goal
Stop re-applying heavy snapshot path on every text delta.

### Design
1. Add lane-local buffer keyed by `{threadId, itemId}` for active assistant message.
2. On `conversation.item.patch.v3` message text append:
   - update lane buffer immediately
   - update active row selector state
3. Snapshot reducer reconciliation policy:
   - periodic reconcile (e.g., every N ms or boundary events)
   - hard reconcile on lifecycle boundaries / snapshot events
4. Ensure event ordering guarantees preserved via event_id checks.

### Deliverables
- new lane state + selectors
- active row component consumes lane state first
- reconciliation unit tests

### Files
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/conversation/state/applyThreadEventV3.ts`
- `frontend/src/features/conversation/components/messages/*`
- `frontend/tests/unit/*threadById*`

### Risks
- divergence between lane buffer and snapshot

### Mitigation
- invariant checks in dev mode
- forced reconcile on boundary events

### Exit criteria
- active streaming row render cost reduced significantly (>30% fewer heavy renders)
- no correctness test regressions

### Phase 14.3C completion note
- Added UI parity test asserting streaming text lane override wins over snapshot text for assistant `in_progress` rows.
- Added lane guard normalization for thread/item keys before lane patch apply to reduce drift from malformed payloads.
- Verified with frontend typecheck + unit suites (including `MessagesV3`, `threadByIdStoreV3`, profiling hooks).

---

## Phase 14.4 — Row-level Render Isolation (3–4 days)

### Goal
Prevent “whole list rerender” during streaming.

### Deliverables
1. Memoization strategy per row:
   - `React.memo` + stable props
   - selectors by `itemId`
2. Separate `StreamingMessageRow` from heavy static rows.
3. Avoid regroup/remeasure on plain text append events.

### Files
- `frontend/src/features/conversation/components/messages/MessageRow*.tsx`
- `frontend/src/features/conversation/components/messages/MessagesV3*.tsx`
- `frontend/src/features/conversation/components/messages/hooks/*`

### Exit criteria
- row render profile confirms only active streaming row updates for text deltas.

### Phase 14.4 completion note
- Moved streaming lane subscription from list-level `MessagesV3` into row-level `MessageRowV3` selector keyed by `(threadId, itemId)`.
- Removed list-level `streamingTextLaneByItemId` map wiring from grouped render path.
- Added profiling unit test asserting lane updates rerender targeted active row without rerendering stable neighbor rows.
- Verified via frontend typecheck + unit suite.

---

## Phase 14.5 — Markdown-safe Stream Rendering (4 days)

### Goal
Reduce markdown parse churn + avoid malformed partial rendering during stream.

### Design
1. During active stream:
   - render plain text for active row by default
   - optional lightweight markdown if safe boundary reached
2. Safe boundary detector:
   - newline/sentence boundary minimum
   - fenced code block/link closure heuristics
3. On turn complete or boundary flush:
   - promote to full markdown render

### Deliverables
- boundary detector utility
- staged renderer strategy
- benchmark for markdown-heavy prompts

### Files
- `frontend/src/features/conversation/components/Markdown*`
- `frontend/src/features/conversation/components/messages/StreamingMessageRow.tsx`
- `frontend/src/features/conversation/utils/*`

### Exit criteria
- markdown-heavy execution turns no longer drop FPS sharply on each delta.

---

## Phase 14.6 — Early Response UX (post-send responsiveness) (2–3 days)

### Goal
Perceived instant response right after user submits.

### Deliverables
1. immediate local placeholder/typing state on send (`<= 50ms`)
2. deterministic transition:
   - pending user send -> stream_open -> first delta
3. if stream delayed:
   - gentle status indicator updates without layout shift

### Files
- `threadByIdStoreV3.ts`
- input/send action handlers in conversation UI
- loading/typing components

### Exit criteria
- UX audit confirms immediate feedback after send in ask and execution.

---

## Phase 14.7 — Resilience & Long-session Hardening (3 days)

### Goal
Ensure smoothness improvements do not hurt reconnect/replay resilience.

### Deliverables
1. stress scenarios:
   - lagged subscriber
   - reconnect with replay cursor near edge
   - long session (1000+ items)
2. validate no increase in mismatch reload storms
3. add defensive logging around lane reconcile failures

### Files
- `scripts/phase08_stream_resilience_scenario.py`
- `scripts/phase12_long_session_volume_tests.py`
- backend/frontend test suites

### Exit criteria
- resilience metrics within gate thresholds.

---

## Phase 14.8 — Canary Rollout & Rollback Drills (2–3 days)

### Goal
Safe production adoption.

### Rollout steps
1. Internal dogfood only
2. Ask thread canary 10% -> 50% -> 100%
3. Execution thread canary 10% -> 50% -> 100%
4. Monitor 48h each step

### Rollback controls
- FE: `VITE_THREAD_STREAM_LOW_LATENCY=false`
- BE: `PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS=50`
- disable streaming text lane flag (new flag from phase 14.3)

### Exit criteria
- all KPI gates green for 1 full cycle
- rollback drill validated

---

## 6) Test Strategy

## Unit tests
- event order and cursor monotonic checks
- lane reconcile logic
- markdown safe-boundary detector
- row memoization behavior

## Integration tests
- ask/execution stream scenarios with bursty deltas
- reconnect + replay from Last-Event-ID
- user input interrupt + resume

## E2E / UX tests
- submit -> first feedback timing
- long thread scrolling while streaming
- markdown-heavy turn smoothness

## Performance tests
- CPU/memory sampling on low-end device profile
- render commit duration under high delta rates

---

## 7) Work Breakdown Structure (tickets)

### FE-14A Observability
- FE-14A-1 add interUpdateGap telemetry
- FE-14A-2 add row render counters
- FE-14A-3 benchmark report exporter

### FE-14B Cadence
- FE-14B-1 priority micro-flush tuning
- FE-14B-2 device profile adaptive thresholds

### FE-14C Streaming Lane
- FE-14C-1 lane state model
- FE-14C-2 append fast path integration
- FE-14C-3 reconcile scheduler + invariants

### FE-14D Render Isolation
- FE-14D-1 StreamingMessageRow split
- FE-14D-2 row selectors + memo guards
- FE-14D-3 list regroup suppression on text append

### FE-14E Markdown staging
- FE-14E-1 boundary detector
- FE-14E-2 staged rendering pipeline
- FE-14E-3 finalize-on-turn-complete

### BE-14A Transport tuning
- BE-14A-1 coalesce config docs + presets
- BE-14A-2 env rollout templates

### QA-14
- QA-14-1 matrix ask/execution + low/high load
- QA-14-2 resilience regression suite
- QA-14-3 canary dashboard + alarm thresholds

---

## 8) Risks & Mitigations

1. **State divergence (lane vs snapshot)**
   - invariant assertions + forced reconcile boundaries
2. **CPU increase from over-frequent flush**
   - adaptive cadence by device profile
3. **Markdown visual inconsistency**
   - explicit staged rendering states + completion sync
4. **Canary blind spots**
   - split dashboards by thread role and project size

---

## 9) Rollout Decision Checklist

- [ ] Baseline report approved
- [ ] Phase 14.3 lane correctness tests green
- [ ] execution-thread stress scenario green
- [ ] reconnect/replay mismatch rate stable
- [ ] rollback switches verified in staging

---

## 10) Definition of Done (program-level)

- Ask + execution streaming subjectively smooth in QA scripts
- KPI gates pass for 2 consecutive canary windows
- No material regression in correctness/reconnect metrics
- Documentation and runbook complete (flags, tuning, rollback)

---

## 11) Suggested Timeline

- Week 1: Phase 14.1 + 14.2
- Week 2: Phase 14.3
- Week 3: Phase 14.4 + 14.5
- Week 4: Phase 14.6 + 14.7 + 14.8

(Adjust based on team bandwidth; phase boundaries are designed for independent PR batches.)
