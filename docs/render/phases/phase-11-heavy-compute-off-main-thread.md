# Phase 11 - Heavy Compute Off Main Thread

Status: Planned.

Scope IDs: D05, D06, D07.

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

## Risks and Mitigations

1. Risk: worker serialization overhead offsets gains for small payloads.
   - Mitigation: threshold-based worker offload.
2. Risk: ordering mismatch between async worker results and live stream.
   - Mitigation: version token per item update and stale result discard.

## Handoff to Phase 12

After compute offload, data volume governance can further reduce rendering pressure at source.

