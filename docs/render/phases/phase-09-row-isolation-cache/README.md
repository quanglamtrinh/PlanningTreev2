# Phase 09 - Row Isolation and Parse Cache

Status: Planned.

Scope IDs: D01, D02, D10.

Subphase workspace: ./subphases/.


## Objective

Isolate row rendering so updates only affect changed rows, then cache parse-heavy artifacts with stable keys.

## In Scope

1. D01: Memoize V3 row components.
2. D02: Stable callback and prop identity.
3. D10: Cache by `itemId + updatedAt`.

## Detailed Improvements

### 1. Row memoization baseline (D01)

Apply `React.memo` to heavy row components with strict prop equality contracts.

### 2. Stable prop identity (D02)

Prevent unnecessary memo misses by:

- memoizing callbacks (`useCallback`)
- memoizing derived objects (`useMemo`)
- avoiding inline object/array literal recreation in hot render loops

### 3. Parse cache key policy (D10)

For markdown/diff/highlight output:

- cache key = `itemId + updatedAt + parseMode`
- invalidate only when relevant source changes

## Implementation Plan

1. Audit row prop shapes and remove unstable props.
2. Add memo wrappers and explicit comparator where needed.
3. Implement parse cache utility and integrate in heavy content pipeline.

## Quality Gates

1. Rerender reduction:
   - unchanged rows do not rerender on neighbor updates.
2. Cache efficiency:
   - parse cache hit ratio improves under streaming updates.
3. Correctness:
   - no stale render artifact after content update.

## Test Plan

1. Unit tests:
   - memo comparator behavior.
   - cache invalidation rules.
2. Component tests:
   - neighbor row updates do not rerender unaffected rows.
3. Manual profiling:
   - measure commit duration and rerender counts.

## Risks and Mitigations

1. Risk: over-memoization hides needed updates.
   - Mitigation: explicit update invariants and snapshot tests.
2. Risk: cache growth.
   - Mitigation: bounded LRU/TTL cache policy.

## Handoff to Phase 10

After row isolation, long-thread rendering strategy (progressive mount + virtualization) can be tuned with less noise.


## Effort Estimate

- Size: Medium
- Estimated duration: 4-5 engineering days
- Suggested staffing: 1 frontend primary
- Confidence level: Medium (depends on current code-path complexity and test debt)



