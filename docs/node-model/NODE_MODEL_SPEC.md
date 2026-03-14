# Node Data Model Specification

Last updated: 2026-03-12

## 1. Overview

A node is the fundamental unit of work in the planning tree. In the current implementation, node content is stored in four per-node files:

```text
nodes/{node_id}/
  task.md
  briefing.md
  spec.md
  state.yaml
```

Each file has a distinct role:

- `task.md` = statement of work
- `briefing.md` = execution context
- `spec.md` = delivery contract
- `state.yaml` = machine state

Persisted `tree.json` remains the tree index for structure, ordering, and selected synced caches. It is not the source of truth for task text.

## 2. Implementation Status

Phase F is the current implemented baseline:

- persisted `tree.json` uses `schema_version: 5`
- persisted `tree.json` does not store `title` or `description`
- public snapshots still expose `title` and `description` by loading `task.md`
- `phase` and thread/chat identifiers are mirrored into `tree.json` as synced caches
- document CRUD exists for `task.md`, `briefing.md`, `spec.md`, and read-only `state.yaml`
- confirmation endpoints advance lifecycle state through task, briefing, and spec review
- content-changing edits to confirmed documents automatically step the node back and clear downstream confirmations
- execution starts explicitly from `ready_for_execution` and completion closes the node
- explicit AI spec generation replaces `spec.md` from canonical node context
- `state.yaml` tracks `spec_generation_status` and startup recovery clears stranded `generating` states
- the frontend consumes task/briefing/spec document endpoints directly instead of relying on legacy task patching
- task, briefing, and spec panels surface lifecycle state in the UI without exposing raw `state.yaml`
- the spec panel exposes explicit AI generation controls and generation-status feedback

## 3. Project Storage Layout

```text
projects/{project_id}/
  meta.json
  tree.json
  thread_state.json
  chat_state.json
  nodes/
    {node_id}/
      task.md
      briefing.md
      spec.md
      state.yaml
```

### `tree.json`

`tree.json` is a lightweight index optimized for traversal and sibling-ordering logic.

Example:

```json
{
  "schema_version": 5,
  "project": {
    "id": "...",
    "name": "...",
    "root_goal": "...",
    "base_workspace_root": "...",
    "project_workspace_root": "...",
    "created_at": "...",
    "updated_at": "..."
  },
  "tree_state": {
    "root_node_id": "abc123",
    "active_node_id": "def456",
    "node_index": {
      "abc123": {
        "node_id": "abc123",
        "parent_id": null,
        "child_ids": ["def456"],
        "status": "draft",
        "phase": "planning",
        "depth": 0,
        "display_order": 0,
        "hierarchical_number": "1",
        "node_kind": "root",
        "planning_mode": null,
        "split_metadata": null,
        "chat_session_id": null,
        "planning_thread_id": null,
        "execution_thread_id": null,
        "planning_thread_forked_from_node": null,
        "planning_thread_bootstrapped_at": null,
        "created_at": "2026-03-12T00:00:00+00:00"
      }
    }
  },
  "updated_at": "2026-03-12T00:00:00+00:00"
}
```

Persisted node fields in `tree.json`:

- `node_id`
- `parent_id`
- `child_ids`
- `status`
- `phase`
- `depth`
- `display_order`
- `hierarchical_number`
- `node_kind`
- `planning_mode`
- `split_metadata`
- `chat_session_id`
- `planning_thread_id`
- `execution_thread_id`
- `planning_thread_forked_from_node`
- `planning_thread_bootstrapped_at`
- `created_at`

Important rules:

- `title` and `description` are never persisted in schema v5 `tree.json`
- `phase` and thread/chat identifiers are mirrored here as synced caches
- the authoritative source of node text is always the per-node document set
- public snapshots may include `title` and `description`, but those values are backfilled from `task.md`

## 4. `task.md`

### Role

The current task statement of the node. It answers what this node is about and what slice of responsibility it owns.

### Structure

```markdown
# Task

## Title
<short task title>

## Purpose
<why this node exists>

## Responsibility
<what this node owns within the larger plan>
```

### Rules

- short, clear, and stable at the conceptual level
- auto-populated when a node is created through split
- used as the source of `title` and `description` for public snapshots and prompt assembly
- serialized in canonical markdown with exactly these top-level `##` sections:
  `Title`, `Purpose`, `Responsibility`
