# Codex Thread Boundary

PlanningTree owns only the workflow binding boundary:

```text
projectId + nodeId + role -> threadId
```

`ThreadBindingServiceV2` may create or adopt a thread, persist the binding, inject workflow context, and expose workflow-specific business actions. Once a caller has a `threadId`, every session operation must use Codex app-server semantics and must not require `projectId`, `nodeId`, or `role`.

## Invariant Checklist

- Workflow APIs may accept `projectId`, `nodeId`, and `role` to resolve a lane to a `threadId`.
- Session APIs under `/v4/session` are `threadId` scoped only.
- `turn/start`, `turn/steer`, `turn/interrupt`, and `thread/inject_items` must not require PlanningTree-only idempotency fields.
- Workflow idempotency stays in workflow state records, not in the thread runtime protocol.
- Workflow context injection uses `thread/inject_items` with raw Codex `ResponseItem` payloads.
- Rendering reads, resumes, streams, and submits by `threadId`; workflow state can still decide which lane is active.
