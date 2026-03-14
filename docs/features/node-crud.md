# Node CRUD

## Scope

Phase F keeps per-node documents authoritative, adds lifecycle confirmation, exposes explicit AI spec generation, and routes the frontend through document-first editing flows:

- `task.md` owns `title`, `purpose`, and `responsibility`
- `briefing.md` owns contextual document fields
- `spec.md` owns contract fields
- `state.yaml` owns machine state
- `tree.json` remains the structural index plus synced caches for `phase` and thread/chat IDs
- shipping frontend task, briefing, and spec editing uses document endpoints and lifecycle routes directly

Persisted `tree.json` in schema v5 does not store `title` or `description`.

## Routes

- `PATCH /v1/projects/{project_id}/active-node`
- `POST /v1/projects/{project_id}/nodes`
- `PATCH /v1/projects/{project_id}/nodes/{node_id}`
- `GET /v1/projects/{project_id}/nodes/{node_id}/documents`
- `GET /v1/projects/{project_id}/nodes/{node_id}/documents/task`
- `PUT /v1/projects/{project_id}/nodes/{node_id}/documents/task`
- `GET /v1/projects/{project_id}/nodes/{node_id}/documents/briefing`
- `PUT /v1/projects/{project_id}/nodes/{node_id}/documents/briefing`
- `GET /v1/projects/{project_id}/nodes/{node_id}/documents/spec`
- `PUT /v1/projects/{project_id}/nodes/{node_id}/documents/spec`
- `GET /v1/projects/{project_id}/nodes/{node_id}/documents/state`
- `POST /v1/projects/{project_id}/nodes/{node_id}/confirm-task`
- `POST /v1/projects/{project_id}/nodes/{node_id}/confirm-briefing`
- `POST /v1/projects/{project_id}/nodes/{node_id}/confirm-spec`
- `POST /v1/projects/{project_id}/nodes/{node_id}/generate-spec`
- `POST /v1/projects/{project_id}/nodes/{node_id}/start-execution`
- `POST /v1/projects/{project_id}/nodes/{node_id}/complete`

## Create Child

- Request body: `{ parent_id }`
- Create a new `tree.json` entry without `title` or `description`
- Create node files with default task content: `title = "New Node"`, `purpose = ""`, `responsibility = ""`
- Append to the parent `child_ids`
- Compute `depth`, `display_order`, and `hierarchical_number`
- The first active child is `ready`; later active siblings are `locked`
- If the parent or any ancestor is `locked`, the new child stays `locked`
- If a leaf parent was `ready` or `in_progress`, downgrade it to `draft`
- Reject child creation for `done` or superseded nodes
- Set `active_node_id` to the new child node id

## Update Node

Legacy `PATCH /nodes/{node_id}` remains for backward compatibility:

- Request body: `{ title?, description? }`
- `title` maps to `task.title`
- `description` maps to `task.purpose`
- Empty body is rejected with `400`
- Empty `title` is rejected with `400`
- Superseded or `done` nodes are rejected with `409`
- Edits are rejected with `409` while `phase=executing`
- If the task was already confirmed, content-changing updates clear downstream confirmations and step the node back to `planning`
- The route no longer writes `title` or `description` into persisted `tree.json`
- Public snapshots still return `title` and `description` by loading `task.md`

## Document CRUD

### `GET /documents`

Returns all four node documents:

```json
{
  "task": {
    "title": "Implement Catalog UI",
    "purpose": "Build the browsing interface.",
    "responsibility": "Own the catalog page."
  },
  "briefing": {
    "user_notes": "",
    "business_context": "",
    "technical_context": "",
    "execution_context": "",
    "clarified_answers": ""
  },
  "spec": {
    "business_contract": "",
    "technical_contract": "",
    "delivery_acceptance": "",
    "assumptions": ""
  },
  "state": {
    "phase": "planning",
    "task_confirmed": false,
    "briefing_confirmed": false,
    "spec_generated": false,
    "spec_generation_status": "idle",
    "spec_confirmed": false,
    "planning_thread_id": "",
    "execution_thread_id": "",
    "ask_thread_id": "",
    "planning_thread_forked_from_node": "",
    "planning_thread_bootstrapped_at": "",
    "chat_session_id": ""
  }
}
```

