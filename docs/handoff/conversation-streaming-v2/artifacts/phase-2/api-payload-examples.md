# Phase 2 API Payload Examples

These examples reflect the implemented additive V2 backend path.

## `GET /v2/projects/{project_id}/nodes/{node_id}/threads/{thread_role}`

```json
{
  "ok": true,
  "data": {
    "snapshot": {
      "projectId": "project_1",
      "nodeId": "node_1",
      "threadRole": "ask_planning",
      "threadId": "ask-thread-1",
      "activeTurnId": null,
      "processingState": "idle",
      "snapshotVersion": 3,
      "createdAt": "2026-03-28T10:00:00Z",
      "updatedAt": "2026-03-28T10:00:03Z",
      "lineage": {
        "forkedFromThreadId": "audit-thread-1",
        "forkedFromNodeId": "node_1",
        "forkedFromRole": "audit",
        "forkReason": "ask_bootstrap",
        "lineageRootThreadId": "audit-thread-1"
      },
      "items": [],
      "pendingRequests": []
    }
  }
}
```

## `POST /v2/.../turns`

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "threadId": "ask-thread-1",
    "turnId": "turn_123",
    "snapshotVersion": 4,
    "createdItems": [
      {
        "id": "turn:turn_123:user",
        "kind": "message",
        "threadId": "ask-thread-1",
        "turnId": "turn_123",
        "sequence": 1,
        "createdAt": "2026-03-28T10:00:01Z",
        "updatedAt": "2026-03-28T10:00:01Z",
        "status": "completed",
        "source": "local",
        "tone": "neutral",
        "metadata": {},
        "role": "user",
        "text": "Hello V2",
        "format": "markdown"
      }
    ]
  }
}
```

## First SSE frame for `GET /v2/.../events`

```json
{
  "eventId": "evt_123",
  "channel": "thread",
  "projectId": "project_1",
  "nodeId": "node_1",
  "threadRole": "ask_planning",
  "occurredAt": "2026-03-28T10:00:02Z",
  "snapshotVersion": 4,
  "type": "thread.snapshot",
  "payload": {
    "snapshot": {
      "projectId": "project_1",
      "nodeId": "node_1",
      "threadRole": "ask_planning",
      "threadId": "ask-thread-1",
      "activeTurnId": "turn_123",
      "processingState": "running",
      "snapshotVersion": 4,
      "createdAt": "2026-03-28T10:00:00Z",
      "updatedAt": "2026-03-28T10:00:02Z",
      "lineage": {
        "forkedFromThreadId": "audit-thread-1",
        "forkedFromNodeId": "node_1",
        "forkedFromRole": "audit",
        "forkReason": "ask_bootstrap",
        "lineageRootThreadId": "audit-thread-1"
      },
      "items": [],
      "pendingRequests": []
    }
  }
}
```

## Wrapped error example

```json
{
  "ok": false,
  "error": {
    "code": "conversation_stream_mismatch",
    "message": "The requested stream is no longer the active live stream for this conversation.",
    "details": {}
  }
}
```

## `thread.reset` followed by fresh `thread.snapshot`

```json
{
  "eventId": "evt_456",
  "channel": "thread",
  "projectId": "project_1",
  "nodeId": "node_1",
  "threadRole": "ask_planning",
  "occurredAt": "2026-03-28T10:00:05Z",
  "snapshotVersion": 5,
  "type": "thread.reset",
  "payload": {
    "threadId": "ask-thread-1"
  }
}
```

```json
{
  "eventId": "evt_457",
  "channel": "thread",
  "projectId": "project_1",
  "nodeId": "node_1",
  "threadRole": "ask_planning",
  "occurredAt": "2026-03-28T10:00:05Z",
  "snapshotVersion": 5,
  "type": "thread.snapshot",
  "payload": {
    "snapshot": {
      "projectId": "project_1",
      "nodeId": "node_1",
      "threadRole": "ask_planning",
      "threadId": null,
      "activeTurnId": null,
      "processingState": "idle",
      "snapshotVersion": 5,
      "createdAt": "2026-03-28T10:00:00Z",
      "updatedAt": "2026-03-28T10:00:05Z",
      "lineage": {
        "forkedFromThreadId": null,
        "forkedFromNodeId": null,
        "forkedFromRole": null,
        "forkReason": null,
        "lineageRootThreadId": null
      },
      "items": [],
      "pendingRequests": []
    }
  }
}
```

## Workflow stream envelope example

```json
{
  "eventId": "evt_789",
  "channel": "workflow",
  "projectId": "project_1",
  "nodeId": "node_1",
  "occurredAt": "2026-03-28T10:00:06Z",
  "type": "node.workflow.updated",
  "payload": {
    "projectId": "project_1",
    "nodeId": "node_1",
    "executionState": "completed",
    "reviewState": "running"
  }
}
```
