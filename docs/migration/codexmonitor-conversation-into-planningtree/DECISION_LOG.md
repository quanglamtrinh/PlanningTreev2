# Decision Log

## Locked Decisions Imported From Plan 1
- Migrate only the core conversation and chat experience.
- Use one shared conversation surface embedded inside ask, planning, and execution.
- Keep PlanningTree breadcrumb, thread, task, brief, and spec concepts intact.
- Task, brief, and spec are read-only context in this migration phase.
- Use a thin gateway, not direct frontend-to-app-server communication.
- Use a per-project or per-workspace persistent session model.
- Persist normalized rich messages as the durable truth model.
- Support retry, continue, regenerate, cancel, concurrency, reconnect, and replay.

## Refinements Added While Formalizing Plan 1
- `conversation_id` is lazily created on first new-path initialization for a `(project_id, node_id, thread_type)` tuple.
- In this migration phase, each tuple owns exactly one canonical `conversation_id`.
- `thread_type` and `runtime_mode` are separate fields with different responsibilities.
- Raw event logs are not the durable replay source of truth.
- `event_seq` is a reconnect cursor only.
- Hot-path forwarding is forward-first, persist-after.
- Approval requests, runtime input requests, terminal states, and lineage transitions must flush promptly.
- Planning composer is disabled by default for the initial cutover phase only; future enablement is a later product decision.
- No shell creep rule is explicit and mandatory.
- Phase 2 remains backend-only and execution-only.
- Phase 2 introduces only the execution-scoped conversation-v2 `get`, `send`, and `events` slice.
- Phase 2 snapshot reads are durable-store-first and may enrich with live ownership metadata.
- Phase 2 send-start creates a stable assistant placeholder message and stable `assistant_text` part for all delta and final updates of the turn.
- Execution-specific single-active orchestration is a per-conversation policy and is kept separate from infrastructure-level session reuse and concurrency capability.
- No public `cancel`, `retry`, `continue`, or `regenerate` routes are added in Phase 2.

## Chosen Tradeoffs
- Prefer `reimplement_with_reference` for native and process-bound CodexMonitor pieces rather than direct code copy.
- Add conversation-v2 in parallel instead of replacing the current path immediately.
- Replace singleton frontend state early with keyed state foundations to avoid overfitting later phases to the old path.
- Introduce a dedicated conversation store rather than forcing rich data into `thread_state.json`.

## Rejected Alternatives
- Rejected: direct frontend-to-`codex-app-server` transport.
  - Reason: violates the locked thin gateway boundary.
- Rejected: one global backend `codex-app-server` process for the whole app.
  - Reason: violates project or workspace isolation.
- Rejected: raw event log as replay storage.
  - Reason: conflicts with the normalized rich message truth model and increases hot-path coupling.
- Rejected: implicit migration of CodexMonitor shell components.
  - Reason: outside the locked scope and likely to destabilize PlanningTree wrappers.
- Rejected: using unlocked ownership snapshots for stream callbacks.
  - Reason: risks stale-stream races and half-updated ownership reads.
