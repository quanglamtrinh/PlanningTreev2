# Phase 6 Umbrella Plan: Performance, Concurrency, Replay, And Cleanup

## Documentation And Artifact Role
- This file is the canonical Phase 6 scaffold for the external CodexMonitor-to-PlanningTree migration workstream.
- It is both:
  - the umbrella plan
  - the source template for Phase 6 tracking artifacts and subphase-specific docs
- Shared boundaries, invariants, gate rules, and whole-phase exit conditions are defined here first.
- Subphase docs inherit these rules and narrow them to their own scope.
- Subphase docs must refine this umbrella plan, not redefine Phase 6 from scratch.

## Summary
- Phase 6 is the hardening and closeout umbrella after feature migration phases are complete.
- It does not introduce new conversation semantics.
- It exists to make the migrated conversation-v2 platform:
  - fast enough on hot paths
  - stable under dense event volume
  - isolated under concurrent activity
  - replay-faithful under reconnect, refresh, reload, and restart
  - safe to clean up through explicit, gate-based removal

CodexMonitor source context is used for hotspot discovery and comparative hardening analysis only. It is not a requirement to restore source-specific shell architecture or non-target product behavior in PlanningTree.

## Entry Conditions
Phase 6 may begin only when:
- Phase 5 semantic work is complete enough that Phase 6 is not forced to redefine missing semantics.
- Any remaining semantic gaps are explicitly tracked as blockers or carve-outs.
- Baseline performance, replay, and reconnect behavior is captured before optimization or cleanup begins.
- Rollback boundaries from prior phases remain understood before removal work starts.

## Cross-Subphase Invariants
- Durable normalized conversation state remains the replay source of truth.
- No Phase 6 work may silently redefine unresolved Phase 5 semantics.
- Performance optimization must preserve semantic equivalence.
- Reconnect hardening must remain durable-store-first.
- Cleanup must be gate-based and rollback-aware.
- Replay fidelity means the durable replay path reconstructs the same semantic conversation state as the live path, even when event ordering, reconnect timing, or guarded refresh behavior differ.

## Positioning
By the start of Phase 6:
- execution is already the native durable reference path on the migration target
- ask and planning are already embedded on the shared surface on the migration target
- advanced semantics are already implemented to the degree required by Phase 5

Phase 6 is not a semantic-expansion phase. It is a hardening and cleanup phase.

## Out Of Scope
- new conversation semantics
- new lineage or action behavior beyond what Phase 5 already defines
- shell migration
- breadcrumb artifact write-back
- broad architecture rewrites disguised as cleanup
- speculative compatibility removal before validation gates pass

## Source Context Anchors
Use current CodexMonitor source context to identify likely hotspots and risk areas:
- `docs/codebase-map.md`
- `docs/app-server-events.md`
- `src/services/events.ts`
- `src/features/app/hooks/useAppServerEvents.ts`
- `src/features/threads/hooks/useThreads.ts`
- `src/features/threads/hooks/useThreadsReducer.ts`
- `src/features/threads/hooks/useThreadActions.ts`
- `src/features/app/hooks/useRemoteThreadLiveConnection.ts`

These anchors are comparative inputs for Phase 6 hardening analysis only. They do not override the migration target's durable-store-first contract.

## Scope
Phase 6 covers:
- latency improvements on snapshot, stream, reducer, normalization, and render paths
- dense-event hardening for long or high-frequency conversations
- concurrent stream validation across multiple threads and conversations
- reconnect hardening and replay fidelity checks under stress
- compatibility cleanup after explicit gates pass
- migration closeout artifacts for removed compatibility paths and surviving permanent architecture

## Intended Subphase Shape
Phase 6 is split into:
- Phase 6.1 - Performance And Dense-Event Hardening
- Phase 6.2 - Concurrency, Reconnect, And Replay Robustness
- Phase 6.3 - Compatibility Cleanup And Gate-Based Removal

This umbrella plan defines the shared boundary and exit rules for all three.

## Artifact Package And Tracking Rules
Default Phase 6 artifact package:
- `PHASE_6_PLAN.md`
- `PHASE_6_PROGRESS.md`
- `PHASE_6_BATCHES.md`
- `PHASE_6_VALIDATION.md`
- `PHASE_6_OPEN_ISSUES.md`
- `PHASE_6_CHANGELOG.md`
- `PHASE_6_CLEANUP_LOG.md`

Derived subphase docs:
- `PHASE_6_1_PLAN.md`
- `PHASE_6_1_PROGRESS.md`
- `PHASE_6_1_VALIDATION.md`
- `PHASE_6_1_OPEN_ISSUES.md`
- `PHASE_6_2_PLAN.md`
- `PHASE_6_2_PROGRESS.md`
- `PHASE_6_2_VALIDATION.md`
- `PHASE_6_2_OPEN_ISSUES.md`
- `PHASE_6_3_PLAN.md`
- `PHASE_6_3_PROGRESS.md`
- `PHASE_6_3_VALIDATION.md`
- `PHASE_6_3_OPEN_ISSUES.md`

Artifact rules:
- `PHASE_6_PLAN.md` is the umbrella source of truth for entry conditions, invariants, gate model, and whole-phase exit conditions.
- Subphase plans narrow umbrella scope and must not restate Phase 6 from scratch.
- `PHASE_6_BATCHES.md` must use subphase-prefixed batch IDs:
  - `P6.1.a`, `P6.1.b`
  - `P6.2.a`, `P6.2.b`
  - `P6.3.a`, `P6.3.b`
