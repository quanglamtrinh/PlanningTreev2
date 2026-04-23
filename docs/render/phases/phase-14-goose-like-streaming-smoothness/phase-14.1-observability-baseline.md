# Phase 14.1 — Observability & Baseline Runbook

This runbook documents the telemetry added for Phase 14.1 and how to generate baseline artifacts.

---

## 1) New telemetry fields (`threadByIdStoreV3.telemetry`)

- `lastStreamUpdateAtMs: number | null`
- `interUpdateGapMaxMs: number`
- `interUpdateGapTotalMs: number`
- `interUpdateGapSamples: number`
- `streamingRowRenderCount: number`
- `markdownParseDurationTotalMs: number`
- `markdownParseDurationMaxMs: number`
- `markdownParseDurationSamples: number`

### Semantics

- `interUpdateGap*` are updated when batched business events are flushed into visible state.
- `streamingRowRenderCount` increments when a `message` row with `in_progress` status renders.
- `markdownParseDuration*` accumulates per `ConversationMarkdown` render-cycle measurement.

---

## 2) Where metrics are instrumented

- Stream flush cadence:  
  `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- Streaming row render counter:  
  `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
- Markdown parse duration counter:  
  `frontend/src/features/conversation/components/ConversationMarkdown.tsx`

---

## 3) Local verification commands

```bash
npm run typecheck
npm run test:unit --prefix frontend -- tests/unit/threadByIdStoreV3.test.ts tests/unit/messagesV3.profiling-hooks.test.tsx
```

---

## 4) Baseline artifact script

Script:
- `scripts/phase14_1_streaming_telemetry_baseline.py`

Synthetic local dry-run:

```bash
python scripts/phase14_1_streaming_telemetry_baseline.py \
  --self-test \
  --allow-synthetic \
  --output tmp/phase14_1/streaming_telemetry_baseline.json
```

Candidate mode (gate-eligible):

```bash
python scripts/phase14_1_streaming_telemetry_baseline.py \
  --self-test \
  --candidate <candidate-json-path> \
  --candidate-commit-sha <git-sha> \
  --output docs/render/phases/phase-14-goose-like-streaming-smoothness/evidence/streaming_telemetry_baseline.json
```

Expected candidate payload can include:

- `candidate_metrics.ask.inter_update_gap_p95_ms`
- `candidate_metrics.execution.inter_update_gap_p95_ms`
- `candidate_metrics.ask.streaming_row_render_count`
- `candidate_metrics.execution.streaming_row_render_count`
- `candidate_metrics.ask.markdown_parse_duration_avg_ms`
- `candidate_metrics.execution.markdown_parse_duration_avg_ms`

---

## 5) Phase 14.1 completion checklist

- [x] Add inter-update gap telemetry
- [x] Add streaming row render telemetry
- [x] Add markdown parse duration telemetry
- [x] Add/adjust unit tests for telemetry updates
- [x] Add baseline artifact script for ask/execution
- [x] Verify local synthetic baseline generation
