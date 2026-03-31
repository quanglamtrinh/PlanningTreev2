# Execution and Audit API and Internal Contract Spec

Status: draft redesign spec. Defines the public workflow API and the internal contract between PTM workflow services and Codex/app-server transcript services.

Related docs:

- `docs/thread-rework/workflow-rework/execution-audit-workflow-spec.md`
- `docs/thread-rework/workflow-rework/execution-thread-redesign-spec.md`
- `docs/thread-rework/workflow-rework/audit-thread-redesign-spec.md`
- `docs/specs/gating-rules-matrix.md`

## Intent

Under the new workflow:

- `Finish Task` starts an execution run
- execution remains writable for follow-up implement turns before review or done
- execution completion exposes `Mark Done` and `Review in Audit`
- local review completion exposes `Mark Done` and `Improve in Execution`
- audit lineage is readonly context in standard workflow mode
- actual local review runs on an app-server review thread

Transcript follows a CodexMonitor-style client-owned model:

- raw app-server event
- frontend hook and reducer merge items
- semantic view-state derives presentation
- UI rerenders from local thread state

Backend remains authoritative for workflow correctness:

- run creation
- current decision points
- lane-local start-state persistence
- Git and commit decisions
- node state transitions
- review and improve handoff

## Supersession and Scope

This contract supersedes `docs/specs/conversation-streaming-v2.md` for:

- execution after `Finish Task`
- finished-leaf local audit/review

`docs/specs/conversation-streaming-v2.md` remains authoritative for:

- `ask_planning`
- the review-node flow
- legacy or transitional V2 conversation surfaces outside this rework

For the reworked lanes:

- transcript discovery and hydration are keyed by app-server `threadId`
- workflow control remains keyed by PTM `projectId` and `nodeId`
- node/role transcript lookup is not target architecture for execution or finished-leaf local review

## Public Workflow State

`GET /v2/projects/{project_id}/nodes/{node_id}/workflow-state`

Response:

```json
{
  "ok": true,
  "data": {
    "nodeId": "node_1",
    "workflowPhase": "audit_decision_pending",
    "executionThreadId": "th_exec_1",
    "auditLineageThreadId": "th_audit_lineage_1",
    "reviewThreadId": "th_review_1",
    "activeExecutionRunId": null,
    "latestExecutionRunId": "exec_run_2",
    "activeReviewCycleId": null,
    "latestReviewCycleId": "review_cycle_1",
    "latestReviewCommitSha": "gitsha:abc123",
    "latestReviewDisposition": "changes_requested",
    "currentCandidateSha": null,
    "currentCandidateWorkspaceHash": null,
    "runtimeBlock": "none",
    "activeRequestId": null,
    "executionStartState": "started",
    "auditStartState": "started",
    "executionLastError": null,
    "auditLastError": null,
    "currentExecutionDecision": null,
    "currentAuditDecision": {
      "decisionId": "audit_decision_1",
      "sourceReviewCycleId": "review_cycle_1",
      "reviewThreadId": "th_review_1",
      "reviewCommitSha": "gitsha:abc123",
      "status": "current"
    },
    "acceptedSha": null,
    "canFinishTask": false,
    "canSendExecutionMessage": false,
    "canSendAuditMessage": false,
    "canMarkDoneFromExecution": false,
    "canReviewInAudit": false,
    "canMarkDoneFromAudit": true,
    "canImproveInExecution": true
  }
}
```

Rules:

