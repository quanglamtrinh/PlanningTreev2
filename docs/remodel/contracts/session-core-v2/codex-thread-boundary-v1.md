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

## Phase 0-1 Guard Status

Status: guarded, no behavior switch yet.

Baseline recorded 2026-04-26:

- `python -m pytest backend/tests/unit/test_workflow_v2_thread_binding.py backend/tests/unit/test_session_v2_protocol_compat_gate.py backend/tests/integration/test_workflow_v4_ensure_thread.py` -> pass (`14 passed`).

Phase 1 guard coverage:

- `ThreadBindingServiceV2.ensure_thread` remains the workflow-owned boundary for creating, adopting, updating, and replaying role bindings.
- `/v4/session/*` route paths are guarded against workflow path params such as `projectId`, `nodeId`, and `role`.
- Session runtime request schemas reject top-level PlanningTree-only fields (`projectId`, `nodeId`, `role`, `idempotencyKey`).
- Breadcrumb V2 is guarded against legacy V3/chat transcript APIs and must render/submit through `useSessionFacadeV2`.

Deprecated compatibility endpoint:

- `/v4/session/threads/{threadId}/recover` has been removed from Session V4. Recovery/backfill remains an internal adapter concern and is not exposed via client-facing HTTP.

## Phase 2-3 Guard Status

Status: shadow read path added, UI recover dependency soft-removed.

Phase 2 read modes:

- `SESSION_CORE_V2_THREAD_READ_MODE=native` preserves native rollout-backed `thread/read`, `thread/resume`, and `thread/turns/list` responses as rollback mode.
- `SESSION_CORE_V2_THREAD_READ_MODE=shadow` calls the Codex provider read/resume/turns path after native succeeds, returns native, and logs minimal diff telemetry (`threadId`, method, turn counts, status mismatch, missing side, provider error).
- `SESSION_CORE_V2_THREAD_READ_MODE=codex` returns provider responses where available and falls back to native rollout on provider failure or unsupported `thread/turns/list`.

Phase 3 UI behavior:

- `resyncThreadTranscript(threadId, { recoverFromProvider })` kept the option for compatibility, but normal resync hydrated with `thread/read(includeTurns=true)` and reopened the event stream.
- Breadcrumb V2 tab switch and `visibilitychange` resync no longer pass `recoverFromProvider`.
- `recoverThreadFromProvider` and `/v4/session/threads/{threadId}/recover` are removed from client-facing surfaces.

## Phase 4-5 Guard Status

Status: Codex default, native rollback available.

Phase 4 recover hardening:

- `resyncThreadTranscript(threadId)` no longer accepts `recoverFromProvider`.
- Session facade/runtime controller no longer expose `recoverThreadFromProvider`.
- `/v4/session/threads/{threadId}/recover` is no longer exposed.

Phase 5 read source:

- `SESSION_CORE_V2_THREAD_READ_MODE=codex` is the default production read path.
- `SESSION_CORE_V2_THREAD_READ_MODE=native` remains the rollback mode.
- `SESSION_CORE_V2_THREAD_READ_MODE=shadow` remains available for native/provider diff telemetry.
- Native rollout is retained as journal/replay safety net and fallback source, but no longer the default render source below `threadId`.
