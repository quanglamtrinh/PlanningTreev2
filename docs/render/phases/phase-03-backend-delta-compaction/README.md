# Phase 03 - Backend Delta Compaction

Status: Planned.

Scope IDs: A01, A04, A08.

Subphase workspace: ./subphases/.


## Objective

Reduce raw event explosion by compacting hot-path deltas before projection, persistence, and publish.

## In Scope

1. A01: Delta coalescing window (target 30-100ms, default 50ms).
2. A04: Item-level patch compaction.
3. A08: No-op lifecycle/event suppression.

## Detailed Improvements

### 1. Short coalescing window (A01)

Group consecutive deltas by:

- `thread_id`
- `item_id`
- `patch_kind`

within a short time window so bursts are processed as smaller batches.

### 2. Patch compaction for same target (A04)

Merge compatible consecutive patches:

- text append + text append -> single append
- metadata set where value unchanged -> removed
- overlapping patch ranges -> normalized single patch

### 3. Suppress no-op transitions (A08)

Before publish:

- compare old/new lifecycle/status
- if no semantic change and no side-effect, skip event emission

## Implementation Plan

1. Add compaction stage in runtime service before projector/persist path.
2. Implement deterministic merge rules with order guarantees.
3. Add no-op guard in lifecycle transition publisher.
4. Expose counters for compacted vs raw events in logs/debug output.

## Quality Gates

1. Volume reduction:
   - significant drop in persisted/published events per turn.
2. Ordering integrity:
   - final rendered content matches non-compacted baseline.
3. Latency safety:
   - coalescing window does not create user-visible lag beyond target.

## Test Plan

1. Unit tests:
   - patch merge matrix (compatible/incompatible pairs).
   - no-op suppression guard cases.
2. Integration tests:
   - streamed turn with many micro deltas yields equivalent final state.
3. Manual checks:
   - verify typing/stream appearance remains smooth.

## Risks and Mitigations

1. Risk: over-compaction changes semantics.
   - Mitigation: strict merge whitelist and golden test snapshots.
2. Risk: coalescing adds perceived delay.
   - Mitigation: tune window, apply immediate flush on boundary events.

## Handoff to Phase 04

Reduced event volume lowers pressure on in-memory actor and checkpointing work in the next phase.


## Effort Estimate

- Size: Medium
- Estimated duration: 4-6 engineering days
- Suggested staffing: 1 backend primary + 1 reviewer
- Confidence level: Medium (depends on current code-path complexity and test debt)



