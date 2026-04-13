# C4 Mini-Journal Spec v1

Status: Frozen entry artifact for `mini_journal_spec_frozen`.

Owner: backend runtime actor + persistence layer.

Date: 2026-04-12.

## Purpose

Defines the minimum Phase 04 mini-journal contract required to satisfy durability and deterministic recovery before full hybrid persistence in Phase 05.

This spec is normative for Phase 04 and is referenced by:

- `docs/render/system-freeze/contracts/c4-durability-contract-v1.md`
- `docs/render/phases/phase-04-inmemory-actor-checkpointing/README.md`

## Required Record Contract

Each mini-journal record MUST be a JSON object with these fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `journalSeq` | integer | yes | Monotonic per `(projectId,nodeId,threadRole,threadId)`. |
| `projectId` | string | yes | Project scope key. |
| `nodeId` | string | yes | Node scope key. |
| `threadRole` | string | yes | Thread role (`plan`, `audit`, `ask_planning`, etc.). |
| `threadId` | string | yes | Runtime thread identity. |
| `turnId` | string | no | Present for turn-scoped boundaries. |
| `eventIdStart` | integer | yes | First event id covered by this boundary record. |
| `eventIdEnd` | integer | yes | Last event id covered by this boundary record. |
| `boundaryType` | string | yes | Must be in Boundary Type Set below. |
| `snapshotVersionAtWrite` | integer | yes | Snapshot version visible when the journal record is appended. |
| `createdAt` | string | yes | ISO-8601 UTC timestamp. |

## Boundary Type Set

Allowed values for `boundaryType`:

- `turn_completed`
- `turn_failed`
- `waiting_user_input`
- `eviction`
- `timer_checkpoint`

Any other value is contract-invalid for Phase 04.

## Ownership and Write Model

1. Actor is the single writer for thread mutation and mini-journal append.
2. Any mutation path that bypasses actor ownership is prohibited in Phase 04 mode.
3. Checkpoint boundaries MUST consume lifecycle transitions from C3 only.

## Public Interfaces (Phase 04)

Mini-journal store:

- `append_boundary_record(record) -> None`
- `read_tail_after(cursor) -> list[record]`
- `prune_before(cursor) -> int`

Checkpoint policy:

- `should_checkpoint(boundary_type, elapsed_ms, dirty_events_count) -> bool`

Default policy values:

- boundary types above always checkpoint
- periodic safety checkpoint interval default is `5000` ms

## Deterministic Recovery Contract

Recovery procedure is fixed:

1. Load latest persisted snapshot.
2. Load mini-journal tail records ordered by `journalSeq` after snapshot checkpoint cursor.
3. Replay records in strict `journalSeq` order to reconstruct boundary coverage.
4. Validate no gap in `journalSeq` and no invalid event range (`eventIdStart > eventIdEnd`).

If validation fails, recovery MUST fail closed with explicit error, not silent continuation.

## Crash-Loss Budget (Phase 04 Defaults)

1. Boundary loss target is `0` events for `turn_completed`, `turn_failed`, `waiting_user_input`, and `eviction`.
2. Non-boundary loss is bounded by checkpoint timer and defaults to <= `5000` ms of in-flight non-boundary progress.
3. Budget compliance must be verified by recovery fault-injection tests (P04-G3 source).

## Compatibility Constraints

1. No C1/C2 envelope/replay semantics changes are introduced by this spec.
2. No C3 lifecycle transitions are added or interpreted outside the frozen state machine.
3. This is a Phase 04 baseline spec only; Phase 05 may extend storage internals but must preserve these observable guarantees.
