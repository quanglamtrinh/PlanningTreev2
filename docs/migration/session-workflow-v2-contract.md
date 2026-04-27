# Session and Workflow V2 Contract Freeze

This freezes the current migration boundary: Session V2 is the native
conversation/runtime contract, while workflow execution/audit is still backed by
V3 business workflow APIs until Workflow V2 replaces them.

## 1. Session V2 contract

Current public surface is `/v4/session/*`.

- Initialize/status: `POST /v4/session/initialize`, `GET /v4/session/status`.
- Thread lifecycle: `POST /v4/session/threads/start`, `POST /v4/session/threads/{threadId}/resume`, `GET /v4/session/threads/list`, `GET /v4/session/threads/{threadId}/read`, `POST /v4/session/threads/{threadId}/fork`.
- Thread turn history: `GET /v4/session/threads/{threadId}/turns`.
- Turn control: `POST /v4/session/threads/{threadId}/turns/start`, `POST /v4/session/threads/{threadId}/turns/{turnId}/steer`, `POST /v4/session/threads/{threadId}/turns/{turnId}/interrupt`.
- Event stream: `GET /v4/session/threads/{threadId}/events?cursor={eventId}`.
- Pending requests: `GET /v4/session/requests/pending`.
- Resolve/reject: `POST /v4/session/requests/{requestId}/resolve`, `POST /v4/session/requests/{requestId}/reject`.

Required semantics:

- Turn commands use Codex app-server payloads and do not carry PlanningTree
  `clientActionId`; workflow mutations keep idempotency at the workflow layer.
- Request resolution is idempotent by `resolutionKey`.
- Event streams are ordered by `eventSeq`; clients detect gaps and reconnect with
  the last `eventId`.
- Pending request records must include enough scope to show only active-thread
  requests in the Breadcrumb surface.

## 2. Workflow V2 target contract

Target public surface should be V2-owned and should not expose V3 workflow
routes to UI code. Route family: `/v4/projects/{projectId}/nodes/{nodeId}/...`.

- Get node workflow state:
  `GET /v4/projects/{projectId}/nodes/{nodeId}/workflow-state`.
- Ensure thread for node role:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/threads/{role}/ensure`
  with `role` as `"ask_planning" | "execution" | "audit" |
  "package_review"` and `{ idempotencyKey }`.
  The UI may use lane aliases such as `ask`, but the API should normalize them
  server-side.
- Start execution:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/start`.
- Mark done from execution:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/mark-done`
  with `{ idempotencyKey, expectedWorkspaceHash }`.
- Review in audit:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/start`
  with `{ idempotencyKey, expectedWorkspaceHash }`.
- Improve in execution:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/execution/improve`
  with `{ idempotencyKey, expectedReviewCommitSha }`.
- Mark done from audit:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/audit/accept`
  with `{ idempotencyKey, expectedReviewCommitSha }`.
- Package review:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/package-review/start`
  with `{ idempotencyKey }`.
- Context stale/rebase:
  `POST /v4/projects/{projectId}/nodes/{nodeId}/context/rebase`
  with `{ idempotencyKey, expectedWorkflowVersion? }`.

Canonical V2 wire naming:

- Public V4 workflow responses use camelCase field names.
- The state envelope uses `phase` and `version`.
- Internal Python models may use snake_case and `state_version`.
- V3 compatibility views may continue exposing legacy names such as
  `workflowPhase`, `executionThreadId`, `reviewThreadId`, and
  `currentExecutionDecision`.

V3-to-V2 phase mapping:

| Legacy V3 `workflowPhase` | Canonical V2 `phase` |
| --- | --- |
| `idle` | `ready_for_execution` |
| `execution_running` | `executing` |
| `execution_decision_pending` | `execution_completed` |
| `audit_running` | `audit_running` |
| `audit_decision_pending` | `review_pending` |
| `done` | `done` |
| `failed` | `blocked` |

Action mapping:

- Current V3 `improve-in-execution` maps to V4 `execution/improve`.
- V4 `audit/request-changes` records or exposes the audit decision that enables
  improvement. It is not the first replacement for the current Breadcrumb
  "Improve in Execution" button.

Required target semantics:

- The server owns all business prompts.
- The server owns role-to-thread binding and decides when to reuse, fork, or
  create a thread.
- Mutations return either the updated workflow state or an accepted async
  operation with enough ids for the UI to select the right Session V2 thread.
- Stale context should use deterministic errors, for example
  `ERR_WORKFLOW_CONTEXT_STALE`, with a rebase/reload affordance in the response.
- Workflow V2 should provide an invalidation/event stream, for example
  `GET /v4/projects/{projectId}/events`, so the UI can remove
  `useWorkflowEventBridgeV3`.

## 3. UI rule

- UI must not call V3 workflow/conversation control-plane endpoints directly.
- UI must not build business prompts.
- UI must not decide fork vs. new thread vs. reuse thread.
- UI may render server-provided state, select Session V2 threads, submit user
  text through Session V2, and dispatch Workflow V2 actions.

Scope note: the broad rule "UI does not call `/v3`" is the right end state, but
it should be applied to the session/workflow surface first. Project snapshot and
node detail APIs may need their own migration contract if they also must leave
`/v3`.

## Current V3 endpoints used by the workflow UI

- `GET /v3/projects/{projectId}/nodes/{nodeId}/workflow-state`
- `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/finish-task`
- `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/mark-done-from-execution`
- `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/review-in-audit`
- `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/improve-in-execution`
- `POST /v3/projects/{projectId}/nodes/{nodeId}/workflow/mark-done-from-audit`
- `GET /v3/projects/{projectId}/events`

## Workflow state fields the UI currently needs

- Identity and phase: `nodeId`, `workflowPhase`.
- Thread bindings: `askThreadId`, `executionThreadId`, `auditLineageThreadId`,
  `reviewThreadId`.
- Active/latest operation ids: `activeExecutionRunId`, `latestExecutionRunId`,
  `activeReviewCycleId`, `latestReviewCycleId`.
- Decisions: `currentExecutionDecision`, `currentAuditDecision`.
- Decision guards: `currentExecutionDecision.candidateWorkspaceHash`,
  `currentAuditDecision.reviewCommitSha`.
- Completion/runtime: `acceptedSha`, `runtimeBlock`.
- Action availability: `canSendExecutionMessage`, `canReviewInAudit`,
  `canImproveInExecution`, `canMarkDoneFromExecution`,
  `canMarkDoneFromAudit`.

If Workflow V2 is also expected to eliminate project snapshot reads from this
surface, include `projectPath` and `nodeKind` or `isReviewNode` in the workflow
state envelope.

## V3 actions/mutations to replace

- `loadWorkflowState` -> Workflow V2 get node workflow state.
- `finishTask` / `finishTaskWorkflowV3` -> Workflow V2 start execution.
- `markDoneFromExecution` -> Workflow V2 mark done from execution.
- `reviewInAudit` -> Workflow V2 review in audit.
- `improveInExecution` -> Workflow V2 improve in execution.
- `markDoneFromAudit` -> Workflow V2 mark done from audit.
- `useWorkflowEventBridgeV3` -> Workflow V2 event/invalidation stream.

## Assessment

This is a reasonable migration step because it freezes the current hybrid seam
before moving business workflow ownership. The main improvement is to make the
target contract include workflow invalidation events and stale/rebase semantics;
otherwise the UI can stop calling V3 mutations but still remain coupled to V3
refresh behavior. The second improvement is to keep the UI rule scoped until
project and node-detail data have their own non-V3 replacement.
