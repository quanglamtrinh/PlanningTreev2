# Phase 0 Deferred Backlog Guard

Status: completed.

Purpose: record explicitly deferred scope so Phase 1+ does not absorb non-locked requirements.

## Deferred items (out of current track)

1. Workspace/project filter in Usage Snapshot UI.
2. SSE or push-based live usage updates for this screen.
3. Persistent aggregate store/database for historical usage snapshots.
4. Advanced drill-down views (per-model timeline, per-session table, export).
5. Cross-device or remote aggregation logic.

## Reason for deferral

- Keeps current rollout additive and low-risk.
- Preserves compatibility with existing codex account snapshot flows.
- Minimizes implementation decisions in Phase 1.

## Earliest candidate phase for reassessment

- After Phase 7 closeout as follow-up roadmap items.

## Scope guard rule

- Any request matching deferred items must be logged as follow-up and must not change Phase 1 implementation contract unless a new explicit phase decision is approved.
