# Phase 03 Gate Measurement Plan v1

Status: Active measurement protocol for Phase 03.

Last updated: 2026-04-12.

Owner: backend runtime + QA pairing.

## Purpose

Define a repeatable way to evaluate Phase 03 gates:

- `P03-G1` persisted event reduction
- `P03-G2` semantic mismatch count
- `P03-G3` added stream latency p95

Source of gate truth:

- `docs/render/system-freeze/phase-gates-v1.json`

## Baseline Pinning

Before collecting candidate results, pin baseline:

1. Select a baseline commit before Phase 03 compaction changes.
2. Record it in `evidence/baseline-commit.txt`.
3. Run the same workload profile for baseline and candidate.

## Evidence Folder Layout

Use this fixed layout:

- `docs/render/phases/phase-03-backend-delta-compaction/evidence/baseline-commit.txt`
- `docs/render/phases/phase-03-backend-delta-compaction/evidence/backend-stream-benchmark.json`
- `docs/render/phases/phase-03-backend-delta-compaction/evidence/golden-replay-equivalence.json`
- `docs/render/phases/phase-03-backend-delta-compaction/evidence/stream-latency-probe.json`
- `docs/render/phases/phase-03-backend-delta-compaction/evidence/phase03-gate-report.json`

## Metric Definitions

### P03-G1 persisted_events_per_turn_reduction_pct

Formula:

- `((baseline_persisted_events_per_turn - candidate_persisted_events_per_turn) / baseline_persisted_events_per_turn) * 100`

Input file:

- `backend-stream-benchmark.json`

Required fields:

- `baseline_persisted_events_per_turn`
- `candidate_persisted_events_per_turn`

Target:

- `>= 40`

### P03-G2 semantic_mismatch_cases_vs_baseline

Definition:

- number of replay/equivalence cases where final snapshot differs vs non-compacted baseline

Input file:

- `golden-replay-equivalence.json`

Required fields:

- `semantic_mismatch_cases_vs_baseline`

Target:

- `<= 0`

### P03-G3 added_stream_latency_p95_ms

Definition:

- incremental stream latency p95 introduced by compaction window (candidate minus baseline)

Input file:

- `stream-latency-probe.json`

Required fields:

- `added_stream_latency_p95_ms`

Target:

- `<= 80`

## Gate Evaluation Command

Run:

```powershell
python scripts/phase03_gate_report.py `
  --benchmark docs/render/phases/phase-03-backend-delta-compaction/evidence/backend-stream-benchmark.json `
  --equivalence docs/render/phases/phase-03-backend-delta-compaction/evidence/golden-replay-equivalence.json `
  --latency docs/render/phases/phase-03-backend-delta-compaction/evidence/stream-latency-probe.json `
  --out docs/render/phases/phase-03-backend-delta-compaction/evidence/phase03-gate-report.json
```

Expected output:

- non-zero exit code if any gate fails
- JSON report with per-gate pass/fail and raw values

## Minimum Workload Protocol

Use at least these scenarios for both baseline and candidate:

1. message streaming burst (high `item/agentMessage/delta`)
2. tool output burst (high `item/commandExecution/outputDelta`)
3. mixed stream with lifecycle and user-input boundaries

Each scenario should run enough turns to compute stable p95 values (recommendation: at least 30 turns/scenario).

## Acceptance Rule

Phase 03 can be marked pass only when all are true:

1. `P03-G1` pass
2. `P03-G2` pass
3. `P03-G3` pass
4. replay/reconnect contract tests remain green