- deeper markdown headings are allowed inside section bodies
- unknown or duplicate top-level `##` sections are invalid
- empty/default content comes from creation helpers, not read-time fallback

## 5. `briefing.md`

### Role

Execution context for the node. This is the working context document that can keep evolving as the user clarifies intent.

### Structure

```markdown
# Briefing

## User-Pinned Notes
<user steering and constraints>

## Business / Product Context
<product behavior and scope context>

## Technical / System Context
<stack, paths, schemas, and technical boundaries>

## Execution Context
<expected output, allowed edits, priorities>

## Clarified Answers
<resolved clarification content>
```

### Rules

- starts empty on node creation
- editable by the user until the node reaches `executing`
- ask-thread packet merges append best-effort entries into `Clarified Answers`
- serialized in canonical markdown with exactly these top-level `##` sections:
  `User-Pinned Notes`, `Business / Product Context`, `Technical / System Context`,
  `Execution Context`, `Clarified Answers`
- deeper markdown headings are allowed inside section bodies
- unknown or duplicate top-level `##` sections are invalid

### Clarified Answers Append Format

Each merged ask packet is appended as a markdown block:

```markdown
**<summary>**

<context_text>
```

Multiple merged packets are separated by:

```markdown
---
```

## 6. `spec.md`

### Role

The formal contract for delivery. In Phase E it is user-editable, participates in confirmation/start-execution lifecycle, and can also be replaced by an explicit AI-generated draft.

### Structure

```markdown
# Spec

## 1. Business / Product Contract
<scope, user-visible behavior, non-goals>

## 2. Technical Contract
<technical boundaries, required systems, forbidden changes>

## 3. Delivery & Acceptance
<expected output and pass conditions>

## 4. Assumptions
<assumptions currently in effect>
```

### Rules

- starts empty on node creation
- serialized in canonical markdown with exactly these top-level `##` sections:
  `1. Business / Product Contract`, `2. Technical Contract`,
  `3. Delivery & Acceptance`, `4. Assumptions`
- deeper markdown headings are allowed inside section bodies
- unknown or duplicate top-level `##` sections are invalid
- like other node documents, it is frozen when `phase=executing`

## 7. `state.yaml`

### Role

Machine-readable node state. This file is not for long-form explanation.

### Structure

```yaml
phase: planning
task_confirmed: false
briefing_confirmed: false
spec_generated: false
spec_generation_status: idle
spec_confirmed: false
planning_thread_id: ""
execution_thread_id: ""
ask_thread_id: ""
planning_thread_forked_from_node: ""
planning_thread_bootstrapped_at: ""
chat_session_id: ""
```

### Fields

| Field | Type | Meaning |
|---|---|---|
| `phase` | string | Node document/execution phase |
| `task_confirmed` | bool | Task document has been confirmed |
| `briefing_confirmed` | bool | Briefing document has been confirmed |
| `spec_generated` | bool | Spec content exists, whether authored manually or generated later |
| `spec_generation_status` | string | Spec generation status: `idle`, `generating`, or `failed` |
| `spec_confirmed` | bool | Spec document has been confirmed for execution |
| `planning_thread_id` | string | Planning thread ID |
| `execution_thread_id` | string | Execution thread ID |
| `ask_thread_id` | string | Clarification thread ID |
| `planning_thread_forked_from_node` | string | Source node of planning-thread fork |
| `planning_thread_bootstrapped_at` | string | Bootstrap timestamp |
| `chat_session_id` | string | Execution chat session ID |

### Rules

- machine-managed only
- required for every existing node directory
- malformed YAML or non-mapping YAML is invalid
- HTTP exposes this file as read-only

## 8. Lifecycle Fields

The system uses two orthogonal lifecycle fields.

### `status` in `tree.json`

Controls sibling execution ordering:

```text
draft -> ready -> in_progress -> done
         ^
       locked
```

Values:

- `draft`: parent has children and this node is not yet actionable
- `ready`: actionable now
- `locked`: blocked by sibling ordering
- `in_progress`: execution has started
- `done`: execution is complete

### `phase` in `state.yaml` and `tree.json`

Controls document/execution maturity.

Phase E actively uses:

