# Phase 04 Preflight v1

Status: Frozen implementation preflight.

Date: 2026-04-12.

Phase: `phase-04-inmemory-actor-checkpointing` (A02, A03).

## 1. Entry Criteria Lock

`phase_03_passed` evidence:

- `docs/render/phases/phase-03-backend-delta-compaction/evidence/phase03-gate-report.json`
- `P03-G1=46.7391304347826`, `P03-G2=0`, `P03-G3=34.7`

`mini_journal_spec_frozen` artifact:

- `docs/render/system-freeze/contracts/c4-mini-journal-spec-v1.md`

## 2. Frozen Decisions for Implementation

1. Ownership:
   - actor runtime is single writer for mutation and mini-journal append in Phase 04 mode.
2. Recovery:
   - deterministic recovery path is `latest snapshot -> mini-journal tail ordered by journalSeq`.
   - gap/invalid-range detection fails closed.
3. Crash-loss budget defaults:
   - boundary loss target is `0` events.
   - non-boundary loss bounded by timer checkpoint default `5000` ms.

## 3. Rollout Mode Contract

Feature flag: `thread_actor_mode`

- `off`: current non-actor flow (default)
- `shadow`: actor path runs in validation mode without serving authoritative writes
- `on`: actor path is authoritative single-writer path

Default for Phase 04 implementation start: `off`.

## 4. Compatibility and Non-Goals

Compatibility lock:

- no C1 envelope shape or event identity semantics change
- no C2 replay protocol or cursor semantics change
- no C3 lifecycle state set or legal transition change

Non-goals for this wave:

- no Layer F observability expansion
- no Layer G rollout/safety expansion beyond the explicit `thread_actor_mode` contract above

## 5. Gate and Evidence Lock

Phase 04 gate harness:

- `scripts/phase04_gate_report.py`
- canonical output: `docs/render/phases/phase-04-inmemory-actor-checkpointing/evidence/phase04-gate-report.json`

Required evidence inputs:

- `backend-runtime-benchmark.json`
- `recovery-fault-injection.json`

## 6. Preflight Exit

No open blocker questions remain for Phase 04 implementation kickoff under the frozen contracts and defaults in this document.
