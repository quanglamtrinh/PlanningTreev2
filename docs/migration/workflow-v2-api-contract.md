# Workflow V2 API Contract

Workflow V2 routes are separate from Session Core V2. Session runtime remains
under `/v4/session/*`; workflow business routes use:

```text
/v4/projects/{projectId}/nodes/{nodeId}/...
```

All mutating endpoints should accept an idempotency key. The preferred shape is
an `idempotencyKey` body field; route handlers may also accept an
`Idempotency-Key` header if useful.

## State Response

`GET /v4/projects/{projectId}/nodes/{nodeId}/workflow-state`

Response:

```json
{
  "projectId": "p1",
  "nodeId": "n1",
  "phase": "review_pending",
  "version": 42,
  "threads": {
    "askPlanning": "thread_ask",
    "execution": "thread_exec",
    "audit": "thread_audit",
    "packageReview": null
  },
  "decisions": {
    "execution": {
      "status": "completed",
      "candidateWorkspaceHash": "sha256:...",
      "headCommitSha": "abc"
    },
    "audit": null
  },
  "context": {
    "frameVersion": 2,
    "specVersion": 1,
    "splitManifestVersion": 3,
    "stale": false,
    "staleReason": null
  },
  "allowedActions": [
    "review_in_audit",
    "mark_done_from_execution"
  ]
}
```

## Ensure Thread

`POST /v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/ensure`

Path `role` values:

- `ask_planning`
- `execution`
- `audit`
- `package_review`

Request:

```json
{
  "idempotencyKey": "ensure-thread:uuid",
  "model": "gpt-5.4",
  "modelProvider": "openai",
  "forceRebase": false
}
```

Response:

```json
{
  "binding": {
    "projectId": "p1",
    "nodeId": "n1",
    "role": "execution",
    "threadId": "thread_exec",
    "createdFrom": "new_thread",
    "sourceVersions": {
      "frameVersion": 2,
      "specVersion": 1,
      "splitManifestVersion": 3
    },
    "contextPacketHash": "sha256:..."
  },
  "workflowState": { "...": "canonical state response" }
}
```

## Execution

`POST /v4/projects/{projectId}/nodes/{nodeId}/execution/start`

Starts or resumes execution through Workflow Core V2. The backend ensures the
execution thread, injects execution context when needed, and starts the Codex
turn.

Request:

```json
{
  "idempotencyKey": "execution-start:uuid",
  "model": "gpt-5.4",
  "modelProvider": "openai"
}
```

Response:

```json
{
  "accepted": true,
  "threadId": "thread_exec",
  "turnId": "turn_exec",
  "executionRunId": "exec_run_1",
  "workflowState": { "...": "canonical state response" }
}
```

`POST /v4/projects/{projectId}/nodes/{nodeId}/execution/mark-done`

Request:

```json
{
  "idempotencyKey": "execution-mark-done:uuid",
  "expectedWorkspaceHash": "sha256:..."
}
```

`POST /v4/projects/{projectId}/nodes/{nodeId}/execution/improve`

Request:

```json
{
  "idempotencyKey": "execution-improve:uuid",
  "expectedReviewCommitSha": "abc"
}
```

The backend injects audit findings into the execution thread as a context packet
and starts the improvement turn. It should not prepend audit findings to the
user's freeform text.

## Audit

`POST /v4/projects/{projectId}/nodes/{nodeId}/audit/start`

Request:

```json
{
  "idempotencyKey": "audit-start:uuid",
  "expectedWorkspaceHash": "sha256:..."
}
```

The backend ensures the audit thread, injects audit context, and runs either
`review/start` or `turn/start` with `outputSchema`.

`POST /v4/projects/{projectId}/nodes/{nodeId}/audit/accept`

Request:

```json
{
  "idempotencyKey": "audit-accept:uuid",
  "expectedReviewCommitSha": "abc"
}
```

`POST /v4/projects/{projectId}/nodes/{nodeId}/audit/request-changes`

Request:

```json
{
  "idempotencyKey": "audit-request-changes:uuid",
  "expectedReviewCommitSha": "abc"
}
```

This endpoint records the audit decision and enables
`improve_in_execution`. If the implementation immediately starts the improvement
turn, it should return the execution `threadId` and `turnId`.

## Package Review

`POST /v4/projects/{projectId}/nodes/{nodeId}/package-review/start`

Request:

```json
{
  "idempotencyKey": "package-review-start:uuid"
}
```

The backend builds package review context from the parent and child node rollup,
ensures a package review thread, injects context, and starts review.

## Context Rebase

`POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase`

Request:

```json
{
  "idempotencyKey": "context-rebase:uuid",
  "roles": ["ask_planning", "execution", "audit"],
  "expectedWorkflowVersion": 42
}
```

Response:

```json
{
  "rebased": true,
  "updatedBindings": [
    {
      "role": "execution",
      "threadId": "thread_exec",
      "contextPacketHash": "sha256:new"
    }
  ],
  "workflowState": { "...": "canonical state response" }
}
```

## Workflow Events

`GET /v4/projects/{projectId}/events`

SSE event payload:

```json
{
  "type": "workflow/state_changed",
  "projectId": "p1",
  "nodeId": "n1",
  "phase": "review_pending",
  "version": 42,
  "eventId": "evt_1",
  "occurredAt": "2026-04-24T12:00:00Z"
}
```

Event types:

- `workflow/state_changed`
- `workflow/context_stale`
- `workflow/action_completed`
- `workflow/action_failed`

Frontend behavior:

- Subscribe by project.
- Filter by `nodeId`.
- Refresh workflow state on `workflow/state_changed` and
  `workflow/context_stale`.
- Do not consume Session Core V2 item/turn events from this stream.

## Error Envelope

Route errors should be deterministic:

```json
{
  "code": "ERR_WORKFLOW_CONTEXT_STALE",
  "message": "Workflow context is stale. Rebase before starting execution.",
  "details": {
    "projectId": "p1",
    "nodeId": "n1",
    "allowedActions": ["rebase_context"]
  }
}
```

Suggested status mapping:

- `ERR_WORKFLOW_NOT_FOUND`: 404
- `ERR_WORKFLOW_ACTION_NOT_ALLOWED`: 409
- `ERR_WORKFLOW_CONTEXT_STALE`: 409
- `ERR_WORKFLOW_IDEMPOTENCY_CONFLICT`: 409
- `ERR_WORKFLOW_ARTIFACT_VERSION_CONFLICT`: 409
- `ERR_WORKFLOW_THREAD_BINDING_FAILED`: 500 or 502 depending on cause