- `workflowPhase` is authoritative only for the active top-level lane
- `workflow-state` is authoritative for lane ownership, thread ids, runtime block, active request id, current decision objects, artifact references used by validation, and CTA flags
- `runtimeBlock` and `activeRequestId` are lane-local runtime fields; they do not create a new top-level workflow phase
- `executionStartState` and `auditStartState` expose `starting` and `start_failed` without moving ownership back to another lane
- `currentExecutionDecision` and `currentAuditDecision` are the authoritative CTA target and gating records for `Mark Done`, `Review in Audit`, and `Improve in Execution`
- `executionThreadId` is the transcript entry point for execution hydration
- `auditLineageThreadId` is the canonical node-context thread id for the audit lane
- `reviewThreadId` is the transcript entry point for audit hydration once the first local review thread exists
- `latestReviewCommitSha`, `latestReviewCycleId`, and `latestReviewDisposition` are metadata for audit prefix and CTA context
- `currentCandidateSha` remains `null` until a decision action commits candidate output
- execution composer is enabled only when workflow allows follow-up implement turns and no execution run is active
- audit generic composer remains disabled in standard workflow mode
- `canSendAuditMessage` remains `false` in standard workflow mode
- `currentCandidateSha`, `currentCandidateWorkspaceHash`, `latestReviewCommitSha`, `latestReviewCycleId`, and `latestReviewDisposition` are display mirrors only and must not be treated as gating truth
- if mirrored top-level metadata conflicts with a current decision object, CTA gating must follow the current decision object
- `latestReviewDisposition` is reviewer metadata only; it does not by itself decide `Mark Done` or `Improve in Execution`

## Public Detail Metadata Contract

`GET /v2/projects/{project_id}/nodes/{node_id}/detail-state` remains the node metadata dossier for execution and audit surfaces.

It is intentionally non-authoritative for workflow control.

Allowed responsibilities:

- task title, hierarchy, and node labels
- frame/spec summary and parent split/clarify context
- readonly audit shell context
- display-oriented metadata mirrors that help render the shell

Forbidden responsibilities:

- deciding `workflowPhase` or CTA enablement
- deciding `executionThreadId`, `auditLineageThreadId`, or `reviewThreadId` for transcript hydration
- overriding current decision objects, runtime block, start-state fields, or accepted artifact fields

Conflict rule:

- if `detail-state` mirrors any field also returned by `workflow-state`, `workflow-state` wins
- clients may fetch `detail-state` in parallel for render, but workflow writes and CTA gating must never validate against `detail-state`

## Authoritative Decision Rules

### Supersede old decision only after turn confirmation

When a new follow-up execution run or improve-from-audit execution run is requested:

- the previous current decision remains authoritative while the new run is only in `starting`
- only after backend confirms the new turn by immediate start success or reconciliation by `clientRequestId` does the previous decision become `superseded` or finalized
- only the newest confirmed current decision remains actionable
- actions against a confirmed superseded decision must fail with `workflow_transition_invalid`

### Persist `starting` and `start_failed` without losing prior authority

Actions that create a new turn must persist lane-local start state:

- `starting` before the runtime turn is created
- `started` after the runtime turn is created successfully
- `start_failed` plus lane-local error details if turn creation fails
- turn confirmation may come from the immediate start response or later reconciliation by `clientRequestId`
- if start fails before the new turn is confirmed, backend must keep or restore the prior authoritative state:
  - `Finish Task` remains `ready_for_execution`
  - execution follow-up remains `execution_decision_pending` with the prior execution decision still current
  - `Improve in Execution` remains `audit_decision_pending` with the prior audit decision still current
- if ownership already transferred because a commit-backed artifact was created first, the failure stays on the new lane:
  - `Review in Audit` after `reviewCommitSha` is committed remains in `audit_running`

The owning thread surface must render the error and retry affordance inline.

### Decision gating uses decision plus source record

Decision objects and run-cycle records have different responsibilities:

- decision object decides which artifact is still current
- source run or source review cycle decides whether the source turn has terminally completed

Validation must therefore use the conjunction:

- `currentExecutionDecision.status = current` plus `sourceExecutionRun.status = completed`
- `currentAuditDecision.status = current` plus `sourceReviewCycle.lifecycleStatus = completed`

`ReviewCycle.reviewDisposition` is reviewer metadata only. It may be rendered in audit metadata, but it does not replace workflow decision state.

### Freeze artifact on `commit succeeded but review/start failed`

If `Review in Audit` commits successfully and creates `reviewCommitSha = C1`, but local review start fails:

