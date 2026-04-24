# S0 Codex Parity Method Map v1

Status: Normative

This map defines how PlanningTree `/v4/session/*` surfaces Codex-native semantics.
Wrapper behavior is intentionally thin.

## Connection

1. `POST /v4/session/initialize` -> JSON-RPC `initialize`
2. Internal transition only (not public REST by default):
   - JSON-RPC notification `initialized`
3. `GET /v4/session/status` -> connection state from session manager

## Thread lifecycle

1. `POST /v4/session/threads/start` -> `thread/start`
2. `POST /v4/session/threads/{threadId}/resume` -> `thread/resume`
3. `POST /v4/session/threads/{threadId}/fork` -> `thread/fork`
4. `GET /v4/session/threads/list` -> `thread/list`
5. `GET /v4/session/threads/{threadId}/read` -> `thread/read`
6. `GET /v4/session/threads/{threadId}/turns` -> `thread/turns/list` (or equivalent read projection)
7. `GET /v4/session/threads/loaded/list` -> `thread/loaded/list`
8. `POST /v4/session/threads/{threadId}/unsubscribe` -> `thread/unsubscribe`

Phase-gated:

1. `POST /v4/session/threads/{threadId}/archive` -> `thread/archive`
2. `POST /v4/session/threads/{threadId}/unarchive` -> `thread/unarchive`
3. `POST /v4/session/threads/{threadId}/name/set` -> `thread/name/set`
4. `POST /v4/session/threads/{threadId}/metadata/update` -> `thread/metadata/update`
5. `POST /v4/session/threads/{threadId}/rollback` -> `thread/rollback`
6. `POST /v4/session/threads/{threadId}/compact/start` -> `thread/compact/start`

## Turn lifecycle

1. `POST /v4/session/threads/{threadId}/turns/start` -> `turn/start`
2. `POST /v4/session/threads/{threadId}/turns/{turnId}/steer` -> `turn/steer` with `expectedTurnId={turnId}`
3. `POST /v4/session/threads/{threadId}/turns/{turnId}/interrupt` -> `turn/interrupt`
4. `POST /v4/session/threads/{threadId}/inject-items` -> `thread/inject_items`

## Server-request lifecycle

Server-initiated JSON-RPC requests are emitted as pending requests and must be resolved via:

1. `GET /v4/session/requests/pending`
2. `POST /v4/session/requests/{requestId}/resolve`
3. `POST /v4/session/requests/{requestId}/reject`

Authoritative request state is event-driven:

- `serverRequest/created`
- `serverRequest/updated`
- `serverRequest/resolved`

`serverRequest/created` is emitted once for a new pending request. `serverRequest/updated` carries status or metadata changes such as `submitted`, `expired`, and `rejected`. `serverRequest/resolved` is retained for compatibility with upstream notifications and should include the full request record when the registry can resolve it.

Turn/item completion remains event-driven:

- terminal `item/completed`
- terminal `turn/completed`

## Event stream

`GET /v4/session/threads/{threadId}/events` streams canonical envelopes whose `method` values are Codex notification names:

- `thread/*`
- `turn/*`
- `item/*`
- `serverRequest/*`
- `error`

No semantic remapping of method names is allowed in V2.
