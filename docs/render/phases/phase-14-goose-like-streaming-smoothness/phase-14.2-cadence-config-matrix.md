# Phase 14.2 — Transport Cadence Config Matrix

This document defines safe cadence knobs for ask/execution streaming with profile-based presets.

---

## 1) Frontend cadence profile

Env:
- `VITE_THREAD_STREAM_CADENCE_PROFILE=low|standard|high`
- Legacy fallback (still supported): `VITE_THREAD_STREAM_LOW_LATENCY=true|false`

Implementation:
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- resolver: `resolveThreadStreamCadencePolicy(...)`

### Presets

| Profile | fallbackFlushMs | priorityFlushMs | maxQueueAgeMs |
|---|---:|---:|---:|
| low | 20 | 12 | 60 |
| standard | 16 | 8 | 25 |
| high | 12 | 6 | 20 |

Selection order:
1. `VITE_THREAD_STREAM_CADENCE_PROFILE` (explicit)
2. Legacy switch (`VITE_THREAD_STREAM_LOW_LATENCY=false` => `low`)
3. Device-memory heuristic
   - `< 4GB` => `low`
   - `>= 8GB` => `high`
   - otherwise `standard`

---

## 2) Backend coalescing profile

Envs:
- `PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE=low|standard|high`
- Optional explicit override: `PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS`

Implementation:
- `backend/config/app_config.py`
- `backend/main.py` wiring + startup log

### Presets (used when explicit ms override is NOT set)

| Profile | coalesce window ms |
|---|---:|
| low | 60 |
| standard | 25 |
| high | 20 |

Override precedence:
1. `PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS` (clamped 10..80)
2. profile default from `PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE`

---

## 3) Recommended matrix by environment

| Environment | FE profile | BE profile | Notes |
|---|---|---|---|
| Local dev (default) | standard | standard | Balanced baseline |
| CI perf smoke | high | high | Stress low-latency path |
| Lower-end client cohort | low | low | Throughput/stability bias |
| Canary (10%) | standard | standard | Compare KPI deltas first |
| Full rollout target | standard/high mix | standard/high mix | Split by device profile |

---

## 4) Rollout checklist

- [ ] capture baseline (Phase 14.1 metrics)
- [ ] apply profile in canary only
- [ ] monitor inter-update gap p95/p99 (ask/execution separately)
- [ ] verify reconnect and forced-reload guardrails
- [ ] promote profile only after 48h stable window

---

## 5) Rollback

Immediate rollback knobs:
- FE: `VITE_THREAD_STREAM_CADENCE_PROFILE=low`
- FE legacy hard fallback: `VITE_THREAD_STREAM_LOW_LATENCY=false`
- BE: `PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE=low`
- BE hard fallback: `PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS=50`

---

## 6) KPI expectation for Phase 14.2

Primary expected gain:
- Execution inter-update gap p95 improves by at least 20% over Phase 14.1 baseline.

Guardrails:
- reconnect/session does not regress >10%
- forced snapshot reload rate does not regress >5%
