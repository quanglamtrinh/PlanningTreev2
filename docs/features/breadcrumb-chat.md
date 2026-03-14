# Breadcrumb Chat

## Goal

Deliver the execution loop for a leaf node:

1. User clicks `Finish Task` in the graph.
2. App navigates to `/projects/:projectId/nodes/:nodeId/chat`.
3. Breadcrumb chat streams responses from the Codex app server over SSE.
4. User clicks `Mark Done` to complete the node and advance the tree.

## Session Lifecycle

- Chat session identity is implicit: `(project_id, node_id)`.
- Session state is stored in `projects/<project-id>/chat_state.json`.
- The file is a top-level node map:

```json
{
  "<node_id>": {
    "project_id": "string",
    "node_id": "string",
    "thread_id": "string | null",
    "active_turn_id": "string | null",
    "config": {
      "access_mode": "project_write | read_only",
      "cwd": "string",
      "writable_roots": ["string"],
      "timeout_sec": 120
    },
    "messages": [
      {
        "message_id": "string",
        "role": "user | assistant",
        "content": "string",
        "status": "pending | streaming | completed | error",
        "created_at": "ISO timestamp",
        "updated_at": "ISO timestamp",
        "error": "string | null"
      }
    ]
  }
}
```

- `GET /chat/session` lazily normalizes missing or partial session state.
- If `active_turn_id` is present on session load, it is treated as stale after restart:
  - `active_turn_id` is cleared
  - the latest assistant message in `pending` or `streaming` is marked `error`
  - the error message is `Session interrupted - the server restarted before this response completed.`

## Message And Event Types

### Chat messages

- User messages are created with `status = completed`.
- Assistant messages start as `pending`, transition to `streaming` during deltas, then end as `completed` or `error`.

### SSE events

- `message_created`
  - payload: `active_turn_id`, `user_message`, `assistant_message`
- `assistant_delta`
  - payload: `message_id`, `delta`, `content`, `updated_at`
- `assistant_completed`
  - payload: `message_id`, `content`, `updated_at`, `thread_id`
- `assistant_error`
  - payload: `message_id`, `content`, `updated_at`, `error`
- `session_reset`
  - payload: `session`

### SSE transport

- Endpoint: `GET /v1/projects/{project_id}/nodes/{node_id}/chat/events`
- Events are streamed as SSE `message` events with JSON payloads.
- When no event is ready for 15 seconds, the server emits `: heartbeat`.
- The frontend relies on native `EventSource` auto-reconnect.
- On reconnect, the client reloads the session once to recover any missed updates because the stream has no replay cursor.

## Finish Task Flow

- `Finish Task` is client-side only.
- The graph workspace:
  - flushes pending edits for the selected node if needed
  - flushes the target node draft even when it is already selected
  - builds this transient seed text:

```text
Task: {title}
Description: {description}

Please help me complete this task.
```

- The app navigates to `/projects/:projectId/nodes/:nodeId/chat` with router state:

```ts
{ composerSeed: string }
```

- `BreadcrumbWorkspace` applies that seed once into the local chat composer, then clears the router state with `replace`.
- The seed is transient only:
  - refresh does not restore it
  - leaving and reopening the route does not restore it
  - sent messages remain persisted in session history

## Node Status Rules

- First accepted `POST /chat/messages` promotes the node from `ready` to `in_progress`.
- `in_progress` persists until explicit completion.
- Resetting the chat session does not change node status.
- The backend does not restrict chat to `ready` nodes only; `Finish Task` is the guarded execution entrypoint in the graph UI.

## Mark Done Flow

- `Mark Done` uses the existing endpoint:
  - `POST /v1/projects/{project_id}/nodes/{node_id}/complete`
- The button is enabled only for leaf nodes with status `ready` or `in_progress`.
- On success:
  - the node becomes `done`
  - the next eligible locked sibling becomes `ready`
  - ancestor cascade runs through the existing completion logic
  - the UI navigates back to the graph workspace

## Internal Chat Config Defaults

- Phase 4 does not expose config editing in the API or UI.
- Default session config:

```json
{
  "access_mode": "project_write",
  "cwd": "<project_workspace_root>",
  "writable_roots": ["<project_workspace_root>"],
  "timeout_sec": 120
}
```

- Config values are still normalized and validated to stay under `project_workspace_root`.

## Acceptance Criteria

- `Finish Task` opens breadcrumb chat with a transient prefilled composer.
- Sending the first message promotes `ready -> in_progress`.
- Assistant output appears incrementally via SSE.
- Reload preserves message history but not the unsent transient composer seed.
- `Reset` clears chat history and thread state only.
- `Mark Done` completes the node and returns to the graph with sibling unlock and ancestor cascade visible.
