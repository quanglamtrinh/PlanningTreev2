# Phase 09 - Row Isolation and Parse Cache

Status: Completed (all P09 gates passed with candidate-backed evidence).

Date: 2026-04-13.

Scope IDs: D01, D02, D10.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Uses CodexMonitor-style row isolation and stable props to reduce render fanout.

Contract focus:

- Primary: `C5` Frontend State Contract v1

Must-hold decisions:

- Cache invalidation keys remain contract-safe (`threadId + itemId + updatedAt + mode + rendererVersion`).
- Memoization does not suppress legitimate row updates.
- Row identity behavior remains stable for Phase 10 virtualization follow-up.

## Objective

Isolate row rendering so updates only affect changed rows, and add contract-safe parse artifact caching for markdown/reasoning/diff workloads.

Frozen entry artifact:

- `row-cache-invalidation-policy-v1.md`

## Implemented Scope

### 1. Row Memoization (D01)

Implemented row-level memoization in `MessagesV3` with explicit comparators for:

1. message rows
2. reasoning rows
3. tool rows
4. review/explore/diff/status/error/user-input rows

Outcomes:

- unchanged neighbor rows no longer rerender on unrelated updates
- row keys and ordering remain deterministic
- comparator rules prioritize correctness over over-aggressive skipping

### 2. Stable Props and Callbacks (D02)

Stabilized hot-path identities with `useMemo`/`useCallback` and removed avoidable inline prop churn in row rendering flow.

Key outcomes:

- stable `isExpanded` and handler identities passed to memoized rows
- stable synthetic file-change item derivation for diff/tool rows
- render fanout reduced without changing user-visible behavior

### 3. Parse Cache Production Path (D10)

Implemented in-memory parse artifact cache with frozen policy:

1. LRU max entries: `1500`
2. TTL: `10 minutes`
3. in-memory only (no `localStorage` persistence)

Canonical key source-of-truth:

- `frontend/src/features/conversation/components/v3/parseCacheContract.ts`
- `buildParseCacheKey(...)` used for all Phase 09 parse cache integration

Integrated cache paths:

1. message/review rendered text path in `MessagesV3`
2. reasoning summary/detail normalization in `messagesV3.utils`
3. file-change diff parsing/stats/line splitting in `FileChangeToolRow`

Thread lifecycle behavior:

- parse artifact cache resets by thread lifecycle transitions in `MessagesV3`

### 4. Profiling Guardrail Continuity

Pre-phase profiling hardening remains intact:

1. profiling is opt-in outside tests
2. profiling emits stay measurement-only
3. profiling state does not control production cache behavior

## Validation Snapshot

Implementation checks:

1. `npm run typecheck --prefix frontend` -> pass
2. `npm run test:unit --prefix frontend -- tests/unit/parseArtifactCache.test.ts tests/unit/messagesV3.profiling-hooks.test.tsx tests/unit/messagesV3.utils.test.ts tests/unit/MessagesV3.test.tsx` -> pass
3. `npm run check:render_freeze` -> pass

Phase 09 evidence generation:

1. `python scripts/phase09_row_render_profile.py --candidate ... --candidate-commit-sha <sha> --output ...` -> pass
2. `python scripts/phase09_parse_cache_trace.py --candidate ... --candidate-commit-sha <sha> --output ...` -> pass
3. `python scripts/phase09_ui_regression_suite.py --candidate ... --candidate-commit-sha <sha> --output ...` -> pass
4. `python scripts/phase09_gate_report.py --self-test --candidate ... --output ...` -> pass

## Exit Gates (P09)

Gate targets from `docs/render/system-freeze/phase-gates-v1.json`.

| Gate | Metric | Target | Current value | Status |
|---|---|---|---|---|
| P09-G1 | unchanged_row_rerender_rate_pct | `<= 5` | `4.333` | pass |
| P09-G2 | parse_cache_hit_rate_pct | `>= 60` | `65.0` | pass |
| P09-G3 | stale_render_artifact_incidents | `<= 0` | `0.0` | pass |

Gate artifacts:

1. `docs/render/phases/phase-09-row-isolation-cache/evidence/row_render_profile.json`
2. `docs/render/phases/phase-09-row-isolation-cache/evidence/parse_cache_trace.json`
3. `docs/render/phases/phase-09-row-isolation-cache/evidence/ui_regression_suite.json`
4. `docs/render/phases/phase-09-row-isolation-cache/evidence/phase09-gate-report.json`

## Residual Notes

1. Candidate evidence is currently fixture-backed for local closure rehearsal.
2. CI closeout should regenerate artifacts with CI candidate payloads and injected commit SHA.
3. Phase 10 can now focus on progressive/virtualized rendering with lower row-level invalidation noise.

## Closeout and Handoff

- `docs/render/phases/phase-09-row-isolation-cache/close-phase-v1.md`
- `docs/render/phases/phase-09-row-isolation-cache/handoff-to-phase-10.md`
