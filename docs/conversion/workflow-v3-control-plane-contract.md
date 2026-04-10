# Workflow V3 Control Plane Contract

Status: locked  
Updated: 2026-04-10

## 1. Purpose

This document locks the workflow control plane contract between frontend and backend for the native V3 conversion track.

## 2. Naming Contract

- Canonical public naming: `thread_role`
- Supported values: `ask_planning | execution | audit`
- Canonical JSON key for thread role in V3 payloads: `threadRole`
- Final target contract (Phase 7+) does not emit `lane`.
- During Phase 0-2 adapter baseline, legacy `lane` may still appear on transcript payloads; no new workflow control-plane dependency may be introduced on `lane`.

## 3. Envelope Contract

Success:

```json
{
  "ok": true,
  "data": {}
}
```

Failure:

```json
{
  "ok": false,
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
```

## 4. Workflow State Endpoint

- `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`

The response shape must remain compatible with the current frontend model (NodeWorkflowView-equivalent), including:

- `workflowPhase`
- `askThreadId`
- `executionThreadId`
- `reviewThreadId`
- `auditLineageThreadId`
- `currentExecutionDecision`
- `currentAuditDecision`
- `canSendExecutionMessage`
- `canReviewInAudit`
- `canImproveInExecution`
- `canMarkDoneFromExecution`
- `canMarkDoneFromAudit`

## 5. Workflow Action Endpoints

- `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task`
- `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution`
- `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit`
- `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit`
- `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution`

Idempotency and guard behavior must preserve baseline semantics:

- duplicate idempotency key -> same logical outcome
- workspace/review guard mismatch -> typed invalid request

## 6. Workflow Events Endpoint

- `GET /v3/projects/{project_id}/events`
- Backend ownership: `backend/routes/workflow_v3.py`

Minimum event families:

- workflow-updated event (equivalent to `node.workflow.updated`)
- detail-invalidate event (equivalent to `node.detail.invalidate`)

The frontend bridge must be reconnect-safe and filter events by `projectId` and `nodeId`.

## 7. Active Path Rule

- Primary frontend workflow control-plane path must use only:
  - `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/*`
  - `GET /v3/projects/{project_id}/events`
- `/v2` workflow endpoints are compatibility-only during migration and must not remain on the primary active path after Phase 5.

## 8. Error Semantics To Preserve

- `invalid_request` for policy mismatch
- `conversation_stream_mismatch` for snapshot-version guard mismatch
- `ask_v3_disabled` (409) while the ask gate still exists

## 9. Versioning Rule

If the response shape must change, we must:

1. Update this document first.
2. Update the related baseline tests.
3. Record a clear migration note in the current phase artifact.
