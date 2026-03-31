# Execution and Audit Workflow Rework

Status: draft redesign spec. Defines the new post-`Finish Task` workflow where execution and local review are explicit decision-driven lanes instead of an auto-review chain.

Related docs:

- `docs/thread-rework/workflow-rework/execution-audit-api-internal-contract-spec.md`
- `docs/thread-rework/workflow-rework/execution-thread-redesign-spec.md`
- `docs/thread-rework/workflow-rework/audit-thread-redesign-spec.md`
- `docs/specs/gating-rules-matrix.md`

## Intent

This workflow replaces the current implicit `Finish Task -> auto review` behavior with an explicit user-driven loop:

1. `Finish Task` starts an execution run.
2. When execution completes, the user chooses:
   - `Mark Done`
   - `Review in Audit`
   - or sends another follow-up implement message in execution
3. When local review completes, the user chooses:
   - `Mark Done`
   - `Improve in Execution`

Goals:

- make execution a pure implement/fix thread
- keep execution writable for iterative follow-up implement turns before the user commits to review or done
- keep audit lineage as the canonical node context thread
- run actual local review on an app-server review thread, not on the audit lineage thread
- bind every local review cycle to one immutable reviewed commit
- remove automatic review handoff from execution completion
- keep workflow state explicit, inspectable, and recoverable
- make transcript behavior match CodexMonitor as closely as practical

## Scope

In scope:

- execution thread workflow after `Finish Task`
- audit lineage thread plus review thread model for finished leaf nodes
- local review workflow based on immutable `reviewCommitSha`
- improve loop from local review back into execution
- workflow state machine, artifacts, and Git semantics
- transcript and workflow ownership boundaries

Out of scope:

- redesign of `ask_planning`
- final subtree review in the review-node flow
- detailed visual design of thread UIs
- changes to the public conversation item schema beyond review-mode integration

### Supersession note

This doc set supersedes `docs/specs/conversation-streaming-v2.md` for:

- execution after `Finish Task`
- finished-leaf local audit/review

`docs/specs/conversation-streaming-v2.md` remains authoritative for:

- `ask_planning`
- the review-node flow
- legacy or transitional V2 conversation surfaces outside this rework

## Architectural Model

### Transcript lane

Execution transcript and review transcript follow a CodexMonitor-style model:

- raw app-server event
- client hook and reducer merge thread items
- view-state derives semantic rendering
- UI rerenders directly from local thread state

Reload and reopen follow the same model:

- client thread service calls `thread/read`
- client rebuilds local thread items from app-server history
- client resubscribes to live thread events if the turn is still active

PTM v1 does not maintain a separate local execution or review transcript archive.

### Workflow lane

Backend remains authoritative for:

- `ExecutionRun`
- `ReviewCycle`
- current execution and audit decision points
- `workflowPhase`
- Git drift checks
- `Mark Done`
- `Review in Audit`
- `Improve in Execution`
- thread start-state persistence and decision reconciliation independent of browser memory

### Metadata lane

Task title, frame/spec context, parent split context, review cycle metadata, commit metadata, and CTA gating are not part of transcript hydration.

They come from backend APIs with distinct authority boundaries and render separately from live thread items:

- `workflow-state` is authoritative for `workflowPhase`, thread ids, runtime block, active request state, CTA gating, decision objects, and artifact references used by workflow validation
- `detail-state` is non-authoritative node metadata for title, hierarchy, frame/spec context, parent split/clarify context, and other shell display data

If mirrored fields conflict, `workflow-state` wins for thread identity, runtime state, CTA gating, and workflow validation.

This keeps execution and review transcript latency independent from PTM-specific UI metadata.

## Core Concepts

### ExecutionRun

One implement or improve cycle on the execution thread.

### ReviewCycle

One local review cycle for exactly one immutable `reviewCommitSha`.

### Audit Lineage Thread

The canonical audit/context thread for a node.

It holds durable node context, such as node-local `spec.md`, frame, and inherited split/clarify context. For finished leaf nodes in standard workflow mode, it is readonly and is not the main local-review transcript surface.

### Review Thread

The local-review history thread for a finished leaf node.

It is created from the audit lineage thread on the first local review, then reused for later local reviews.

