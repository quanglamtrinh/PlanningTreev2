# Phase 3 Entry Checklist

Use this checklist before starting consumer migration work on top of the Phase 2 backend core.

## Stable Phase 2 Contracts

- `thread_snapshot_store_v2` is the transcript source of truth
- `thread_registry_store` is the metadata source of truth
- `thread_event_projector` owns canonical item upsert and patch semantics
- `thread_runtime_service` owns turn lifecycle mutation
- `thread_query_service` owns ensure-and-read, reconciliation, and reset orchestration
- additive `/v2` routes and separate V2 brokers are the only supported consumer surface for new work

## Entry Checks

- [ ] read `docs/specs/conversation-streaming-v2.md` before changing any consumer behavior
- [ ] confirm no planned change requires reopening the V2 schema or route contract
- [ ] confirm the migration target uses a V2 abstraction instead of direct V1 session reads
- [ ] confirm no new item mutation path is being introduced outside `conversation.item.upsert` or `conversation.item.patch`
- [ ] confirm audit writes will migrate onto V2 abstractions instead of duplicating V1 append helpers
- [ ] confirm metadata-bearing changes will still synchronize through `thread.snapshot`
- [ ] review `artifacts/phase-2/projector-replay-matrix.md` before changing any projector-facing contract or consumer assumption

## Still Out of Scope for Phase 3

- frontend cutover to `/v2`
- deletion of V1 routes, stores, or semantic mapping files
- relaxing the no-shadow-execution rule for rehearsal or cutover
