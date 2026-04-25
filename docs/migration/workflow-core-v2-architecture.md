# Workflow Core V2 Architecture

Workflow Core V2 is the canonical business workflow layer for node planning,
execution, audit, package review, context binding, and workflow events.

It sits beside Session Core V2:

- Session Core V2 owns Codex-native runtime primitives: session connection,
  threads, turns, items, pending requests, and session event streams under
  `/v4/session/*`.
- Workflow Core V2 owns PlanningTree business state and decides which session
  thread should be used for each workflow role.

## Package Layout

```text
backend/business/workflow_v2/
  __init__.py
  models.py
  state_machine.py
  repository.py
  thread_binding.py
  context_packets.py
  context_builder.py
  artifact_orchestrator.py
  execution_audit_orchestrator.py
  events.py
  errors.py
```

## Module Responsibilities

### `models.py`

Canonical Pydantic models:

- `WorkflowPhase`
- `ThreadRole`
- `WorkflowAction`
- `NodeWorkflowStateV2`
- `ThreadBinding`
- `PlanningTreeContextPacket`
- execution/audit/package review decision models
- API response models where route-local models are not enough

`allowed_actions` may appear in API responses, but it should be derived by the
state machine whenever possible.

### `state_machine.py`

Pure domain transition logic.

Allowed dependencies:

- `models.py`
- `errors.py`
- Python standard library

Forbidden dependencies:

- storage
- FastAPI routes
- Codex/session clients
- SSE/event broker
- V3 workflow service

The state machine should answer:

- What phase is next?
- What actions are allowed?
- Which domain events should be emitted?
- Which deterministic error should be raised for invalid commands?

### `repository.py`

Persistence boundary for Workflow V2 state and related metadata.

Responsibilities:

- read/write canonical V2 state
- increment `state_version`
- preserve `schema_version`, `created_at`, and `updated_at`
- store idempotency records or delegate to a dedicated idempotency ledger
- convert legacy workflow state into a V2 view during migration

The existing storage path currently uses a `workflow_v2` directory name, but its
payload shape is still legacy-oriented. Do not treat that file shape as the
canonical V2 model without a converter.

### `thread_binding.py`

Backend-owned binding between workflow roles and Session Core V2 thread ids.

The public service should expose:

```python
class ThreadBindingServiceV2:
    def ensure_thread(
        self,
        *,
        project_id: str,
        node_id: str,
        role: ThreadRole,
        model: str | None = None,
        model_provider: str | None = None,
        force_rebase: bool = False,
    ) -> ThreadBinding:
        ...
```

The service owns:

- create/reuse/rebase decisions
- context packet hash bookkeeping
- source artifact version pinning
- calls into Session Core V2 for `thread/start` and `thread/inject_items`

The frontend must not decide whether a workflow role uses a new thread, fork, or
existing thread.

### `context_packets.py`

Canonical context packet models.

Required packet kinds:

- `ask_planning_context`
- `child_activation_context`
- `execution_context`
- `audit_context`
- `package_review_context`
- `context_update`

Packets are JSON models first. Delivery to Codex can initially be a neutral
model-visible context message:

```text
<planning_tree_context kind="execution_context" schema_version="1">
{...json...}
</planning_tree_context>
```

The backend should preserve the JSON packet and compute the packet hash before
rendering it into any message/item format.

### `context_builder.py`

Builds context packets from project, node, artifact, split, and parent/child
state.

Responsibilities:

- collect source versions
- build deterministic packet payloads
- compute packet hashes
- determine whether context is stale
- build rebase/update packets

### `execution_audit_orchestrator.py`

Canonical business logic for execution and audit workflows.

Target public methods:

```python
class ExecutionAuditOrchestratorV2:
    def start_execution(...): ...
    def complete_execution(...): ...
    def mark_done_from_execution(...): ...
    def start_audit(...): ...
    def accept_audit(...): ...
    def request_improvements(...): ...
    def start_package_review(...): ...
```

Current V3 `improve-in-execution` maps to the V2
`request_improvements`/execution-improve flow. V4 `audit/request-changes` is a
separate audit decision endpoint and should not be collapsed into that existing
Breadcrumb action without a deliberate UI change.

The orchestrator may depend on:

- `state_machine.py`
- `repository.py`
- `thread_binding.py`
- `context_builder.py`
- artifact/git services
- Session Core V2 manager/protocol client
- event publisher