### Review Commit

The immutable commit reviewed by one local review cycle.

This is the authoritative reviewed artifact field for the audit lane.

### Candidate Output

The workspace state produced by a completed execution run before the user decides what to do next.

### Accepted Output

The Git SHA that the user ultimately accepts when marking the task done.

## Data Model

```ts
type WorkflowPhase =
  | "ready_for_execution"
  | "execution_running"
  | "execution_decision_pending"
  | "audit_running"
  | "audit_decision_pending"
  | "done";
```

```ts
type RuntimeBlock = "none" | "waiting_user_input";
```

```ts
type TurnStartState = "idle" | "starting" | "started" | "start_failed";
```

```ts
type ExecutionRun = {
  run_id: string;
  project_id: string;
  node_id: string;
  execution_thread_id: string;
  execution_turn_id: string;
  client_request_id: string;
  trigger_kind: "finish_task" | "improve_from_review" | "follow_up_message";
  source_review_cycle_id: string | null;
  start_sha: string;
  candidate_workspace_hash: string | null;
  committed_head_sha: string | null;
  status: "running" | "completed" | "failed";
  decision: "pending" | "marked_done" | "sent_to_review" | null;
  summary_text: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  decided_at: string | null;
};
```

```ts
type ReviewDisposition = "approved" | "changes_requested";
```

```ts
type ReviewCycle = {
  cycle_id: string;
  project_id: string;
  node_id: string;
  source_execution_run_id: string;
  audit_lineage_thread_id: string;
  review_thread_id: string | null;
  review_turn_id: string | null;
  review_commit_sha: string;
  delivery_kind: "detached" | "inline";
  client_request_id: string;
  lifecycle_status: "running" | "completed" | "failed" | "superseded";
  review_disposition: ReviewDisposition | null;
  final_review_text: string | null;
  requested_at: string;
  completed_at: string | null;
  decided_at: string | null;
  error_message: string | null;
};
```

```ts
type ExecutionDecision = {
  decision_id: string;
  source_execution_run_id: string;
  candidate_workspace_hash: string;
  candidate_sha: string | null;
  status: "current" | "superseded" | "marked_done" | "sent_to_review";
  superseded_by_execution_run_id: string | null;
};
```

```ts
type AuditDecision = {
  decision_id: string;
  source_review_cycle_id: string;
  review_thread_id: string | null;
  review_commit_sha: string;
  status: "current" | "superseded" | "accepted" | "improve_requested";
  superseded_by_execution_run_id: string | null;
};
```

```ts
type NodeWorkflowView = {
  workflow_phase: WorkflowPhase;
  execution_thread_id: string | null;
  audit_lineage_thread_id: string | null;
  review_thread_id: string | null;
  active_execution_run_id: string | null;
  latest_execution_run_id: string | null;
  active_review_cycle_id: string | null;
  latest_review_cycle_id: string | null;
  latest_review_commit_sha: string | null;
  latest_review_disposition: ReviewDisposition | null;
  current_candidate_sha: string | null;
  current_candidate_workspace_hash: string | null;
  accepted_sha: string | null;
  runtime_block: RuntimeBlock;
  active_request_id: string | null;
  execution_start_state: TurnStartState;
  audit_start_state: TurnStartState;
  execution_last_error: string | null;
  audit_last_error: string | null;
  current_execution_decision: ExecutionDecision | null;
  current_audit_decision: AuditDecision | null;
  can_finish_task: boolean;
  can_send_execution_message: boolean;
  can_send_audit_message: boolean;
  can_mark_done_from_execution: boolean;
  can_review_in_audit: boolean;
  can_mark_done_from_audit: boolean;
  can_improve_in_execution: boolean;
};
```

Notes:

