# Phase 14.7 — Resilience & Long-session Hardening

## Goal
Đảm bảo các tối ưu smoothness (14.1–14.6) **không làm xấu đi** độ bền của stream/replay/reconnect trên session dài.

---

## Scope
Theo roadmap:
1. Stress scenarios
   - lagged subscriber
   - reconnect với replay cursor near-edge
   - long session (1000+ items)
2. Không tăng mismatch reload storms
3. Bổ sung defensive logging quanh lane reconcile anomalies

---

## Implemented artifacts

### 1) Store defensive logging (frontend)
**File:** `frontend/src/features/conversation/state/threadByIdStoreV3.ts`

- Added throttled warning helper:
  - `emitStreamingLaneReconcileWarning(...)`
  - throttle window: `STREAMING_LANE_RECONCILE_WARN_THROTTLE_MS = 5000`
- Added warning emission in reconcile anomalies:
  - `snapshot_thread_id_missing`
  - `entry_thread_mismatch`
  - `entry_not_in_progress_or_missing`
  - `entry_text_suffix_mismatch`

Mục tiêu: khi có drift/contract anomaly ở lane reconcile, có evidence rõ để audit mà không spam console/log pipeline.

### 2) Phase 14.7 resilience report script
**File:** `scripts/phase14_7_resilience_hardening_report.py`

Output default:
- `docs/render/phases/phase-14-goose-like-streaming-smoothness/evidence/phase14_7_resilience_hardening_report.json`

Metrics aggregated (candidate/synthetic):
- `lagged_subscriber_reconnect_rate`
- `replay_edge_mismatch_reload_rate`
- `long_session_live_items_exceeds_cap_events`
- `transient_reconnect_unnecessary_forced_reload`

Gate thresholds (script-level):
- reconnect rate `<= 0.35`
- mismatch reload rate `<= 1.5`
- long-session cap exceed events `== 0`
- unnecessary forced reload after transient reconnect `== 0`

---

## Local verification

### A. Self-test (synthetic local dry-run)
```bash
python scripts/phase14_7_resilience_hardening_report.py --self-test --allow-synthetic
```

### B. Candidate mode (gate-eligible)
```bash
python scripts/phase14_7_resilience_hardening_report.py \
  --candidate <path-to-candidate-metrics.json> \
  --candidate-commit-sha <sha> \
  --self-test
```

---

## Rollback / safety guard
- Không thay đổi protocol/network contract.
- Defensive logging chỉ là quan sát (không ảnh hưởng apply path).
- Nếu cần tắt nhanh noise ở runtime: giữ throttle cao hơn hoặc strip warn calls trong hotfix patch.

---

## Exit checklist (phase-level)
- [x] Có stress evidence aggregator cho 3 scenario
- [x] Có guard metric cho mismatch/reload storm
- [x] Có defensive logging cho lane reconcile anomaly
- [x] Script self-test pass
