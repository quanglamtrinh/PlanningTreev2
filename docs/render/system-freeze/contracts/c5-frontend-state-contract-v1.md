# C5 Frontend State Contract v1

Status: Frozen frontend state and render correctness contract.

Owner: frontend conversation store + render layers.

## Scope

Defines normalized state shape, hot-path update rules, structural identity guarantees, and render invariants for progressive/virtualized views.

## Required Behaviors

1. State shape supports normalized access patterns.
2. Patch hot path must avoid global sort unless order changes.
3. Unchanged branches preserve object identity for memo effectiveness.
4. Render keys and ordering remain deterministic under batching/virtualization.
5. Presentation optimizations do not mutate canonical semantics.

## Performance-Safe Rules

- frame batching is apply/render batching only
- memoization must not suppress true content updates
- cache invalidation must key by data freshness fields (`itemId + updatedAt + mode`)

## Prohibited Behaviors

- frontend semantic coalescing that can diverge from backend canonical state
- forced reload without explicit mismatch/corruption classification
- unstable keying that breaks anchor/scroll integrity