- the current audit decision remains bound to `reviewCommitSha = C1`
- retry must reuse exactly that reviewed commit
- retry must not create a new commit
- the failure belongs to the audit lane

### First detached review creation must reconcile by `clientRequestId`

The first local review for a finished leaf node is special because backend may not yet know the new `reviewThreadId`.

Rules:

- backend persists a `clientRequestId` before calling `review/start(detached)`
- app-server must echo that `clientRequestId` or idempotency identifier in detached-thread lifecycle metadata
- if retry happens before backend has persisted `reviewThreadId`, backend must reconcile by `clientRequestId`
- if an existing detached review thread is found, backend adopts that thread instead of creating another one
- only when no detached review thread is found may backend call detached creation again

Later local reviews run on an already-known `reviewThreadId` and do not require detached-thread discovery, but they still must reconcile by `clientRequestId` before a retry issues a duplicate inline start.

### Persist `clientRequestId` for every turn-start action

Every backend-started execution or review turn must have a persisted runtime correlation id.

Rules:

- backend persists `clientRequestId` before calling runtime for `Finish Task`, execution follow-up, `Improve in Execution`, detached review start, and inline review start
- app-server must echo that correlation id or an equivalent idempotency identifier in lifecycle metadata
- if backend is unsure whether a turn was created, retry must reconcile by `clientRequestId` before attempting another start
- if an existing turn is found, backend adopts its turn binding instead of creating a duplicate turn
- detached review reconciliation may also need to adopt the resulting `reviewThreadId`

### Single-instance platform constraint

PTM v1 officially supports:

- one Electron app instance
- one active window
- no multi-tab workflow

This constraint removes the need for a backend multi-tab coordinator in v1, but does not remove backend idempotency requirements for workflow actions.

## Client Transcript Contract

Execution and local review transcript are not hydrated by a PTM backend `thread view` endpoint in the target model.

Instead, the client follows the same high-level shape as CodexMonitor:

1. client fetches `workflow-state` to get `executionThreadId`, `auditLineageThreadId`, `reviewThreadId`, workflow phase, runtime block, and CTA state
2. client may fetch `detail-state` in parallel for prefix/context metadata
3. client thread service calls `thread/read` using the app-server `threadId` chosen from `workflow-state`
4. client converts returned thread payload into thread items
5. client hydrates local reducer state
6. client subscribes or resubscribes to live thread events if the turn is still active

Rules:

- PTM backend does not build `hydratedItems` for execution or local review in the target model
- PTM backend does not return `prefixItems` as part of transcript bootstrap
- prefix metadata is rendered from `workflow-state` plus `detail-state`, not from transcript hydration
- client thread service is keyed by app-server `threadId`, not by `(projectId, nodeId, threadRole)`
- execution transcript hydrates from `executionThreadId`
- local review transcript hydrates from `reviewThreadId` once it exists
- before first local review, audit tab may render readonly metadata without hydrating a review transcript because `reviewThreadId` is still `null`
- PTM relies on app-server history via `thread/read`; any Codex-managed local storage backing that history is an implementation detail, not a PTM-owned contract
- if `thread/read` cannot reconstruct a pending request after refresh, that is a transcript correctness failure for this rework; v1 does not define a fallback request-state endpoint

## Client Live Transport Contract

The target model mirrors CodexMonitor:

- client transcript transport subscribes to live events by app-server `threadId`
- reconnect and resubscribe are handled by the client transport layer
- resume and hydrate are handled by the client thread service

Rules:

- PTM workflow APIs do not own a thread-scoped `transportDescriptor` contract in v1
- PTM workflow APIs do not proxy transcript discovery or transport by node/role in the target architecture for execution or finished-leaf local review
- if the client transport layer later needs cursors or tokens, that remains an app-server or client-transport concern, not a workflow API concern
- browser never starts execution or local review turns directly against the app-server
- all turn creation still goes through backend workflow actions

## Reconciliation Trigger Rules

Backend reconciliation is required before every authoritative read or write that depends on runtime progress.

Required trigger points:

- `GET /workflow-state` must reconcile before returning if the local lane is still non-terminal
- every mutating workflow action must reconcile before validation
- every retry attempt must reconcile before validation

