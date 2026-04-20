# Phase 14.8 — Full Rollout Cutover (100%)

## Mục tiêu
Bật **100% rollout** cho ask + execution với cấu hình đã tối ưu 14.1–14.8, đồng thời giữ khả năng rollback nhanh.

---

## 1) Production config (100% enable)

### Frontend (`.env.production`)
```bash
# Keep V3 path enabled
VITE_ASK_V3_FRONTEND_ENABLED=true

# Full smooth-stream profile
# NOTE: high is now default in codebase; keep explicit for operational clarity.
VITE_THREAD_STREAM_LOW_LATENCY=true
VITE_THREAD_STREAM_CADENCE_PROFILE=high
```

### Backend (`.env` / deployment env)
```bash
# Keep V3 backend enabled
PLANNINGTREE_ASK_V3_BACKEND_ENABLED=true

# Stream cadence profile (production target)
# NOTE: high is now default in codebase; keep explicit for operational clarity.
PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE=high

# Optional explicit pin (recommended when doing hard cutover)
PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS=20

# Optional protection for burst pressure
PLANNINGTREE_SSE_SUBSCRIBER_QUEUE_MAX=128
```

> Nếu bạn muốn ít aggressive hơn: dùng `standard` + `coalesce_ms=25`.

---

## 2) Preflight before cutover

Run:
```bash
python scripts/phase14_8_canary_rollout_report.py --self-test --allow-synthetic --output tmp/phase14_8/full_rollout_preflight.json
python scripts/phase14_7_resilience_hardening_report.py --self-test --allow-synthetic --output tmp/phase14_7/full_rollout_resilience.json
```

Frontend quality gate:
```bash
npm run typecheck --prefix frontend
npm run test:unit --prefix frontend -- tests/unit/threadByIdStoreV3.test.ts tests/unit/ComposerBar.test.tsx tests/unit/BreadcrumbChatViewV2.test.tsx
```

---

## 3) Full cutover steps (ops)

1. Apply FE env values
2. Apply BE env values
3. Restart FE/BE deployments
4. Smoke verify:
   - Ask thread: send -> `Sending...` -> `Agent connected...` -> `Responding...`
   - Execution thread: tool-heavy turn vẫn stream ổn định
   - Không có reconnect storm hoặc forced reload spike

---

## 4) KPI watch (first 2h / 24h)

Must-watch:
- ask/execution `interUpdateGap p95`
- reconnect/session
- mismatch reload rate
- forced reload count by reason
- stream_open -> first_delta latency

Escalation trigger:
- reconnect/session tăng > 20% baseline
- mismatch reload rate > 1.5
- interUpdateGap regression > 10% baseline

---

## 5) One-shot rollback

### FE rollback
```bash
VITE_THREAD_STREAM_LOW_LATENCY=false
VITE_THREAD_STREAM_CADENCE_PROFILE=low
```

### BE rollback
```bash
PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE=low
PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS=50
```

Apply + restart services.

---

## 6) Decision log template

```md
- Cutover timestamp (UTC):
- FE env commit/ref:
- BE env commit/ref:
- 2h KPI snapshot:
- 24h KPI snapshot:
- Rollback executed? (yes/no):
- Final decision: keep / rollback / partial
```