- `current_execution_decision` and `current_audit_decision` are the authoritative workflow decision records for CTA gating.
- decision objects decide which artifact is current; source run and review-cycle records decide whether the source turn has completed successfully.
- `current_candidate_sha` is normally `null` during `execution_decision_pending` because execution completion does not auto-commit.
- `current_candidate_workspace_hash` is the primary artifact identifier before the user chooses `Mark Done` or `Review in Audit`.
- `audit_lineage_thread_id` is the canonical context thread id for the node.
- `review_thread_id` is the canonical local-review history thread id for the leaf node once the first detached review has been created.
- `workflow-state` is the authoritative API for `execution_thread_id`, `audit_lineage_thread_id`, `review_thread_id`, decision objects, runtime-block state, and CTA booleans.
- `detail-state` may mirror display metadata, but it must not override workflow-state for transcript hydration or transition validation.
- `latest_review_commit_sha`, `latest_review_cycle_id`, and `latest_review_disposition` are metadata for audit prefix and CTA context. They are not transcript items.
- top-level candidate and review metadata fields are mirrored metadata for rendering; they must not override current decision objects for CTA gating.
- `review_disposition` is reviewer metadata, not a workflow decision. `Mark Done` and `Improve in Execution` remain gated by `current_audit_decision` plus the source cycle lifecycle record, not by reviewer disposition alone.
- `runtime_block = "waiting_user_input"` does not change the top-level workflow phase. It only blocks generic send and exposes the inline request currently being answered.
- `execution_start_state` and `audit_start_state` are persisted lane-local states. They expose `starting` and `start_failed` without introducing new top-level workflow phases.

## State Machine

Primary happy-path flow:

- `ready_for_execution`
- `execution_running`
- `execution_decision_pending`
- `audit_running`
- `audit_decision_pending`
- `done`

Allowed transitions:

- `Finish Task`: `ready_for_execution -> execution_running`
- execution terminal success: `execution_running -> execution_decision_pending`
- `Execution follow-up message`: `execution_decision_pending -> execution_running`
- `Mark Done` from execution: `execution_decision_pending -> done`
- `Review in Audit`: `execution_decision_pending -> audit_running`
- review terminal success: `audit_running -> audit_decision_pending`
- `Mark Done` from audit: `audit_decision_pending -> done`
- `Improve in Execution`: `audit_decision_pending -> execution_running`

For actions that start a new turn:

- the top-level phase changes only after the new turn is confirmed by immediate start success or reconciliation
- if start fails before the new turn is confirmed, the prior authoritative phase remains or is restored

Lane-local states that do not create new top-level phases:

- `runtime_block = waiting_user_input`
- `execution_start_state = starting | start_failed`
- `audit_start_state = starting | start_failed`

## Invariants

- at most one `ExecutionRun.status = "running"` per node
- at most one `ReviewCycle.lifecycle_status = "running"` per node
- at most one `ExecutionDecision.status = "current"` per node
- at most one `AuditDecision.status = "current"` per node
- `ReviewCycle.review_commit_sha` is immutable once created
- the first local review for a finished leaf node creates `review_thread_id` with `delivery_kind = "detached"`
- later local reviews for that same leaf node reuse the same `review_thread_id` with `delivery_kind = "inline"`
- the audit lineage thread remains the canonical node-context thread even after a review thread exists
- the review thread remains the canonical local-review history thread for the leaf node after it is created
- when a new execution turn is confirmed for follow-up execution or improve, the previous current decision for that lane is superseded or finalized at that moment
- `Improve in Execution` is only allowed from the current audit decision
- `Mark Done` must accept the exact artifact represented by the current decision point
- UI CTA gating must come from workflow state, not from transcript heuristics
- execution transcript is writable in `execution_decision_pending`
- audit lineage is readonly in standard workflow mode after `Finish Task`
- local review transcript is review-only in standard workflow mode
- `runtime_block = "waiting_user_input"` disables normal send for the owning lane until that request is resolved
- `start_failed` is thread-local state; once ownership has already transferred, it does not hand control back to the previous lane
- decision validation must always use both the current decision object and its source run or source review-cycle record
- `review_disposition` is advisory review metadata only; it must not by itself disable `Mark Done` or `Improve in Execution`

## Resolved Implementation Rules

### Rule 1: supersede old decision only after the new turn is confirmed

When a follow-up execution run or `Improve in Execution` execution run is requested:

- the previous current decision remains authoritative while the new run is only in `starting`
- once backend has confirmed the new turn by immediate start success or reconciliation by `client_request_id`, the previous decision is superseded or finalized for that lane
- only after that confirmation does the new run own the active lane and its top-level phase
- if start fails before a new turn is confirmed, the previous decision remains current or is restored as current
- only a confirmed superseded decision loses `Mark Done`, `Review in Audit`, or `Improve in Execution`

