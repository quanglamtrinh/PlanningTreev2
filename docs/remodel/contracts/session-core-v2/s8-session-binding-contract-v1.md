# S8 Session Binding Contract v1 (Reserved Post-Core)

Status: Reserved (Phase 2+ integration)

This contract reserves stable integration points between business workflow state and Session Core V2.

## Ownership boundary

1. Session core owns protocol/runtime semantics for Thread/Turn/Item.
2. Business workflow owns ask/execution/audit policy and operator gating.
3. Binding must be additive metadata only.

## Thread metadata bindings

Reserved thread metadata keys:

1. `metadata.domain.projectId`
2. `metadata.domain.nodeId`
3. `metadata.domain.phase` (`ask` | `execution` | `audit`)
4. `metadata.lineage.parentThreadId`
5. `metadata.lineage.forkedAtEventSeq`

## Turn metadata bindings

Reserved turn metadata namespace:

1. `turn.metadata.domain.*`

Session core stores these values but never interprets business semantics.

## Lineage rules

1. Any business branch operation must use native `thread/fork`.
2. Manual transcript cloning in business layer is prohibited.
3. Lineage metadata must be written at fork creation time.

## Compatibility requirements

1. Missing domain metadata must not break core runtime behavior.
2. Binding evolution must be backward-compatible for existing threads.