Read-through rule:

- before backend answers "what lane is current?" or "is this CTA allowed?", it must reconcile pending runtime progress from app-server lifecycle or `thread/read`

## Public Workflow Actions

All workflow actions that may create a commit or start a new turn must support an idempotency key.

The same idempotency key must not create a second commit, a second review artifact, or a second runtime turn for the same action attempt.

### Finish Task

`POST /v2/projects/{project_id}/nodes/{node_id}/workflow/finish-task`

Request:

```json
{
  "idempotencyKey": "wf_finish_task_1"
}
```

Response:

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "workflowPhase": "execution_running",
    "executionStartState": "started",
    "executionRun": {
      "runId": "exec_run_1",
      "executionThreadId": "th_exec_1",
      "executionTurnId": "turn_exec_1",
      "clientRequestId": "wf_exec_internal_1",
      "triggerKind": "finish_task",
      "startSha": "gitsha:base1",
      "status": "running"
    }
  }
}
```

### Mark Done from Execution

`POST /v2/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution`

Request:

```json
{
  "executionRunId": "exec_run_1",
  "expectedWorkspaceHash": "ws_hash_1",
  "idempotencyKey": "wf_mark_done_exec_1"
}
```

### Review in Audit

`POST /v2/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit`

Request:

```json
{
  "executionRunId": "exec_run_1",
  "expectedWorkspaceHash": "ws_hash_1",
  "idempotencyKey": "wf_review_in_audit_1"
}
```

Response:

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "workflowPhase": "audit_running",
    "auditStartState": "started",
    "reviewCycle": {
      "cycleId": "review_cycle_1",
      "auditLineageThreadId": "th_audit_lineage_1",
      "reviewThreadId": "th_review_1",
      "reviewTurnId": "turn_review_1",
      "reviewCommitSha": "gitsha:abc123",
      "deliveryKind": "detached",
      "clientRequestId": "wf_review_internal_1",
      "lifecycleStatus": "running",
      "reviewDisposition": null
    }
  }
}
```

Retry rule:

- if commit succeeded but review start failed, the retry action must reuse the same `reviewCommitSha`
- retry must not create a second commit
- on the first detached cycle, retry must reconcile by `clientRequestId` before attempting detached creation again
- the failure is rendered in the audit surface with `auditStartState = "start_failed"`

### Mark Done from Audit

`POST /v2/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit`

Request:

```json
{
  "reviewCycleId": "review_cycle_1",
  "expectedReviewCommitSha": "gitsha:abc123",
  "idempotencyKey": "wf_mark_done_audit_1"
}
```

### Improve in Execution

`POST /v2/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution`

Request:

```json
{
  "reviewCycleId": "review_cycle_1",
  "expectedReviewCommitSha": "gitsha:abc123",
  "idempotencyKey": "wf_improve_exec_1"
}
```

