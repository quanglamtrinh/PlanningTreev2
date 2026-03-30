# Execution and Audit Redesign Overview

Status: draft overview. Summarizes the target workflow and thread model after the execution and audit rework.

Related docs:

- `docs/thread-rework/workflow-rework/execution-audit-workflow-spec.md`
- `docs/thread-rework/workflow-rework/execution-audit-api-internal-contract-spec.md`
- `docs/thread-rework/workflow-rework/execution-thread-redesign-spec.md`
- `docs/thread-rework/workflow-rework/audit-thread-redesign-spec.md`

## Why This Redesign Exists

The current PTM model mixes two concerns too tightly:

- transcript streaming and rendering
- workflow and task correctness

That makes execution and audit slower and harder to reason about than they need to be.

The redesign separates those concerns:

- transcript should behave like CodexMonitor
- workflow should remain PTM-specific and backend-owned

## Old Model

Execution and audit were effectively treated as backend-projected thread snapshots:

- raw event
- backend adapter
- backend projector
- per-delta snapshot mutation
- canonical event to frontend
- frontend render

This model optimized for backend-owned transcript state, but it added latency and complexity to live thread behavior.

## New Model

### Transcript lane

Execution transcript and review transcript follow the same high-level shape as CodexMonitor:

- raw app-server event
- client reducer
- UI

Reload also follows the same shape:

- client thread service calls `thread/read`
- client rebuilds thread items locally
- client resubscribes to live thread events if needed

Transcript source of truth is:

- app-server thread history
- current browser reducer state

PTM v1 does not maintain a separate local execution or review transcript archive.

### Workflow lane

PTM backend still owns:

- `ExecutionRun`
- `ReviewCycle`
- current execution and audit decision points
- workflow phase
- Git drift checks
- `Mark Done`
- `Review in Audit`
- `Improve in Execution`
- lane-local start state and decision reconciliation

Workflow source of truth is:

- backend workflow state
- persisted run and review-cycle records

### Metadata lane

Task title, frame/spec context, parent split context, review commit metadata, cycle IDs, and CTA state are not transcript data.

They are fetched separately from backend workflow/detail state and rendered independently from thread items.

This keeps PTM-specific metadata from slowing down transcript hydration or live streaming.

## Audit Lane Model

The audit lane now has two different thread roles:

- `audit lineage thread`
- `review thread`

### Audit lineage thread

The audit lineage thread remains the canonical context thread for the node.

It stores the context the local reviewer should inherit, such as:

- node-local `spec.md` expectations
- task frame
- parent clarify and split context

The `spec.md` reference here is node-local task context, not a repo-global hardcoded path such as `docs/spec.md`.

For finished leaf nodes in the execution/audit workflow, this thread is readonly in standard workflow mode. It is not the main live review transcript surface.

### Review thread

The review thread is the canonical local-review history surface for a finished leaf node.

Rules:

- first local review creates it by calling `review/start` with `delivery = "detached"` from the audit lineage thread
- later local reviews call `review/start` again on the same review thread
- the review thread inherits context from the audit lineage thread, so normal local reviews do not add extra input at `review/start`
- canonical local review output is `exitedReviewMode.review`

This split lets PTM keep audit lineage semantics while using app-server review mode for actual code review.

## Workflow Summary

### Execution

1. User clicks `Finish Task`.
2. Backend creates an execution run and starts the execution turn.
3. Browser streams transcript directly from app-server events.
4. When execution completes, workflow enters `execution_decision_pending`.
5. User chooses:
   - `Mark Done`
   - `Review in Audit`
   - or sends another follow-up message in execution

### Audit

1. User clicks `Review in Audit`.
2. Backend commits current candidate output and creates a `ReviewCycle` for `reviewCommitSha`.
3. If the node has no review thread yet, backend calls `review/start` with `delivery = "detached"` from the node's audit lineage thread.
4. If the node already has a review thread, backend calls `review/start` again on that review thread.
5. Browser streams the review thread transcript directly from app-server events.
6. When review completes, workflow enters `audit_decision_pending`.
7. User chooses:
   - `Mark Done`
   - `Improve in Execution`

### Improve Loop

`Improve in Execution` uses the latest completed `exitedReviewMode.review` output in v1.

There is no requirement in v1 to extract structured findings before creating the next execution run.

### Final subtree review

The final subtree review on the sealed export commit belongs to the review-node flow, not the local audit lane described in this doc set.

## Role Separation

### Execution thread

- purpose: implement and fix
- writable: yes
- generic composer: enabled when workflow allows follow-up execution messages
- auto-review: no

### Audit lineage thread

- purpose: canonical node context and lineage
- writable: no generic composer in standard workflow mode after `Finish Task`
- runtime policy: readonly for local-review workflow usage
- not the primary live review surface once a review thread exists

### Review thread

- purpose: local-review history for a finished leaf node
- created by: first `review/start(detached)` from the audit lineage thread
- reused by: later local reviews via `review/start` on the same review thread
- runtime policy: review-only
- canonical output: `exitedReviewMode.review`

## Why This Is Close to CodexMonitor

The redesigned transcript path intentionally matches CodexMonitor's mental model:

- app-server owns thread history
- client owns transcript merge
- reload uses `thread/read`
- reconnect is a client transport concern

PTM stays different only where it needs to:

- workflow correctness
- task progression
- Git and commit decisions
- review-cycle lifecycle

## Backend Reconciliation Still Matters

Removing per-delta backend transcript projection does not remove the need for backend reconciliation.

Backend reconciliation is still required because browser state is not allowed to decide:

- whether execution or review really completed
- whether workflow phase should advance
- whether drift checks passed
- whether `Mark Done` or `Improve in Execution` is valid
- whether the current lane is in `starting`, `start_failed`, or `waiting_user_input`
- whether a requested execution or review turn already exists for the current `clientRequestId`
- whether reviewer disposition metadata has changed independently of workflow decision state

The browser owns transcript feel.

The backend owns workflow correctness.

## Key Consequences

- Live transcript becomes faster and simpler.
- Reload behavior becomes closer to CodexMonitor.
- Prefix and workflow metadata become independent from transcript bootstrap.
- Execution remains recoverable because transcript comes from app-server history and workflow comes from backend state.
- Audit lineage and review history are separated cleanly.
- Follow-up or improve requests only supersede the previous decision after the new turn is actually confirmed.
- Review lifecycle and reviewer disposition are modeled separately, so reviewer feedback does not silently override user workflow decisions.
- PTM no longer needs to project every delta into a backend transcript snapshot for execution or local review.

## Target Mental Model

Use this mental model when implementing the redesign:

- execution is a normal live thread from the transcript point of view
- local review is a normal app-server review thread from the transcript point of view
- audit lineage is context, not the main local review transcript
- workflow actions happen outside the thread transcript
- backend decides what actions are allowed
- client decides how transcript is rendered and resumed

That split is the core of the redesign.