```text
planning -> briefing_review -> spec_review -> ready_for_execution -> executing -> closed
```

Current Phase E behavior:

- new and reset nodes start at `planning`
- `confirm-task` requires non-empty `task.title` and `task.purpose`, then sets `task_confirmed=true` and advances to `briefing_review`
- `confirm-briefing` requires `task_confirmed=true`, then sets `briefing_confirmed=true` and advances to `spec_review`
- the first successful content-changing save to `spec.md` sets `spec_generated=true`
- `generate-spec` is allowed from `spec_review` or `ready_for_execution`
- `generate-spec` sets `spec_generation_status=generating`, replaces the full `spec.md` draft on success, then returns `spec_generation_status=idle`
- `generate-spec` failures leave the existing `spec.md` unchanged and set `spec_generation_status=failed`
- `confirm-spec` requires `briefing_confirmed=true` and `spec_generated=true`, then sets `spec_confirmed=true` and advances to `ready_for_execution`
- `start-execution` advances `ready_for_execution -> executing`
- content-changing edits to already-confirmed documents step the node back and clear downstream confirmations:
  - task edit -> `planning`, clears `task_confirmed`, `briefing_confirmed`, and `spec_confirmed`
  - briefing edit -> `briefing_review`, clears `briefing_confirmed` and `spec_confirmed`
  - spec edit -> `spec_review`, clears `spec_confirmed`
- regenerating a confirmed spec from `ready_for_execution` also steps the node back to `spec_review` through the same spec-edit lifecycle path
- unchanged saves do not clear confirmations
- all document edits are rejected while `phase=executing`
- completed nodes are marked `closed`

## 9. `node_kind`

`node_kind` replaces the old boolean `is_superseded`.

| Value | Meaning |
|---|---|
| `root` | project root node |
| `original` | normal non-root node |
| `superseded` | replaced by a later re-split |

## 10. File Boundaries

| Content | Lives in |
|---|---|
| `title`, `purpose`, `responsibility` | `task.md` |
| user notes, business context, technical context, execution context, clarified answers | `briefing.md` |
| business contract, technical contract, delivery acceptance, assumptions | `spec.md` |
| phase, confirmation flags, thread/chat IDs | `state.yaml` |
| structure, ordering, node kind, synced phase/thread caches | `tree.json` |

Public snapshot compatibility:

- clients still receive `title` and `description`
- those fields are loaded from `task.md`
- persisted schema v5 does not store them in `tree.json`

## 11. Design Rules

1. `task.md` is the current task statement.
2. `briefing.md` is execution context and owns clarified answers.
3. `spec.md` is the contract document.
4. `state.yaml` stays machine-readable and minimal.
5. Each file has one role; do not use one as a substitute for another.
6. Split populates `task.md` only. `briefing.md` and `spec.md` start empty.
7. Once a node directory exists, all four files are required.
8. Read helpers fail on malformed structure instead of silently repairing it.
9. Persisted `tree.json` keeps synced caches but not task text.
10. Snapshot compatibility is handled at read time, not by reintroducing `title` / `description` into persisted `tree.json`.

## 12. Migration Notes

### `v3 -> v5`

On first load of an old `state.json` project:

1. Read `state.json`
2. Convert `node_registry` into `tree_state.node_index`
3. Create `nodes/{node_id}/task.md` from legacy `title` / `description`
4. Create empty `briefing.md` and `spec.md`
5. Create `state.yaml` with derived phase and thread/chat identifiers
6. Write schema v5 `tree.json`
7. Rename `state.json` to `state.json.bak`

### `v4 -> v5`

On first load of a schema v4 `tree.json` project:

1. Validate that all node directories exist
2. Strip persisted `title` / `description`
3. Rewrite the project as schema v5

## 13. Runtime Compatibility

Phase F keeps compatibility at the API boundary:

- public snapshots still include `node_registry`
- each public node still includes `title` and `description`
- legacy `PATCH /nodes/{node_id}` updates `task.md` rather than `tree.json`
- legacy `PATCH /nodes/{node_id}` participates in the same task-edit step-back behavior as `PUT /documents/task`
- the shipping frontend no longer depends on legacy `PATCH /nodes/{node_id}` for active task editing
- split, ask, chat, and thread services load task fields from `task.md` when inline values are absent
