# Session V2 Boundary

`session_v2` is the frontend boundary for the native session runtime. It owns
session transport state and protocol projection only. It must not own PlanningTree
workflow business logic.

## Owns

- Initialize/status for the session connection.
- Thread lifecycle commands: start, resume, fork, list, read, select, and loaded
  thread hydration.
- Turn lifecycle commands: start, steer, interrupt, and turn hydration.
- Server request handling: pending request discovery, resolve, reject, and
  request UI models.
- Event projection: thread, turn, item, token usage, stream connection, replay,
  reconnect, cursor, and gap state.
- Generic console UI state derived from session protocol data: active thread,
  active turns, active items, running turn, selected model, stream status, and
  runtime errors.

## Does Not Own

- Lane semantics such as `ask`, `execution`, or `audit`.
- Mapping project/node workflow lanes to session thread ids.
- Review decisions, audit decisions, execution decisions, or approval meaning
  beyond generic server request resolution.
- Workflow actions such as mark done, review in audit, improve in execution, or
  graph navigation after those actions.
- Graph mutations, node mutations, artifact workflow state, or project route
  canonicalization.
- Business queue policy for ask/execution/audit followups.

## State Ownership

Backend/session manager is authoritative for protocol state. The frontend stores
under `session_v2/store` are projection caches for rendering and interaction:

- `connectionStore` projects connection phase and connection errors.
- `threadSessionStore` projects threads, turns, items, event cursors, stream
  connection state, gap detection, and token usage.
- `pendingRequestsStore` projects server requests that need user resolution.

Workflow state stays outside `session_v2`. Containers such as breadcrumb views
may read workflow state and pass session-oriented props into `session_v2`
components, but `session_v2` must not import workflow stores or encode workflow
lane rules.

## Command Ownership

`session_v2/facade` exposes generic session commands:

- `bootstrap`
- `selectThread`
- `createThread`
- `forkThread`
- `refreshThreads`
- `submitSessionAction`
- `setModel`
- `submit`
- `interrupt`
- `resolveRequest`
- `rejectRequest`

Callers own business decisions about when these commands are invoked. For
example, a breadcrumb container may decide that the active `audit` lane maps to a
review thread id, then call `selectThread(threadId)`. The session facade only
selects that thread; it does not know why the thread was chosen.

`resolveRequest` and `rejectRequest` are facade conveniences that submit
`request.resolve` / `request.reject` actions through `submitSessionAction`.
