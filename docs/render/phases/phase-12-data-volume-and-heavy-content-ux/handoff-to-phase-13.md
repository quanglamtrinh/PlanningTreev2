# Handoff to Phase 13

Status: Ready for queue-flow implementation.

From phase: `phase-12-data-volume-and-heavy-content-ux`.

To phase: `phase-13-queued-follow-up-flow`.

## What Phase 12 Guarantees

1. Active live feed is bounded by scrollback hysteresis policy.
2. Older history is recoverable through deterministic sequence-cursor pagination.
3. Heavy payload rows default to collapsed without hiding full payload access.
4. Preview/truncation remains presentation-only.
5. Backend compaction boundaries remain deterministic and lifecycle-safe.

## Inputs Phase 13 Can Rely On

1. Stable snapshot contract additions:
   - optional `live_limit` query
   - optional `historyMeta` payload
2. Stable history API:
   - `/history` endpoint with `before_sequence` cursor
3. Stable UI affordances:
   - top-level load-more action
   - full artifact modal path for heavy payload inspection

## Known Non-Goals Kept Deferred

1. No new observability-specific instrumentation in this phase.
2. No rollout/safety experimentation layer changes in this phase.

## Risks to Watch in Phase 13

1. Queue re-send/reorder UX must not break history anchor behavior under prepend.
2. Queue automation should not assume heavy rows are expanded by default.
3. Queue policy updates must preserve replay/resync cursor contract.
