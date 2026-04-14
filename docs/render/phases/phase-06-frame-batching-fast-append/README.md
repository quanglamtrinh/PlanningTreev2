# Phase 06 - Frame Batching and Fast Text Append

Status: Completed (all P06 gates passed with committed evidence).

Scope IDs: C01, C07.

Subphase workspace: ./subphases/.

## Entry Criteria Artifacts

`phase-manifest-v1.json` entry criteria for Phase 06:

- `phase_05_passed`.
- `frontend_batching_policy_frozen`.

Phase 06 entry artifacts:

- `docs/render/phases/phase-05-persistence-broker-efficiency/evidence/phase05-gate-report.json`.
- `docs/render/phases/phase-06-frame-batching-fast-append/frontend-batching-policy-v1.md`.

Phase closure artifacts:

- `docs/render/phases/phase-06-frame-batching-fast-append/close-phase-v1.md`.
- `docs/render/phases/phase-06-frame-batching-fast-append/handoff-to-phase-07.md`.
- `docs/render/phases/phase-06-frame-batching-fast-append/evidence/phase06-gate-report.json`.

Phase closure snapshot:

- `P06-G1`: `65.0` (`>= 50`).
- `P06-G2`: `100.0` (`<= 120`).
- `P06-G3`: `0` (`<= 0`).

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Applies CodexMonitor-style frontend throughput improvements after stream contract stabilization.

Contract focus:

- Primary: `C5` Frontend State Contract v1
- Secondary: `C1` Event Stream Contract v1

Must-hold decisions:

- Frontend batching is presentation-only, not semantic coalescing.
- Final state must remain equivalent to canonical backend event semantics.
- Apply ordering must remain deterministic under burst traffic.


## Objective

Reduce frontend apply thrash by batching event application per animation frame and using a fast path for streaming text append.

## Execution Snapshot

Implemented outcomes:

- frame-batched event apply pipeline in the V3 thread-by-id stream store.
- guarded fast-path for append-only message text patches with strict fallback.
- internal batching telemetry counters for gate evidence generation.

Gate results (current evidence):

- `P06-G1` apply reduction: `65.0%` (target `>= 50%`).
- `P06-G2` visible lag p95: `100.0 ms` (target `<= 120 ms`).
- `P06-G3` batch order violations: `0` (target `<= 0`).

Evidence files:

- `docs/render/phases/phase-06-frame-batching-fast-append/evidence/frontend-event-burst-scenario.json`.
- `docs/render/phases/phase-06-frame-batching-fast-append/evidence/interactive-stream-smoke.json`.
- `docs/render/phases/phase-06-frame-batching-fast-append/evidence/apply-order-integration-tests.json`.
- `docs/render/phases/phase-06-frame-batching-fast-append/evidence/phase06-gate-report.json`.

## In Scope

1. C01: Frame-batched event apply (RAF batching).
2. C07: Fast-path text append.

## Detailed Improvements

### 1. RAF event queue (C01)

Instead of immediate apply per incoming event:

- enqueue events in a short-lived buffer
- flush on `requestAnimationFrame`
- process as one state transition batch

Result: burst events produce fewer store mutations and rerenders.

### 2. Fast append slot update (C07)

For streaming assistant text chunks:

- avoid generic patch walker
- use direct append path on known item slot
- skip expensive recomputation when only text tail changed

## Implementation Plan

1. Store layer:
   - add event queue and frame flush scheduler.
   - provide immediate flush on terminal/critical events.
2. Apply logic:
   - add text-append specialized path with strict guard conditions.
3. UI behavior:
   - ensure partial text remains responsive during batching.

## Quality Gates

1. Apply reduction:
   - burst event apply calls drop significantly.
2. Responsiveness:
   - no visible lag in live text stream.
3. Correctness:
   - final text content matches non-batched baseline.

## Test Plan

1. Unit tests:
   - RAF scheduler flush timing and ordering.
   - fast append guard conditions.
2. Integration tests:
   - high-frequency text streaming burst.
3. Manual checks:
    - compare visual smoothness before/after.
4. Gate harness:
   - run `scripts/phase06_gate_report.py` with Phase 06 evidence sources.
   - canonical report output:
     - `docs/render/phases/phase-06-frame-batching-fast-append/evidence/phase06-gate-report.json`.

## Risks and Mitigations

1. Risk: delayed rendering from over-batching.
   - Mitigation: max queue age and forced flush policy.
2. Risk: fast path bypasses side-effects.
   - Mitigation: strict eligibility checks and fallback to generic path.

## Known Trade-offs and Residual Risks

1. Frame batching introduces bounded render delay by design.
   - Current mitigation: fallback flush timer and max queue age forced flush.
2. Fast path only optimizes message append patches in this phase.
   - Broader patch hot-path optimization remains in Phase 07 scope.
3. Gate source scripts are deterministic harnesses, not runtime observability.
   - Layer F observability remains explicitly out-of-scope for this wave.

## Handoff to Phase 07

With apply frequency reduced, deeper state-shape optimizations can target remaining hot-path costs.


## Effort Estimate

- Size: Medium
- Estimated duration: 4-5 engineering days
- Suggested staffing: 1 frontend primary + 1 backend support
- Confidence level: Medium (depends on current code-path complexity and test debt)





