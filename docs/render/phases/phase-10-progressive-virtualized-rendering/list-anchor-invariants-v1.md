# Phase 10 List Anchor Invariants v1

Status: Frozen entry artifact for `list_anchor_invariants_frozen`.

Date: 2026-04-13.

Phase: `phase-10-progressive-virtualized-rendering` (D03, D04, D09).

## 1. Purpose

Define non-negotiable anchor and ordering invariants for progressive and virtualized rendering, so Phase 10 performance changes cannot regress feed correctness.

## 2. Frozen Invariants

1. Deterministic ordering:
   - visible list order remains deterministic under batching, virtualization, prepend, and load-more paths.
2. Stable render identity:
   - virtualization keying must remain stable for unchanged grouped entries.
3. Prepend anchor preservation:
   - when older history is prepended, the reader-visible anchor item and on-screen position are preserved.
4. Load-more anchor preservation:
   - loading additional history must not jump current viewport unexpectedly.
5. Bottom pin correctness:
   - auto-scroll-to-bottom is only allowed when viewport is already near bottom before update.
6. Correctness fallback:
   - if invariant checks fail, runtime must switch to safe non-virtualized rendering mode.

## 3. Frozen Defaults

1. Virtualization unit is `groupedEntries` in v1.
2. Anchor correction is offset-based and applies on prepend/load-more deltas.
3. Correctness fallback is fail-closed (disable optimization, keep content correctness).

## 4. Contract Linkage

Primary contract:

- `docs/render/system-freeze/contracts/c5-frontend-state-contract-v1.md`

Phase governance:

- `docs/render/decision-pack-v1.md`
- `docs/render/phases/phase-10-progressive-virtualized-rendering/preflight-v1.md`
