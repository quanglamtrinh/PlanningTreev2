# Phase 2: Backend Performance and Observability

Status: completed on 2026-04-06.

Effort: 14% (about 3.0 engineering days).

Depends on: Phase 1.

## Goal

Harden backend scanner performance and make runtime behavior observable and diagnosable.

## Scope

- Add in-memory caching with safe invalidation strategy.
- Add structured logging and scan diagnostics.
- Add resilience improvements for large histories and malformed data.
- Add targeted performance-focused tests.

## Detailed implementation checklist

## 1) Introduce caching strategy

In `LocalUsageSnapshotService`:

- add cache key by `days`.
- cache value:
  - snapshot payload
  - timestamp of computation
  - scan diagnostics
- add TTL (suggested baseline: 30 seconds).
- behavior:
  - if cache valid, return cached snapshot quickly
  - if cache stale, recompute and replace cache

Concurrency safeguards:

- add lock around cache read/write mutation.
- avoid duplicate concurrent full scans for identical keys.

## 2) Add scan diagnostics and structured logs

Track and log at info/debug level:

- files visited
- files parsed
- invalid JSON lines count
- skipped oversized lines count
- token events processed
- total scan duration milliseconds
- cache hit/miss

Log format guidance:

- one summary log per request path
- avoid per-line noisy logs by default

## 3) Add guardrails for heavy inputs

- line-length cap to prevent excessive memory pressure.
- robust timestamp parser fallback:
  - RFC3339 text
  - epoch seconds
  - epoch milliseconds
- numeric parser tolerance:
  - int/float/string numeric forms where safe
- prevent negative delta accumulation from out-of-order totals.

## 4) Validate days-clamping behavior

- enforce `days in [1, 90]`.
- malformed `days` should not 500 the route.
- document clamping in route docstring/comments.

## 5) Expand tests for cache and perf-sensitive behavior

Add or extend tests:

- cache hit returns identical payload within TTL.
- stale cache triggers refresh.
- concurrent calls do not race into inconsistent cache state.
- malformed data does not break route contract shape.

## File targets

- `backend/services/local_usage_snapshot_service.py`
- `backend/tests/unit/test_local_usage_snapshot_service.py`
- `backend/tests/integration/test_codex_api.py`

## Verification commands

- `python -m pytest backend/tests/unit/test_local_usage_snapshot_service.py -q`
- `python -m pytest backend/tests/integration/test_codex_api.py -q`

## Deliverables

- cache-enabled scanner with deterministic behavior.
- meaningful scan diagnostics available in logs.
- hardened parser for real-world noisy session files.

## Exit criteria

- repeated polling traffic does not trigger expensive full scan every request.
- scan duration and parse-health can be inspected quickly from logs.
- no high-severity performance/regression issue blocks frontend integration.