- `PHASE_6_CHANGELOG.md` must record every material status, gate, or cleanup/removal change and should reference:
  - affected subphase
  - files or artifacts changed
- `PHASE_6_CLEANUP_LOG.md` is mandatory for Phase 6.3.

## Gate Model
Default gate prefixes:
- `P6.1-G*` for performance and dense-event gates
- `P6.2-G*` for concurrency, reconnect, and replay robustness gates
- `P6.3-R*` for cleanup and removal entries

Gate rules:
- Phase 6.1 improvements must be claimed against recorded baseline evidence on the same migrated path category; relative improvement claims without a recorded baseline are insufficient.
- Cleanup removal is allowed only when the exact enabling gate evidence is named.
- Every removal in `PHASE_6_CLEANUP_LOG.md` must reference the exact validation gate evidence that permits the removal.
- Removal without named gate evidence is not allowed.

## Subphase Shape
### Phase 6.1 - Performance And Dense-Event Hardening
Purpose:
- harden snapshot, stream, reducer, normalization, and render hot paths without changing semantics

Default scope:
- snapshot load cost
- event parsing and fanout overhead
- reducer throughput under dense event volume
- render-model and transcript rendering cost
- long-conversation memory pressure
- mixed passive, interactive, and lineage-bearing transcript stress

Rules:
- correctness-first, not speed-first
- no batching, memoization, truncation, or virtualization may change semantic outcome
- measured gains must be compared against recorded baseline evidence on the same migrated path class

### Phase 6.2 - Concurrency, Reconnect, And Replay Robustness
Purpose:
- prove isolation and durable-store-first fidelity under concurrent activity, disconnects, reconnects, refreshes, reloads, and restart

Default scope:
- cross-thread and cross-conversation isolation
- wrong-stream and wrong-thread attachment prevention
- reconnect under load
- missed-event recovery
- refresh, reload, and restart replay fidelity
- stress validation of visible host switching and active-stream recovery

Rules:
- validation must prove isolation, not just lack of crashes
- reconnect improvements may optimize recovery, but durable replay remains authoritative
- memory-only live state must never become replay authority

### Phase 6.3 - Compatibility Cleanup And Gate-Based Removal
Purpose:
- remove transitional compatibility behavior only after replacement paths are already validated under Phase 6.1 and Phase 6.2 gates

Default scope:
- legacy adapters
- duplicate routing
- shadow state
- redundant reconnect paths
- temporary migration compatibility layers

Rules:
- each removal must name its replacement path
- each removal must record rollback impact
- permanent architecture must be separated explicitly from transitional code
- cleanup proceeds in bounded slices, never a big-bang sweep
- every cleanup-log entry must classify the target as one of:
  - transitional and removable
  - transitional but blocked
  - intentionally permanent compatibility
  - uncertain classification requiring decision

Cleanup-log minimum fields:
- removal ID
- target path or behavior
- classification
- replacement path
- enabling gate reference
- rollback impact
- status
- notes on why removal is safe

## Overall Completion Rule
Phase 6 is not complete until all of the following are true:
- performance and dense-event behavior are acceptable on the conversation-v2 path
- reconnect and replay remain faithful under concurrent activity and stress
- compatibility cleanup is completed only where rollback risk is no longer material
- no required migration-critical path still depends on transitional compatibility behavior that Phase 6 intends to remove

## Risks
- performance work accidentally changes semantics
- dense-event optimization hides replay drift
- hidden concurrency bugs appear only under mixed host activity
- reconnect hardening introduces state desynchronization
- cleanup happens before validation gates are actually satisfied
- compatibility code is removed while a host still depends on it implicitly
- rollback assumptions become invalid after cleanup

## Acceptance Criteria
Phase 6 is complete when:
- conversation-v2 performance is acceptable on the main migrated paths under realistic load
- dense-event transcripts remain semantically stable and replay-faithful
- multiple concurrent conversations or streams remain isolated without cross-cancel or cross-attachment
- reconnect and replay remain faithful under stress and after restarts
- compatibility cleanup is explicitly documented, validated, and gated
- no remaining migration-critical host path silently depends on compatibility behavior that was supposed to be removed
- cleanup does not materially reduce rollback confidence until the corresponding gate explicitly allows that reduction
- migration docs clearly record what remains permanent architecture versus what was transitional and removed

## Verification
Phase 6 verification should include:
- latency sanity checks on snapshot load, event application, and transcript rendering
- dense-event stress checks
- long-transcript replay checks
- concurrent stream and cross-thread isolation checks
- reconnect under load checks
- replay fidelity checks after refresh, reload, and restart
- cleanup gate checklist before each removal step
- documentation review proving removed compatibility paths were intentional and validated

## Rollback And Cleanup Boundary
Before cleanup gates pass:
- rollback paths must remain intact where still needed
- compatibility layers may remain temporarily even if redundant

After cleanup gates pass:
- removal may proceed in bounded steps
- each removal must name its replacement path
- each removal must record why rollback risk is acceptable

Phase 6 does not assume a single big-bang cleanup.

## Assumptions And Defaults
- This plan is for the external migration workstream; CodexMonitor is source context, not the implementation target.
- Phase 6 is hardening and cleanup only, not a semantic-expansion phase.
- Any unresolved Phase 5 semantic boundary remains explicit as a blocker or carve-out and is not silently absorbed into Phase 6.
- `PHASE_6_CLEANUP_LOG.md` is required by default, not optional.
