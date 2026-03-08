# Data Model and Contracts — PlanningTreeCodex (Legacy Audit)

Source: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Audit date: 2026-03-07

---

## Node Model (Current)

### Fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique node identifier (UUID) |
| `short_title` | string | AI-generated display title |
| `prompt` | string | User-written goal text |
| `status` | NodeStatus | Current lifecycle state |
| `parent_id` | string \| null | Parent node reference |
| `child_ids` | string[] | Ordered child references |
| `planning_mode` | string \| null | `"walking_skeleton"` \| `"slice"` \| `"finish"` \| null |
| `gate_plan` | GatePlan \| null | Planned gate checkpoints |
| `transition` | string \| null | Last FSM transition that occurred |
| `layer` | string | Grouping for UI display |
| `created_at` | string | ISO timestamp |

### NodeStatus Enum (Current)

```
locked → draft → planned → running → blocked → closed
```

| Status | Meaning |
|---|---|
| `locked` | Blocked; cannot be edited or acted on |
| `draft` | Editable; ready for planning |
| `planned` | Has gate plan; ready for execution |
| `running` | A gate is currently executing |
| `blocked` | Gate returned BLOCKED status; needs intervention |
| `closed` | Completed via finish_node |

### NodeStatus Enum (Rebuild Target)

```
locked → draft → ready → in_progress → done
```

| Status | Meaning |
|---|---|
| `locked` | Blocked by sibling ordering |
| `draft` | Created but not ready for execution |
| `ready` | Ready to execute (leaf, unlocked) |
| `in_progress` | Active chat thread open |
| `done` | Explicitly completed via Mark Done |

---

## Project Snapshot (Current — `state.json`)

```json
{
  "schema_version": 1,
  "project_id": "...",
  "nodes": {
    "<node_id>": { ...NodeModel }
  },
  "tree_state": {
    "root_node_id": "...",
    "current_gate_id": "..." | null,
    "active_node_id": "..." | null,
    "version_id": "..."
  },
  "layers": { ... },
  "updated_at": "ISO timestamp"
}
```

---

## Project Snapshot (Rebuild Target — `state.json`)

Per `docs/08_storage_model.md`:

```json
{
  "schema_version": 2,
  "project": {
    "id": "...",
    "name": "...",
    "created_at": "..."
  },
  "tree_state": {
    "root_node_id": "...",
    "active_node_id": "..." | null,
    "nodes": {
      "<node_id>": {
        "id": "...",
        "title": "...",
        "description": "...",
        "status": "locked|draft|ready|in_progress|done",
        "parent_id": "..." | null,
        "child_ids": ["..."],
        "planning_mode": "walking_skeleton|slice|null",
        "created_at": "..."
      }
    }
  },
  "updated_at": "..."
}
```

**Removed from rebuild:** `gate_plan`, `transition`, `layers`, `current_gate_id`, `version_id`

---

## Chat State (Current — `chat_state.json`)

```json
{
  "<node_id>": {
    "session_id": "...",
    "messages": [
      { "role": "user|assistant", "content": "...", "created_at": "..." }
    ],
    "config": {
      "access_mode": "read-write|read-only",
      "cwd": "/path/to/workspace",
      "writable_roots": ["/path/to/workspace"],
      "timeout_sec": 30
    },
    "runtime_thread_id": "..." | null
  }
}
```

## Chat State (Rebuild Target)

```json
{
  "<node_id>": {
    "session_id": "...",
    "messages": [
      { "role": "user|assistant", "content": "...", "created_at": "..." }
    ],
    "composer_draft": "..." | null,
    "runtime_thread_id": "..." | null,
    "updated_at": "..."
  }
}
```

---

## Persistence Files (Current)

```
<project_root>/
├── meta.json                    # { id, name, created_at, workspace_root }
├── state.json                   # project snapshot (see above)
├── audit.ndjson                 # append-only audit events (26 event types)
├── chat_state.json              # per-node chat sessions
├── gate_runs_archive.ndjson     # gate execution results
├── checkpoints/
│   ├── state/                   # pre-mutation state snapshots
│   └── runtime/                 # Codex runtime state
├── versions/                    # full snapshot per version
│   └── <version_id>/
│       └── state.json
├── artifacts/                   # gate output files
│   └── <node_id>/<gate_id>/
└── .gate.lock                   # file-based mutex
```

## Persistence Files (Rebuild Target)

```
<app-data-root>/
├── config/
│   ├── app.json               # { base_workspace_root, preferences }
│   └── auth.json              # { session, entitlement }
└── projects/
    └── <project-id>/
        ├── meta.json          # { project_id, name, workspace_root, created_at }
        ├── state.json         # project snapshot (schema_version: 2)
        └── chat_state.json    # per-node chat sessions
```

**Removed:** audit.ndjson, gate_runs_archive.ndjson, checkpoints/, versions/, artifacts/, .gate.lock

---

## API Surface (Current — 15 endpoints + 2 SSE streams)

### Projects
| Method | Path | Description |
|---|---|---|
| GET | /v1/projects | List all projects |
| POST | /v1/projects | Create project |
| GET | /v1/projects/{id}/snapshot | Get current tree snapshot |

