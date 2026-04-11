# PTM Render Optimization Decision Pack v1

Status: Approved baseline decisions for implementation.

Approved on: 2026-04-11.

Owner: PTM core engineering.

## 1. Purpose

This document freezes the decisions required to begin implementation of the A-E optimization phases without architecture drift.

It covers:

- blocker resolutions
- selected architecture model
- shared model/contracts to enforce
- answers to open decisions that affect implementation order and risk

## 2. Chosen Architecture Model

Selected model: `Goose-first hybrid`.

Definition:

- use Goose-style patterns for stream correctness and backend event/persistence flow
- use CodexMonitor-style patterns for frontend state shaping, render isolation, and queue UX

Why:

- PTM currently has high risk in stream/replay/persist correctness and event amplification, so backend/transport correctness must lead
- frontend optimizations are still required, but should be layered on top of stable stream contracts

## 3. Blocker Resolutions

### B0-1. No single source of truth contract

Decision:

- adopt schema-first event contracts in this wave
- enforce via shared types/schemas in backend and frontend
- include a minimal contract compatibility test set

Expected outcome:

- every phase implements against the same event/lifecycle definitions

### B0-2. Quality gate says "improve vs baseline" while Layer F is deferred

Decision:

- add thin telemetry only for phase pass/fail gates
- do not expand into full observability platform in this wave

Expected outcome:

- phase exits remain measurable without reopening full Layer F scope

### B0-3. Recovery gap between Phase 04 and Phase 05

Decision:

- Phase 04 will include mini-journal durability (minimum viable append log for recovery-critical boundaries)
- Phase 05 extends this into full hybrid persistence

Expected outcome:

- lower crash-loss risk before full persistence refactor lands

### B0-4. Coalescing ownership ambiguity

Decision:

- backend owns semantic coalescing as canonical source of truth
- frontend may batch apply/render for presentation performance only

Expected outcome:

- no dual semantic merge logic and no backend/frontend divergence

## 4. Shared Contracts (must be created and frozen before main implementation)

### C1. Event Stream Contract v1

Required fields:

- `schema_version`
- `event_id`
- `event_type`
- `thread_id`
- `turn_id` (nullable)
- `snapshot_version`
- `occurred_at_ms`
- `payload`

Rules:

- `event_id` is monotonic per thread
- `event_id` is durable across server restart for the same thread
- heartbeat does not affect replay cursor

### C2. Replay and Resync Contract v1

Rules:

- client reconnect uses `Last-Event-ID`
- server replays events with `event_id > last_event_id` when available
- if replay window is exceeded, server returns explicit replay-miss signal
- client executes targeted resync flow (not silent continuation)
- replay/live handoff must dedupe boundary overlap deterministically

### C3. Lifecycle and Gating Contract v1

Rules:

- single authoritative thread lifecycle state machine
- valid transitions are explicit and testable
- queue pause/resume policy consumes lifecycle states from this contract
- checkpoint boundary policy consumes lifecycle states from this contract

### C4. Durability Contract v1

Rules:

- checkpoint triggers are explicit (terminal events, gated states, timer, eviction)
- mini-journal write policy is explicit for crash recovery
- crash-loss budget is defined and accepted

### C5. Frontend State Contract v1

Rules:

- normalized state shape and operation types are explicit
- patch-on-hot-path must avoid global sort unless order changes
- unchanged branches preserve structural identity
- list keys/invariants support progressive + virtualized rendering safely

### C6. Queue Contract v1

Rules:

- deterministic queue state machine
- explicit pause/resume matrix by lifecycle/gating state
- queue controls include reorder/remove/send-now
- stale-intent handling policy is explicit (see section 5)

## 5. Final Answers to Open Decisions

### Q1. Event ID continuity across restart

Final decision:

- `event_id` must remain monotonic and durable per thread across restart

Rationale:

- required for safe replay and reconnect correctness

### Q2. Phase 04 durability mode

Final decision:

- do not run snapshot-only in Phase 04
- include mini-journal in Phase 04
- expand to full hybrid persistence in Phase 05

### Q3. Coalescing ownership

Final decision:

- backend semantic coalescing is canonical
- frontend only does frame/presentation batching

### Q4. Re-confirm before queued send after long delay

Final decision:

- use risk-based confirmation policy (not always-confirm, not always-auto-send)

Default policy baseline:

- auto-send allowed for short queue age and low-risk context
- re-confirm required when queue age exceeds threshold or context changed significantly

### Q5. Phase pass/fail strictness

Final decision:

- use balanced gates

Balanced gate intent:

- meaningful improvement required per phase
- no major adjacent regressions allowed
- correctness and stability are hard requirements

## 6. Minimum Gate Framework (balanced baseline)

Phase groups and baseline expectations:

- Stream reliability phases (1-2): high reconnect replay success and zero duplicate apply at boundaries
- Backend efficiency phases (3-5): significant reduction in event/persist pressure without stream regressions
- Frontend state phases (6-8): significant drop in apply churn and invalidation fanout
- Render phases (9-11): clear reduction in long tasks and improved large-thread responsiveness
- Data/queue phases (12-13): bounded memory behavior and deterministic queue correctness

Note:

- exact numeric thresholds are defined in phase-level technical design notes before coding each phase

## 7. Implementation Guardrails

- do not introduce phase logic that violates contracts C1-C6
- do not move semantic coalescing responsibility to frontend
- do not merge replay behavior changes without replay boundary tests
- do not close a phase without passing quality gates and documenting trade-offs

## 8. Change Control

Any change to decisions in this document requires:

1. explicit proposal in `docs/render/`
2. impact note on phase ordering/risk
3. approval before implementation divergence