Response:

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "workflowPhase": "execution_running",
    "executionStartState": "started",
    "executionRun": {
      "runId": "exec_run_2",
      "executionThreadId": "th_exec_1",
      "executionTurnId": "turn_exec_2",
      "clientRequestId": "wf_exec_internal_2",
      "triggerKind": "improve_from_review",
      "sourceReviewCycleId": "review_cycle_1",
      "startSha": "gitsha:abc123",
      "status": "running"
    }
  }
}
```

## Retry Contract

PTM v1 reuses the original public action endpoint for retry.

Rules:

- `Finish Task` retry calls `POST /workflow/finish-task` again with the same `idempotencyKey`
- `Review in Audit` retry calls `POST /workflow/review-in-audit` again with the same `idempotencyKey`
- `Improve in Execution` retry calls `POST /workflow/improve-in-execution` again with the same `idempotencyKey`
- execution follow-up retry calls `POST /threads/execution/turns` again with the same idempotency behavior
- the public `idempotencyKey` must map to one persisted runtime `clientRequestId` for that action attempt
- retry must reuse the already-created artifact when the earlier attempt already committed successfully
- retry must not create a second commit or a second review artifact for the same action attempt
- every retry for an execution or review start must reconcile by `clientRequestId` before another runtime start is attempted
- on the first detached review cycle, reconciliation by `clientRequestId` may also need to discover the new `reviewThreadId`
- on later cycles with a known `reviewThreadId`, retry may rerun `review/start` on that same review thread only after `clientRequestId` reconciliation proves no turn was already created

## Public Thread Turns

### Execution Follow-Up Turn

The existing execution thread turn endpoint remains available for normal follow-up implement messages:

`POST /v2/projects/{project_id}/nodes/{node_id}/threads/execution/turns`

Request:

```json
{
  "text": "Please clean up the variable names and tighten the error handling.",
  "metadata": {},
  "idempotencyKey": "wf_exec_follow_up_1"
}
```

Rules:

- only allowed when `canSendExecutionMessage = true`
- supersedes the previous current execution decision only after the new execution turn is confirmed
- creates a new `ExecutionRun(triggerKind = "follow_up_message")`
- does not commit workspace
- does not create a review cycle

### Audit Generic Turn Creation

Audit generic composer is disabled in standard workflow mode.

There is no normal `POST /threads/audit/turns` action for user-authored freeform audit messages in this workflow.

## Persistence Model

Authoritative backend stores:

- `execution_run_store`
- `review_cycle_store`
- `workflow_state_store`

Models:

```ts
type ExecutionRun = {
  runId: string;
  projectId: string;
  nodeId: string;
  executionThreadId: string;
  executionTurnId: string;
  clientRequestId: string;
  triggerKind: "finish_task" | "improve_from_review" | "follow_up_message";
  sourceReviewCycleId: string | null;
  startSha: string;
  candidateWorkspaceHash: string | null;
  committedHeadSha: string | null;
  status: "running" | "completed" | "failed";
  decision: "pending" | "marked_done" | "sent_to_review" | null;
  errorMessage: string | null;
};
```

```ts
type ReviewDisposition = "approved" | "changes_requested";
```

```ts
type ReviewCycle = {
  cycleId: string;
  projectId: string;
  nodeId: string;
  sourceExecutionRunId: string;
  auditLineageThreadId: string;
  reviewThreadId: string | null;
  reviewTurnId: string | null;
  reviewCommitSha: string;
  deliveryKind: "detached" | "inline";
  clientRequestId: string;
  finalReviewText: string | null;
  lifecycleStatus: "running" | "completed" | "failed" | "superseded";
  reviewDisposition: ReviewDisposition | null;
  errorMessage: string | null;
};
```

```ts
type ExecutionDecision = {
  decisionId: string;
  sourceExecutionRunId: string;
  candidateWorkspaceHash: string;
  candidateSha: string | null;
  status: "current" | "superseded" | "marked_done" | "sent_to_review";
};
```

```ts
type AuditDecision = {
  decisionId: string;
  sourceReviewCycleId: string;
  reviewThreadId: string | null;
  reviewCommitSha: string;
  status: "current" | "superseded" | "accepted" | "improve_requested";
};
```

Rules:

- `reviewCommitSha` is immutable
- `reviewThreadId` becomes stable after the first successful detached review creation
- `finalReviewText` is the canonical local review output for `Improve in Execution`
- `reviewDisposition` is reviewer metadata and does not replace audit decision state
- only one running execution run per node
- only one running review cycle per node
- only one current execution decision per node
- only one current audit decision per node
- latest current audit decision is the only valid source for `Improve in Execution`

## Internal Services

### WorkflowDecisionService

- validates transitions
- owns public workflow actions
- updates stores atomically under project lock
- persists decision supersession only after the replacement turn is confirmed or the user has made a terminal workflow decision
- persists `starting` and `start_failed` lane state

### ExecutionTurnStarter

- starts execution turn
- persists `executionStartState`, `clientRequestId`, and `executionTurnId`
- reconciles by `clientRequestId` before issuing a duplicate execution start on retry
- does not own live transcript merge

### ReviewStartService

- starts local review for a review cycle
- calls app-server `review/start`
- persists `auditStartState`
- persists `reviewThreadId`, `reviewTurnId`, `deliveryKind`, and `clientRequestId`
- reconciles by `clientRequestId` before issuing a duplicate detached or inline review start on retry
- never creates a second reviewed commit on retry after a successful commit
- does not own live transcript merge

### WorkflowReconciliationService

- lazily reconciles runtime state from app-server lifecycle or `thread/read`
- materializes current decision points when a turn has already completed
- persists lane-local error state for retry
- binds execution turn creation by `clientRequestId`
- binds first detached review creation by `clientRequestId`
- binds inline review turn creation by `clientRequestId`
- persists `finalReviewText` from `exitedReviewMode.review`
- persists `reviewDisposition` separately from cycle lifecycle when that metadata is available
- runs before authoritative reads and mutating workflow validations
- does not own live transcript merge

### WorkflowMetadataService

- returns workflow-state and role metadata needed by execution/audit UI
- exposes thread ids, review commit metadata, and CTA flags
- does not build transcript item lists

### GitArtifactService

- computes workspace hash
- commits workspace for `Mark Done` or `Review in Audit`
- returns `head_sha`
- enforces drift checks
- guarantees reviewed-commit reuse on retry after `commit succeeded but review/start failed`

## Runtime Reconciliation Contract

Backend reconciliation responsibilities:

- bind `projectId`, `nodeId`, `threadId`, and `turnId`
- reconcile runtime completion independently of browser memory
- record lane-local `runtimeBlock`, `starting`, and `start_failed`
- finalize or supersede current decisions
- adopt execution turn creation by `clientRequestId`
- adopt detached review thread creation by `clientRequestId`
- adopt inline review turn creation by `clientRequestId`
- persist `finalReviewText` from the matching `reviewTurnId`
- persist `reviewDisposition` separately from lifecycle completion when that metadata is available
- emit `node.workflow.updated` and `node.detail.invalidate`
- survive browser refresh and close
- recover on backend restart from persisted run state plus thread binding or on-demand `thread/read`

Reconciliation does not:

- persist every text delta
- build canonical transcript snapshot per delta
- own semantic UI state
- own transcript hydration for reload

## Validation Rules

### Finish Task

- spec confirmed
- node leaf
- no running execution
- no running review cycle

### Send Execution Message

- phase = `execution_decision_pending`
- no running execution
- no running review cycle
- `canSendExecutionMessage = true`

### Mark Done from Execution

- phase = `execution_decision_pending`
- `currentExecutionDecision.status = current`
- `sourceExecutionRun.status = completed`
- current workspace hash equals `expectedWorkspaceHash`

### Review in Audit

- phase = `execution_decision_pending`
- `currentExecutionDecision.status = current`
- `sourceExecutionRun.status = completed`
- current workspace hash equals `expectedWorkspaceHash`
- if a reviewed commit already exists for the same idempotency key, reuse it

### Mark Done from Audit

- phase = `audit_decision_pending`
- `currentAuditDecision.status = current`
- `sourceReviewCycle.lifecycleStatus = completed`
- current `HEAD` equals `expectedReviewCommitSha`

### Improve in Execution

- phase = `audit_decision_pending`
- `currentAuditDecision.status = current`
- `sourceReviewCycle.lifecycleStatus = completed`
- current `HEAD` equals `expectedReviewCommitSha`
- no running execution

Fail-fast errors:

- `workflow_transition_invalid`
- `execution_run_not_found`
- `review_cycle_not_found`
- `artifact_drifted`
- `execution_run_already_running`
- `review_cycle_already_running`

## Execution Start Internal Contract

Every backend-started execution turn must carry a persisted runtime correlation id.

Rules:

- backend persists `clientRequestId` before calling the execution runtime
- app-server must echo that `clientRequestId` or an equivalent idempotency identifier in execution lifecycle metadata
- if retry happens before backend has durably persisted `executionTurnId`, backend must reconcile by `clientRequestId`
- if an existing execution turn is found, backend adopts that `executionTurnId` instead of creating a duplicate turn

## Review Start Internal Contract

First detached local review:

```json
{
  "method": "review/start",
  "params": {
    "threadId": "th_audit_lineage_1",
    "delivery": "detached",
    "clientRequestId": "wf_review_internal_1",
    "target": {
      "type": "commit",
      "sha": "gitsha:abc123",
      "title": "Review commit gitsha:abc123"
    }
  }
}
```

Later local review on existing review thread:

```json
{
  "method": "review/start",
  "params": {
    "threadId": "th_review_1",
    "clientRequestId": "wf_review_internal_2",
    "target": {
      "type": "commit",
      "sha": "gitsha:def456",
      "title": "Review commit gitsha:def456"
    }
  }
}
```

App-server requirements:

- detached review creation must return or later emit the resulting `reviewThreadId`
- app-server must echo `clientRequestId` or equivalent idempotency identifier in detached and inline review lifecycle metadata
- detached and inline review lifecycle must identify the created `reviewTurnId`
- review thread transcript must contain `enteredReviewMode` and `exitedReviewMode`
- `enteredReviewMode` and `exitedReviewMode` must be attributable to that same `reviewTurnId`
- `exitedReviewMode.review` is the canonical review text for that `reviewTurnId`
- reviewer disposition metadata, if available, must stay separate from lifecycle completion and from user audit decisions

## Commit Semantics

- `Finish Task` starts execution from current `HEAD` as `startSha`
- execution completion does not auto-commit
- follow-up execution messages do not auto-commit
- `Mark Done from Execution` commits current workspace and sets `acceptedSha`
- `Review in Audit` commits current workspace and creates immutable `reviewCommitSha`
- if that commit succeeds but local review start fails, retry reuses the same `reviewCommitSha`
- `Mark Done from Audit` accepts existing `reviewCommitSha`; no new commit required
- `Improve in Execution` starts new execution run from reviewed `reviewCommitSha`
- if UI later needs a diff base for display, it may derive it from the parent of `reviewCommitSha`; the workflow model does not gate on that derived base

## Workflow Events

Project-global workflow SSE remains on:

- `node.workflow.updated`
- `node.detail.invalidate`

`node.workflow.updated` payload:

```json
{
  "projectId": "p1",
  "nodeId": "n1",
  "workflowPhase": "audit_decision_pending",
  "activeExecutionRunId": null,
  "activeReviewCycleId": null
}
```

Frontend uses these only for CTA and detail refresh. Transcript rendering remains client-owned via app-server thread transport.

## End-to-End Flows

Execution flow:

- `Finish Task`
- execution run starts
- browser streams execution thread directly from app-server events
- terminal
- `execution_decision_pending`

Review flow:

- `Review in Audit`
- backend commits candidate output
- first cycle detaches review thread from audit lineage thread if needed
- browser streams review thread directly from app-server events
- terminal
- `audit_decision_pending`

Improve flow:

- `Improve in Execution`
- backend reads canonical `finalReviewText` from latest completed review cycle
- new execution run starts on execution thread
- browser streams execution directly
- terminal
- back to `execution_decision_pending`

Done flow:

- `Mark Done` from execution or audit
- node marked `done`
- next-task activation handled by workflow layer

## Migration Rules

- do not make `GET /threads/{thread_role}/view` part of the target execution or audit transcript model
- frontend hydration should move from backend-built `hydratedItems` to client-owned `thread/read`
- frontend live transport should move from backend transcript SSE to app-server thread events
- audit tab should move from treating the audit lineage thread as the live review surface to treating it as readonly context plus a spawned review thread
- prefix metadata should move out of transcript bootstrap and into `workflow-state` plus `detail-state`
- request-user-input queue should be owned by the client reducer path
- execution generic composer remains enabled for follow-up implement turns
- audit generic composer remains disabled
- platform support is single-instance and single-window only in v1
- PTM v1 does not introduce a separate local execution or review transcript archive; transcript recovery relies on `thread/read`