### `PUT /documents/task`

- Partial merge body: `{ title?, purpose?, responsibility? }`
- At least one field is required
- `title` must remain non-empty if provided
- Reject superseded or `done` nodes with `409`
- Reject edits while `phase=executing` with `409`
- If `task_confirmed=true`, content-changing updates clear `task_confirmed`, `briefing_confirmed`, and `spec_confirmed`, then step phase back to `planning`

### `PUT /documents/briefing`

- Partial merge body:
  `{ user_notes?, business_context?, technical_context?, execution_context?, clarified_answers? }`
- At least one field is required
- Reject superseded or `done` nodes with `409`
- Reject edits while `phase=executing` with `409`
- If `briefing_confirmed=true`, content-changing updates clear `briefing_confirmed` and `spec_confirmed`, then step phase back to `briefing_review`

### `PUT /documents/spec`

- Partial merge body:
  `{ business_contract?, technical_contract?, delivery_acceptance?, assumptions? }`
- At least one field is required
- Reject superseded or `done` nodes with `409`
- Reject edits while `phase=executing` with `409`
- The first content-changing save sets `state.spec_generated = true`
- If `spec_confirmed=true`, content-changing updates clear `spec_confirmed` and step phase back to `spec_review`

### `POST /generate-spec`

- No request body
- Allowed only while `phase in {"spec_review", "ready_for_execution"}`
- Reject superseded, `done`, `executing`, `closed`, planning-active, or already-generating nodes with `409`
- Builds AI prompt context from the project root goal, parent chain, current `task.md`, current `briefing.md`, and current `spec.md`
- AI output replaces the full `spec.md`
- Success sets `state.spec_generated = true`
- Success returns `{ spec, state }`
- `state.spec_generation_status` transitions:
  - `generating` while the request is in flight
  - `idle` on success
  - `failed` on model/validation failure
- If the node was already in `ready_for_execution`, generated spec persistence follows the normal spec-edit lifecycle path and steps the node back to `spec_review`

### `GET /documents/state`

- Read-only machine state
- No write endpoint exists for `state.yaml`

## Confirmation And Execution Lifecycle

### `POST /confirm-task`

- Requires the node to be mutable and currently in `phase=planning`
- Requires non-empty `task.title` and `task.purpose`
- Sets `state.task_confirmed = true`
- Advances phase to `briefing_review`
- Returns `{ state }`

### `POST /confirm-briefing`

- Requires the node to be mutable and currently in `phase=briefing_review`
- Requires `state.task_confirmed = true`
- Sets `state.briefing_confirmed = true`
- Advances phase to `spec_review`
- Returns `{ state }`

### `POST /confirm-spec`

- Requires the node to be mutable and currently in `phase=spec_review`
- Requires `state.briefing_confirmed = true`
- Requires `state.spec_generated = true`
- Sets `state.spec_confirmed = true`
- Advances phase to `ready_for_execution`
- Returns `{ state }`

### `POST /start-execution`

- Requires the node to be mutable and in `phase=ready_for_execution` to advance
- Repeated calls while already in `phase=executing` reuse that lifecycle state
- Advances phase to `executing`
- Ensures an execution thread/chat session exists
- Returns the execution chat session payload

### `POST /complete`

- Requires a leaf node with `status in {"ready", "in_progress"}`
- Requires `phase in {"ready_for_execution", "executing"}`
- Marks the node `status=done`
- Sets `state.phase = "closed"`
- Continues to unlock sibling and cascade parent completion as before

## Active Node

- `PATCH /active-node` accepts `{ active_node_id: string | null }`
- Persist manual selection changes
- On load, the frontend restores `active_node_id` or falls back to the root node

## Snapshot Compatibility

- Internal `tree.json` no longer persists `title` or `description`
- Public snapshots still expose `title` and `description`
- `SnapshotViewService` backfills those fields from `task.md`
- Legacy `PATCH /nodes/{node_id}` remains compatibility-only; the shipping frontend no longer depends on it
