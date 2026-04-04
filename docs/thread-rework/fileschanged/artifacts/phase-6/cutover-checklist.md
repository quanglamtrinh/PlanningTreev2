# Phase 6 Cutover Checklist (Observe-only)

Date: 2026-04-04  
Owner scope: execution lane migration stabilization for new turns.

## 1. Preconditions

- [x] No new runtime flag/toggle introduced for file-change migration.
- [x] Public API unchanged (no new endpoint, no wire-field removal).
- [x] New-turn policy locked: migration applies only to newly created turns.
- [x] Canonical `changes[]` path is active for execution rendering logic.
- [x] Compatibility mirror fields (`outputFiles`, `files*`) remain available.

## 2. Rollout stages

## Stage A - Internal

- [x] Deploy to internal environment.
- [x] Run unit + integration gate for file-change lifecycle.
- [x] Verify no render crash in execution thread with expanded file-change card.
- [x] Verify no synthetic `+0/-0` stats on canonical-empty scenarios.

## Stage B - Canary

- [x] Promote release to canary ring.
- [x] Run smoke matrix on new turns:
  - real diff turn expands with visible patch rows
  - commandExecution remains command card
  - legacy path-only data remains fallback/minimal
- [x] Confirm no abnormal spike in apply/reload error signals.

## Stage C - Broad

- [x] Promote same release to broad rollout.
- [x] Keep observe-only monitoring window open.
- [x] Confirm execution + audit parity remains stable for semantic file-change rows.

## 3. Existing signals used for monitoring

- frontend file-change render error logs
- execution apply error traces from existing workflow telemetry
- snapshot reconnect/reload anomaly counters already present in V3 thread store flow
- smoke regression checks for empty-card-on-new-turn behavior

## 4. Exit criteria

- [x] No blocking regression across internal/canary/broad checks.
- [x] New-turn execution file-change card shows content and `+/-` when canonical diff exists.
- [x] Release rollback plan documented and verified.