Example:

- Candidate A is pending in execution
- user sends a follow-up execution message
- backend sets `execution_start_state = "starting"`
- if execution run B is confirmed, decision A is marked `superseded`
- only then does candidate B own the active execution lane
- if B never gets confirmed, candidate A remains actionable

### Rule 2: persist `starting` and `start_failed` without losing the prior authoritative state

Actions that create a new thread turn must persist lane-local start state:

- before the runtime turn is started, set lane `start_state = "starting"`
- if start succeeds, set lane `start_state = "started"`
- if start fails, set lane `start_state = "start_failed"` and persist the error message in that lane
- turn confirmation may come either from the immediate start response or from reconciliation by `client_request_id`
- if start fails before the new turn is confirmed, backend must keep or restore the previous authoritative decision and top-level phase:
  - `Finish Task`: phase remains `ready_for_execution`
  - execution follow-up: phase remains `execution_decision_pending` and `current_execution_decision` remains current
  - `Improve in Execution`: phase remains `audit_decision_pending` and `current_audit_decision` remains current
- if ownership already transferred because a commit-backed artifact was created first, the failure stays on the new lane:
  - `Review in Audit` after `review_commit_sha` is committed remains in `audit_running`

UI must render `start_failed` inline in the owning thread surface together with:

- the error message
- a retry affordance for that lane

UI must not silently stall after the user clicks an action that already committed or transferred ownership.

### Rule 2b: reconcile before authoritative read or write

Before backend answers an authoritative workflow read or validates a mutating action:

- if the local lane is still non-terminal, backend must reconcile runtime progress from app-server lifecycle or `thread/read`
- `GET /workflow-state` must reconcile before returning
- workflow actions must reconcile before validation
- retry actions must reconcile before validation

### Rule 3: `commit succeeded but review/start failed` freezes the artifact

If `Review in Audit` commits successfully and produces `reviewCommitSha = C1`, but `review/start` fails:

- the review artifact remains `reviewCommitSha = C1`
- retry must reuse exactly that reviewed commit
- retry must not create a second commit such as `C2`
- the failure belongs to the audit lane, not the execution lane

This rule prevents retries from reviewing a different artifact than the one the user originally sent to audit.

### Rule 3b: first detached retry must reconcile by `clientRequestId`

The first local review for a finished leaf node creates the review thread with:

- `review/start`
- `delivery = "detached"`
- a persisted `clientRequestId`

The app-server must echo that `clientRequestId` or idempotency identifier in detached-thread creation metadata such as:

- `thread/started`
- review turn metadata
- or equivalent detached review lifecycle payloads

If backend does not know whether detached review thread creation already succeeded:

- retry must reconcile first by `clientRequestId`
- if an existing detached review thread is found, backend adopts that `reviewThreadId`
- only when no existing detached review thread is found may backend call detached creation again

Later local reviews run inline on the existing `reviewThreadId` and do not require detached-thread discovery.

### Rule 3c: every turn-start action must reconcile by persisted `client_request_id`

The same retry and reconciliation principle applies to every backend-started execution or review turn:

- `Finish Task`
- execution follow-up
- `Improve in Execution`
- first detached review start
- later inline review start

Rules:

- backend persists a lane-local `client_request_id` before calling runtime
- app-server must echo that correlation id or an equivalent idempotency identifier in lifecycle metadata
- if retry happens before backend has durably persisted the resulting `turn_id`, backend must reconcile first by `client_request_id`
- if an existing turn is found, backend adopts that `turn_id` instead of starting a duplicate turn
- for detached review creation, the same reconciliation may also need to adopt the resulting `reviewThreadId`

### Rule 4: audit read-only must be runtime-enforced

Audit read-only behavior is not prompt-only guidance.

Review runtime must reject any mutation-capable operation, including:

- editing files
- applying patches
- writing files
- creating commits

Review may only:

- read diffs
- inspect files
- run read-only commands

### Rule 5: single-instance and single-window are platform constraints