### Nodes
| Method | Path | Description |
|---|---|---|
| POST | /v1/projects/{id}/nodes | Create node |
| PATCH | /v1/projects/{id}/nodes/{id} | Update node prompt |
| POST | /v1/projects/{id}/nodes/{id}/split | Split node (walking_skeleton/slice) |
| POST | /v1/projects/{id}/nodes/{id}/plan-gates | Plan gate checkpoints |
| POST | /v1/projects/{id}/nodes/{id}/gates/{gateId}/run | Run a gate |
| POST | /v1/projects/{id}/nodes/{id}/finish | Finish node (mark closed) |
| POST | /v1/projects/{id}/nodes/{id}/close | Close node |

### Actions
| Method | Path | Description |
|---|---|---|
| POST | /v1/projects/{id}/actions/rollback | Rollback to pre-gate state |
| POST | /v1/projects/{id}/actions/reset | Reset project to initial state |

### Versions
| Method | Path | Description |
|---|---|---|
| GET | /v1/projects/{id}/versions | List version history |
| GET | /v1/projects/{id}/versions/{id}/snapshot | Get historical snapshot |
| POST | /v1/projects/{id}/versions/{id}/restore | Restore to version |

### Chat
| Method | Path | Description |
|---|---|---|
| GET | /v1/projects/{id}/nodes/{id}/chat/session | Get chat session |
| PATCH | /v1/projects/{id}/nodes/{id}/chat/config | Update chat config |
| POST | /v1/projects/{id}/nodes/{id}/chat/messages | Send chat message |
| POST | /v1/projects/{id}/nodes/{id}/chat/reset | Reset chat session |

### SSE Streams
| Method | Path | Description |
|---|---|---|
| GET | /v1/projects/{id}/events?from_seq={seq} | Project audit event stream |
| GET | /v1/projects/{id}/nodes/{id}/chat/events | Chat streaming events |

### Metrics (removed in rebuild)
| Method | Path | Description |
|---|---|---|
| GET | /metrics | Operation counters |
| GET | /worker-health | Codex subprocess status |

---

## API Surface (Rebuild Target — from docs/07_api_and_streaming_contracts.md)

### Bootstrap + Auth
| Method | Path |
|---|---|
| GET | /v1/bootstrap/status |
| GET | /v1/auth/session |
| POST | /v1/auth/login |
| POST | /v1/auth/logout |

### Settings
| Method | Path |
|---|---|
| GET | /v1/settings/workspace |
| PATCH | /v1/settings/workspace |

### Projects
| Method | Path |
|---|---|
| GET | /v1/projects |
| POST | /v1/projects |
| GET | /v1/projects/{id}/snapshot |

### Nodes
| Method | Path |
|---|---|
| POST | /v1/projects/{id}/nodes |
| PATCH | /v1/projects/{id}/nodes/{id} |
| POST | /v1/projects/{id}/nodes/{id}/split |
| POST | /v1/projects/{id}/nodes/{id}/complete |

### Chat
| Method | Path |
|---|---|
| GET | /v1/projects/{id}/nodes/{id}/chat/session |
| PATCH | /v1/projects/{id}/nodes/{id}/chat/session |
| POST | /v1/projects/{id}/nodes/{id}/chat/messages |
| POST | /v1/projects/{id}/nodes/{id}/chat/reset |
| GET | /v1/projects/{id}/nodes/{id}/chat/events |

**Removed from rebuild:** plan-gates, run-gate, finish, close, rollback, reset, versions (all), audit events SSE, metrics, worker-health.

---

## Type Definitions (Current — `frontend/src/contracts.ts`)

Key types (abridged):

```typescript
type NodeStatus = "locked" | "draft" | "planned" | "running" | "blocked" | "closed"

interface Node {
  id: string
  short_title: string
  prompt: string
  status: NodeStatus
  parent_id: string | null
  child_ids: string[]
  planning_mode: "walking_skeleton" | "slice" | "finish" | null
  gate_plan: GatePlan | null
  transition: string | null
}

interface Snapshot {
  nodes: Record<string, Node>
  tree_state: TreeState
}

interface AuditEvent {
  seq: number
  event_type: string  // 26 event types
  payload: unknown
  created_at: string
}
```

---

## Error Model (Current)

Custom `ApiError` class in `frontend/src/client.ts`:
- `status`: HTTP status code
- `detail`: Error message string

Backend raises FastAPI `HTTPException` with detail string. Frontend maps known error codes to user-facing messages in `toUserError()`.

Known error codes (current):
- Plan gate requirement errors
- Active children blocking errors
- Gate run conflicts
- Resplit conflicts with running descendants
- Mutation in progress conflicts

**Rebuild error model** (from docs/07_api_and_streaming_contracts.md — typed product-level errors):
- `auth_required`
- `workspace_not_configured`
- `node_not_found`
- `split_not_allowed`
- `finish_not_allowed_non_leaf`
- `complete_not_allowed`
- `chat_turn_already_active`
