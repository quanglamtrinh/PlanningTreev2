# Phase 14.8 — Canary Rollout & Rollback Drills

## Goal
Safe production adoption cho toàn bộ cải tiến 14.1–14.7 với cơ chế rollback rõ ràng, có thể thực thi nhanh.

---

## Rollout plan

### Step 0 — Internal dogfood
- Scope: internal users only
- Duration: tối thiểu 48h
- Requirements:
  - No blocker bug
  - KPI không vượt ngưỡng cảnh báo

### Step 1 — Ask thread canary
- 10% -> 50% -> 100%
- Mỗi nấc theo dõi 48h
- Gate trước khi tăng nấc:
  - `interUpdateGap p95` không xấu hơn baseline > 15%
  - reconnect/session không tăng > 20%
  - mismatch/reload storm không tăng bất thường

### Step 2 — Execution thread canary
- 10% -> 50% -> 100%
- Mỗi nấc theo dõi 48h
- Gate tương tự Ask + kiểm thêm:
  - tool/reasoning heavy turns không tăng render stall

---

## Rollback controls

### Frontend
- `VITE_THREAD_STREAM_LOW_LATENCY=false`
- `VITE_THREAD_STREAM_CADENCE_PROFILE=low`

### Backend
- `PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS=50`
- `PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE=low`

### Feature-path isolation
- Tắt streaming lane override (nếu có rollout flag riêng)
- Tắt markdown-safe staging (nếu có rollout flag riêng)

---

## Rollback drill (required)

### Drill scenario A — FE immediate rollback
1. Canaries đang ở 50%
2. Simulate alert breach (reconnect spike / render stall)
3. Apply FE rollback env
4. Verify:
   - New sessions về low-latency disabled
   - KPI quay về baseline band trong 30 phút

### Drill scenario B — BE immediate rollback
1. Canaries đang ở 50%
2. Simulate backend pressure / coalesce side effects
3. Apply BE rollback env (`coalesce_ms=50`, profile=low)
4. Verify:
   - reconnect/mismatch không tăng
   - stream cadence ổn định lại

### Drill scenario C — Combined rollback
- FE + BE rollback cùng lúc
- Validate không có incompatible state transition ở session đang mở

---

## KPI gates (release)

### Must-pass
- Ask + Execution:
  - `interUpdateGap p95` cải thiện hoặc không xấu hơn baseline > 10%
  - reconnect/session không tăng > 20%
  - mismatch reload rate trong ngưỡng 14.7
- No P1/P0 correctness regression

### Nice-to-have
- `firstMeaningfulFrameLatencyMs` median giảm
- subjective UX QA rating tăng so với baseline

---

## Run commands

### Generate Phase 14.8 rollout report (synthetic local)
```bash
python scripts/phase14_8_canary_rollout_report.py --self-test --allow-synthetic
```

### Candidate mode (gate-eligible)
```bash
python scripts/phase14_8_canary_rollout_report.py \
  --candidate <path-to-candidate-metrics.json> \
  --candidate-commit-sha <sha> \
  --self-test
```

---

## Exit checklist
- [x] Canary plan documented (ask/execution 10->50->100)
- [x] Rollback switches documented (FE/BE)
- [x] Rollback drill scenarios documented
- [x] Gate report script available + self-test pass
- [ ] One full production cycle completed (ops)