It should not depend on V3 route code. During migration, the legacy
`ExecutionAuditWorkflowService` calls this orchestrator and converts results to
legacy shapes.

### `artifact_orchestrator.py`

Coordinates non-chat artifact jobs:

- frame
- spec
- clarify
- split

Artifact jobs should remain distinct from regular session chat. They may inject
confirmed artifact summaries into active threads, but generation and persistence
remain artifact workflows.

### `events.py`

Canonical Workflow V2 event models.

Event types:

- `workflow/state_changed`
- `workflow/context_stale`
- `workflow/action_completed`
- `workflow/action_failed`

Workflow events must not be mixed into Session Core V2 thread event streams.

### `errors.py`

Domain error codes and route mapping.

Suggested codes:

- `ERR_WORKFLOW_NOT_FOUND`
- `ERR_WORKFLOW_ACTION_NOT_ALLOWED`
- `ERR_WORKFLOW_CONTEXT_STALE`
- `ERR_WORKFLOW_THREAD_BINDING_FAILED`
- `ERR_WORKFLOW_IDEMPOTENCY_CONFLICT`
- `ERR_WORKFLOW_ARTIFACT_VERSION_CONFLICT`
- `ERR_WORKFLOW_EXECUTION_FAILED`
- `ERR_WORKFLOW_AUDIT_FAILED`

## Canonical State Shape

Baseline fields:

```python
WorkflowPhase = Literal[
    "planning",
    "ready_for_execution",
    "executing",
    "execution_completed",
    "review_pending",
    "audit_running",
    "audit_needs_changes",
    "audit_accepted",
    "done",
    "blocked",
]

ThreadRole = Literal[
    "ask_planning",
    "execution",
    "audit",
    "package_review",
]

class NodeWorkflowStateV2(BaseModel):
    schema_version: int = 1
    state_version: int = 0
    project_id: str
    node_id: str
    phase: WorkflowPhase

    ask_thread_id: str | None = None
    execution_thread_id: str | None = None
    audit_thread_id: str | None = None
    package_review_thread_id: str | None = None

    active_execution_run_id: str | None = None
    latest_execution_run_id: str | None = None
    active_audit_run_id: str | None = None
    latest_audit_run_id: str | None = None

    current_execution_decision: dict | None = None
    current_audit_decision: dict | None = None

    workspace_hash: str | None = None
    base_commit_sha: str | None = None
    head_commit_sha: str | None = None

    frame_version: int | None = None
    spec_version: int | None = None
    split_manifest_version: int | None = None

    context_stale: bool = False
    context_stale_reason: str | None = None
    blocked_reason: str | None = None
    last_error: dict | None = None

    created_at: str | None = None
    updated_at: str | None = None
```

`allowed_actions` is returned by API views and computed from the state machine.

Public API adapters convert this internal shape to camelCase. The V4 state
response uses `phase` and `version`; `version` maps from internal
`state_version`. Legacy V3 adapters may continue returning `workflowPhase`,
`executionThreadId`, `reviewThreadId`, and other existing field names.

Legacy phase conversion:

| Legacy V3 `workflowPhase` | Canonical V2 `phase` |
| --- | --- |
| `idle` | `ready_for_execution` |
| `execution_running` | `executing` |
| `execution_decision_pending` | `execution_completed` |
| `audit_running` | `audit_running` |
| `audit_decision_pending` | `review_pending` |
| `done` | `done` |
| `failed` | `blocked` |

## V3 Compatibility Strategy

During migration:

```text
V3 route
  -> ExecutionAuditWorkflowService compatibility adapter
  -> Workflow Core V2 orchestrator
  -> V2 repository/state machine
  -> V3 response converter
```

The adapter must preserve old response shapes until the old UI path is retired.
Once the new Breadcrumb V2 path is fully V2-owned, V3 routes can be deprecated or
kept read-only.

## Session Integration Points

Use the actual Session Core V2 implementation paths:

- `backend/session_core_v2/connection/manager.py`
- `backend/session_core_v2/protocol/client.py`
- `backend/session_core_v2/storage/runtime_store.py`
- `backend/routes/session_v4.py`

Required Session Core V2 methods for Workflow Core V2:

- `thread/start`
- `thread/resume`
- `thread/read`
- `turn/start`
- `thread/inject_items`
- optionally `review/start`

Workflow routes should call workflow services, not session route handlers.
