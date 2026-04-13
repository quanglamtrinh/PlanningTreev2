# Phase 07 Normalized State Shape v1

Status: Frozen entry artifact for `normalized_state_shape_frozen`.

Date: 2026-04-13.

Owner: frontend conversation state pipeline.

## 1. Purpose

Freeze the canonical state model and update rules before implementation so Phase 07 can optimize hot paths without behavior drift.

This artifact defines:

- normalized model shape (`itemsById`, `orderedItemIds`, `uiSignals`)
- operation taxonomy (`insert`, `reorder`, `patch-content`, `patch-meta`)
- deterministic order-change rules
- structural sharing guarantees
- compatibility adapter boundary for `snapshot.items`
- non-goals for Phase 07

## 2. Canonical Model

Internal canonical model for apply/reducer logic:

```ts
type ThreadSnapshotNormalizedV1 = {
  threadId: string
  snapshotVersion: number
  activeTurnId: string | null
  processingState: string
  itemsById: Record<string, ConversationItemV3>
  orderedItemIds: string[]
  uiSignals: ThreadSnapshotV3["uiSignals"]
}
```

Required invariants:

1. Every `orderedItemIds[i]` must exist in `itemsById`.
2. `orderedItemIds` must not contain duplicates.
3. Order is deterministic for the same event stream.
4. `uiSignals` remains non-conversation state and does not own canonical item semantics.

## 3. Operation Taxonomy

Allowed operation types in reducer/apply pipeline:

1. `insert`: add a new item id and item payload.
2. `reorder`: change item order without changing item content.
3. `patch-content`: patch user-visible content fields for an existing item.
4. `patch-meta`: patch metadata/status/timestamps for an existing item.

Rules:

1. `insert` and `reorder` may change `orderedItemIds`.
2. `patch-content` and `patch-meta` must not trigger global list sort.
3. Unknown operation intent must fail closed (fallback path), not silently mutate ordering.

## 4. Order-Changed Rule

An event is considered `order_changed = true` only when one of these is true:

1. A new id is inserted into `orderedItemIds`.
2. An existing id changes relative position due to explicit reorder semantics.

Default deterministic comparator policy for sort-required paths:

1. `sequence` ascending
2. `createdAt` ascending
3. `id` ascending (final tie-breaker)

`patch-content` and `patch-meta` are `order_changed = false` by default.

## 5. Structural Sharing Guarantees

Required identity rules:

1. If no item payload changed, unchanged entries in `itemsById` keep the same object reference.
2. If order did not change, `orderedItemIds` keeps the same array reference.
3. If `uiSignals` did not change, `uiSignals` keeps the same object reference.
4. Reducer must not clone full state branches unless the branch is actually modified.

These guarantees are mandatory for C5 memoization and render isolation readiness.

## 6. Adapter Boundary (`snapshot.items`)

Compatibility policy for Phase 07:

1. Internal reducer uses normalized model as canonical.
2. External/UI compatibility keeps `snapshot.items` available through adapter mapping from `orderedItemIds + itemsById`.
3. Adapter must preserve current display order semantics and stable keys.
4. Adapter does not introduce semantic coalescing or replay behavior changes.

This keeps current UI and tests stable while Phase 07 migrates internals.

## 7. Non-Goals (Phase 07)

Out of scope for this phase:

1. Backend stream contract changes (`C1`, `C2`, `C4` semantics remain unchanged).
2. Observability/rollout safety layers beyond existing gate evidence tooling.
3. Store split, selector fanout isolation, virtualization strategy changes (handled in later phases).

## 8. Evidence and Baseline Protocol

Evidence files for Phase 07 use fixed names:

1. `state_hot_path_benchmark.json`
2. `state_hot_path_trace.json`
3. `reducer_identity_tests.json`
4. `phase07-gate-report.json`

Baseline source for comparisons:

- `docs/render/phases/phase-07-state-shape-hot-path/evidence/baseline-manifest-v1.json`

Baseline manifest must include:

1. Phase 06 closing commit reference.
2. Phase 06 closeout document reference.
3. Phase 06 gate report reference.
4. Minimum environment fingerprint (OS, shell, Python version).