PTM v1 officially does not support multi-tab or multi-window workflow for execution and audit.

Platform constraints:

- Electron runs as a single app instance
- only one active window is supported for the current session
- no multi-tab workflow coordinator is required in v1

This constraint is part of the product architecture for v1 and should not be treated as a temporary frontend assumption.

## Action Specification

### Finish Task

Preconditions:

- spec is confirmed
- node is a leaf
- node is not already done
- no execution run is running
- no review cycle is running

Steps:

1. backend validates preconditions
2. backend ensures execution thread exists
3. backend creates `ExecutionRun(trigger_kind = "finish_task")`
4. backend records `start_sha = current HEAD`
5. backend generates and persists execution `client_request_id`
6. backend builds the execution prompt
7. backend sets `execution_start_state = "starting"`
8. backend starts the execution turn using that `client_request_id`
9. if start succeeds or reconciliation finds an existing turn for that `client_request_id`, backend persists `execution_turn_id`, sets `execution_start_state = "started"`, and workflow phase becomes `execution_running`
10. if start fails before the turn is confirmed, backend sets `execution_start_state = "start_failed"`, persists the execution-lane error for retry, and workflow phase remains `ready_for_execution`
11. browser receives raw events and renders transcript live after the turn is confirmed

Completion:

- on successful terminal turn:
  - `ExecutionRun.status = "completed"`
  - `ExecutionRun.decision = "pending"`
  - backend computes `candidate_workspace_hash`
  - backend materializes the current execution decision for that candidate artifact
  - workflow phase becomes `execution_decision_pending`

### Execution Follow-Up Message

Meaning:

- user wants another implement/fix turn on the same execution thread without committing and without sending to audit

Preconditions:

- phase = `execution_decision_pending`
- no execution run is active
- no review cycle is active
- `can_send_execution_message = true`

Steps:

1. user sends a normal execution message
2. backend creates `ExecutionRun(trigger_kind = "follow_up_message")`
3. `ExecutionRun.start_sha` remains the current `HEAD`
4. backend generates and persists execution `client_request_id`
5. backend sets `execution_start_state = "starting"`
6. backend starts another execution turn on the existing execution thread using that `client_request_id`
7. if start succeeds or reconciliation finds an existing turn for that `client_request_id`:
   - backend persists `execution_turn_id`
   - backend supersedes the current execution decision
   - backend sets `execution_start_state = "started"`
   - workflow phase becomes `execution_running`
8. if start fails before the turn is confirmed:
   - backend sets `execution_start_state = "start_failed"` and persists the execution-lane error for retry
   - `current_execution_decision` remains current
   - workflow phase remains `execution_decision_pending`
9. browser streams transcript directly from app-server events after the turn is confirmed

Completion:

- on success:
  - `ExecutionRun.status = "completed"`
  - backend recomputes `candidate_workspace_hash`
  - backend materializes the new current execution decision for the updated candidate artifact
  - phase returns to `execution_decision_pending`

### Mark Done from Execution

Meaning:

- user accepts the current candidate output without local review

Preconditions:

- phase = `execution_decision_pending`
- `current_execution_decision.status = current`
- `source_execution_run.status = completed`
- current workspace hash matches `candidate_workspace_hash`
- no review cycle is active

Steps:

1. backend verifies workspace has not drifted
2. backend commits the current workspace
3. backend sets `ExecutionRun.committed_head_sha = new_head_sha`
4. backend sets `ExecutionRun.decision = "marked_done"`
5. backend sets `accepted_sha = new_head_sha`
6. backend marks node done
7. workflow moves to the next task according to existing progression rules

### Review in Audit

Meaning:

- user wants a local review of the current candidate output as an immutable reviewed commit

Preconditions:

- phase = `execution_decision_pending`
- `current_execution_decision.status = current`
- `source_execution_run.status = completed`
- current workspace hash matches `candidate_workspace_hash`
- no review cycle is active

Steps:

1. backend verifies workspace has not drifted
2. backend commits the current workspace
3. backend sets `review_commit_sha = new_head_sha`
4. backend sets `ExecutionRun.committed_head_sha = review_commit_sha`
5. backend sets `ExecutionRun.decision = "sent_to_review"`
6. backend creates `ReviewCycle` bound to that exact `review_commit_sha`
7. backend transfers workflow ownership to the audit lane immediately after the commit succeeds and workflow phase becomes `audit_running`
8. backend ensures the audit lineage thread exists
9. backend sets `audit_start_state = "starting"`
10. if the node has no review thread yet:
    - backend generates and persists `client_request_id`
    - backend calls `review/start` with `threadId = audit_lineage_thread_id`
    - backend uses `delivery = "detached"`
    - backend sets `target = commit(review_commit_sha)`
11. if the node already has a review thread:
    - backend generates and persists `client_request_id`
    - backend calls `review/start` with `threadId = review_thread_id`
    - backend uses inline delivery semantics
    - backend sets `target = commit(review_commit_sha)`
12. if start succeeds or reconciliation finds an existing review turn for that `client_request_id`, backend persists `review_thread_id`, `review_turn_id`, and `delivery_kind`, then sets `audit_start_state = "started"`
13. if start fails before the review turn is confirmed, backend sets `audit_start_state = "start_failed"` and persists the audit-lane error for retry
14. retry must reuse the same `review_commit_sha` and must not create a new commit

Notes:

- local review does not add extra per-review input to `review/start` in v1
- review thread inherits local review context from the audit lineage thread
- first local review creates the review thread; later local reviews reuse it

### Mark Done from Audit

Meaning:

- user accepts the reviewed implementation

Preconditions:

- phase = `audit_decision_pending`
- `current_audit_decision.status = current`
- `source_review_cycle.lifecycle_status = completed`
- current `HEAD` equals `review_commit_sha`

Steps:

1. backend verifies current `HEAD` matches `review_commit_sha`
2. backend sets `current_audit_decision.status = "accepted"`
3. backend sets `accepted_sha = review_commit_sha`
4. backend marks node done
5. workflow moves to the next task according to existing progression rules

### Improve in Execution

Meaning:

- user wants another execution run based on the latest completed local review output

Preconditions:

- phase = `audit_decision_pending`
- `current_audit_decision.status = current`
- `source_review_cycle.lifecycle_status = completed`
- current `HEAD` equals `review_commit_sha`
- no execution run is active

Steps:

1. backend verifies current `HEAD` still matches `review_commit_sha`
2. backend reads `ReviewCycle.final_review_text` from the latest completed local review cycle
3. backend creates `ExecutionRun(trigger_kind = "improve_from_review")`
4. backend sets `ExecutionRun.source_review_cycle_id = latest_review_cycle_id`
5. backend sets `ExecutionRun.start_sha = review_commit_sha`
6. backend generates and persists execution `client_request_id`
7. backend sets `execution_start_state = "starting"`
8. backend forwards `final_review_text` into a new execution turn using that `client_request_id`
9. if start succeeds or reconciliation finds an existing execution turn for that `client_request_id`:
   - backend persists `execution_turn_id`
   - backend sets `current_audit_decision.status = "improve_requested"`
   - backend sets `execution_start_state = "started"`
   - workflow phase becomes `execution_running`
10. if start fails before the turn is confirmed:
   - backend sets `execution_start_state = "start_failed"` and persists the execution-lane error for retry
   - `current_audit_decision` remains current
   - workflow phase remains `audit_decision_pending`

Notes:

- v1 does not require structured findings extraction
- `exitedReviewMode.review` is the canonical improve input artifact
- the final subtree review on the sealed export commit is handled later by the review-node flow, not here

## Transcript and Metadata Loading Rules

### Transcript loading

Execution and local review transcript loading must mirror CodexMonitor:

- live:
  - raw app-server event
  - client reducer
  - UI
- reload:
  - client thread service calls `thread/read`
  - client rebuilds local thread items
  - client resubscribes to live thread stream if needed

### Metadata loading

Execution and audit metadata comes from two backend sources:

- `workflow-state` provides:
  - `workflowPhase`
  - `executionThreadId`
  - `auditLineageThreadId`
  - `reviewThreadId`
  - CTA enablement
  - runtime block and active request state
  - current decision objects
  - candidate and review artifact metadata needed for validation and display
