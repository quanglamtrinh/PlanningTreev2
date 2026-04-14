# Phase 11 - Heavy Compute Off Main Thread

Status: In progress.

Scope IDs: D05, D06, D07.

Subphase workspace: ./subphases/.

Frozen preflight artifacts:

1. `preflight-v1.md`
2. `worker-result-versioning-policy-v1.md` (`worker_result_versioning_policy_frozen`)

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Offloads expensive UI compute while keeping deterministic rendering semantics.

Contract focus:

- Primary: `C5` Frontend State Contract v1

Must-hold decisions:

- Worker paths must use version tokens and discard stale async results.
- Fallback sync path must remain behaviorally equivalent.
- Off-main-thread optimization cannot alter message semantics.


## Objective

Prevent main-thread stalls from markdown/diff/command-output heavy rows.

## In Scope

1. D05: Lazy markdown rendering.
2. D06: Workerized diff parse/highlight.
3. D07: Incremental command output tail updates.

## Detailed Improvements

### 1. Lazy markdown rendering (D05)

Defer markdown parse for:

- offscreen rows
- collapsed rows
- low-priority historical content

Parse eagerly only for currently visible and active rows.

### 2. Workerized diff/highlight (D06)

Move expensive parsing/highlighting to worker thread:

- main thread sends source payload + mode
- worker returns parsed/highlighted artifact
- fallback to sync path only on worker failure

### 3. Incremental command tail updates (D07)

For streaming command output:

- append incremental segments
- avoid full split/re-parse of entire output on each chunk

## Implementation Plan

1. Add visibility-aware lazy parser scheduling.
2. Build worker interface for diff/highlight tasks.
3. Replace full recompute command-output path with incremental tail algorithm.

## Runtime Controls

Environment flags:

1. `VITE_PTM_PHASE11_HEAVY_COMPUTE_MODE` (`off` | `shadow` | `on`)
2. `VITE_PTM_PHASE11_WORKER_DIFF_THRESHOLD_CHARS`
3. `VITE_PTM_PHASE11_WORKER_TIMEOUT_MS`

Default worker offload thresholds:

1. payload size `>= 8 KB`, or
2. payload line count `>= 400`.

Mode semantics:

1. `off`: sync path only.
2. `shadow`: worker executes but UI applies sync artifacts only.
3. `on`: worker apply is allowed only when version-token freshness check passes.

## Quality Gates

1. Main-thread health:
   - reduced long tasks during heavy diff/markdown streams.
2. Render correctness:
   - parsed output remains equivalent to baseline.
3. Fallback reliability:
   - worker failure path remains functional.

## Test Plan

1. Unit tests:
   - incremental tail update correctness.
   - worker message protocol and error fallback.
2. Integration tests:
   - large diff and large markdown scenarios.
3. Manual checks:
   - UI remains interactive while heavy content arrives.

Gate harness scripts:

1. `scripts/phase11_heavy_payload_profile.py`
2. `scripts/phase11_worker_versioning_tests.py`
3. `scripts/phase11_heavy_content_interaction_smoke.py`
4. `scripts/phase11_gate_report.py`

## Risks and Mitigations

1. Risk: worker serialization overhead offsets gains for small payloads.
   - Mitigation: threshold-based worker offload.
2. Risk: ordering mismatch between async worker results and live stream.
   - Mitigation: version token per item update and stale result discard.

## Handoff to Phase 12

After compute offload, data volume governance can further reduce rendering pressure at source.


## Effort Estimate

- Size: Large
- Estimated duration: 6-8 engineering days
- Suggested staffing: 1 frontend primary + 1 backend/desktop support
- Confidence level: Medium (depends on current code-path complexity and test debt)





