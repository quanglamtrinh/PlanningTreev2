# Phase 09 - Row Isolation and Parse Cache

Status: Planned (pre-phase hardening baseline prepared).

Scope IDs: D01, D02, D10.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Uses CodexMonitor-style row isolation and stable props to reduce render fanout.

Contract focus:

- Primary: `C5` Frontend State Contract v1

Must-hold decisions:

- Cache invalidation keys must stay contract-safe (`threadId + itemId + updatedAt + mode + rendererVersion`).
- Memoization cannot suppress legitimate row updates.
- Row identity behavior must remain stable for later virtualization phases.


## Objective

Isolate row rendering so updates only affect changed rows, then cache parse-heavy artifacts with stable keys.

Implementation scope authority:

- Implementation scope for this phase is `D01`, `D02`, `D10` from `docs/render/system-freeze/phase-manifest-v1.json`.
- Phase 08 handoff is input context only and does not redefine Phase 09 scope IDs.

## In Scope

1. D01: Memoize V3 row components.
2. D02: Stable callback and prop identity.
3. D10: Cache by canonical key contract (`threadId + itemId + updatedAt + mode + rendererVersion`).

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

- cache key = `threadId + itemId + updatedAt + parseMode + rendererVersion`
- invalidate only when relevant source changes

## Pre-Phase 09 Hardening Baseline

### 1. Frozen entry artifact

- `row-cache-invalidation-policy-v1.md` is the Phase 09 entry artifact for `row_cache_invalidation_policy_frozen`.

### 2. Frozen frontend contract utility

- `frontend/src/features/conversation/components/v3/parseCacheContract.ts` defines:
  - `ParseCacheMode`
  - `ParseCacheKeyInput`
  - `buildParseCacheKey`
  - `CACHE_SCHEMA_VERSION`
  - default Phase 09 policy constants (`LRU=1500`, `TTL=10m`, renderer version `v1`)

### 3. Profiling-only instrumentation hooks

- `frontend/src/features/conversation/components/v3/messagesV3ProfilingHooks.ts` provides test-only hooks for:
  - row render profiling
  - parse trace hit/miss telemetry

Guardrail:

- hooks are measurement-only and must not change user-visible behavior.

### 4. Gate harness and evidence contract

Phase 09 source scripts:

1. `scripts/phase09_row_render_profile.py`
2. `scripts/phase09_parse_cache_trace.py`
3. `scripts/phase09_ui_regression_suite.py`
4. `scripts/phase09_gate_report.py`

Evidence workspace:

- `docs/render/phases/phase-09-row-isolation-cache/evidence/`

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