- `detail-state` provides:
  - task title
  - frame/spec context
  - parent split and clarify context
  - hierarchy and other PTM shell metadata

These values are fetched separately from transcript loading and must not block transcript rendering.

Rules:

- execution transcript hydrates by `execution_thread_id`
- audit transcript hydrates by `review_thread_id` once present
- client must not discover execution or review transcript by `(projectId, nodeId, threadRole)` in the target architecture
- if mirrored fields conflict, `workflow-state` wins

### Audit tab loading

Audit UI has two surfaces:

- readonly audit metadata shell before first local review
- live review thread after `review_thread_id` exists

Rules:

- before first local review, audit tab renders metadata from `workflow-state` and `detail-state` and does not hydrate a review transcript
- once `review_thread_id` exists, audit tab hydrates from that review thread
- audit lineage thread is not the main audit transcript surface after the first review thread is created

## Git and Commit Semantics

- `ExecutionRun.start_sha` is the Git `HEAD` when the execution run starts
- execution completion does not auto-commit
- follow-up execution messages do not auto-commit
- `Mark Done from Execution` commits current workspace and sets `accepted_sha`
- `Review in Audit` commits current workspace and creates immutable `review_commit_sha`
- `Mark Done from Audit` accepts the already-reviewed `review_commit_sha`
- `Improve in Execution` starts the next execution run from `review_commit_sha`
- every decision action must fail fast if the expected workspace hash or commit has drifted
- if UI later needs a diff base for display, it may derive it from the parent of `review_commit_sha`; that parent is not the authoritative gating field for this workflow

## UI Rules

Execution UI:

- transcript renders from thread items only
- prefix metadata renders from `workflow-state` and `detail-state`
- execution composer is enabled when `can_send_execution_message = true`
- execution CTA buttons render from workflow state only

Audit UI:

- before the first review, audit tab renders readonly metadata only
- after `review_thread_id` exists, transcript renders from review-thread items only
- review metadata prefix renders from `workflow-state` and `detail-state`
- generic composer is disabled in standard workflow mode
- audit CTA buttons render from workflow state only

## Failure Handling

Failures remain attached to the owning thread lane instead of introducing extra top-level workflow phases.

Execution-lane failure handling:

- persist the execution-lane error message
- keep the error visible in the execution thread surface
- render retry in the execution thread surface

Audit-lane failure handling:

- persist the audit-lane error message
- keep the error visible in the audit surface
- render retry in the audit surface
- for first detached review creation, reconcile by `client_request_id` before attempting detached creation again
- for later inline review cycles on an existing `review_thread_id`, retry the review start inline on that review thread

Start failures must preserve the already-created decision artifact for that lane.

Browser refresh or app close:

- transcript recovery uses `thread/read`
- workflow correctness remains with backend decision state and reconciliation
- workflow completion must never depend on browser presence

## Acceptance Criteria

This redesign is considered correct when:

- execution completion does not auto-trigger audit
- execution remains writable for follow-up implement turns in `execution_decision_pending`
- a follow-up or improve request supersedes the previous decision only after the new turn is confirmed
- a pre-start failure before turn confirmation keeps or restores the previous authoritative decision and phase
- audit lineage remains the canonical node-context thread
- first local review creates a review thread by `review/start(detached)` from the audit lineage thread
- later local reviews reuse the same review thread by `review/start` on that thread
- local review remains review-only and never mutates workspace
- `Review in Audit` always reviews an immutable `review_commit_sha`
- `Improve in Execution` uses the latest completed `exitedReviewMode.review` output in v1
- `workflow-state` is authoritative for phase, thread ids, CTA gating, and runtime state; `detail-state` is display metadata only
- all backend-started execution and review turns persist `client_request_id` and reconcile by it on retry before issuing a duplicate start
- `ReviewCycle` lifecycle and reviewer disposition remain separate concepts; CTA gating uses lifecycle plus decision state, not reviewer disposition alone
- transcript reload for execution and local review comes from `thread/read`, not backend-built `hydratedItems`
- task title, frame/spec context, and review metadata render independently from transcript hydration
- backend workflow state remains authoritative for CTA gating and decision correctness
- no PTM-owned per-delta transcript archive is required in v1
