# Handoff: Continue Thread/Review Model Implementation — Phase 3

## What to do

Continue implementing the Thread and Review Model plan starting at **Phase 3: Core Services — Thread Model + Finish Task**. Phases 1 (specs) and 2 (storage layer) are complete and committed.

## Required reading (in this order)

### 1. Specs — source of truth for all contracts

Read ALL of these before writing any code. The specs define exact field names, state machines, error types, preconditions, and invariants. The plan only summarizes them.

```
docs/specs/execution-state-model.md   — READ FIRST for Phase 3. Execution lifecycle, Finish Task
                                        preconditions/effects, SHA strategy (initial_sha source
                                        selection), Status Model (node.status vs execution_state.status),
                                        shaping freeze rules, detail state extensions.

docs/specs/gating-rules-matrix.md     — READ SECOND. Every action's preconditions, derived UI state
                                        fields (can_finish_task, shaping_frozen, audit_writable, etc.),
                                        new error types (ShapingFrozen 409, ThreadReadOnly 409,
                                        FinishTaskNotAllowed 400), enforcement layers.

docs/specs/thread-state-model.md      — Thread roles (audit/ask_planning/execution/integration),
                                        read-only rules (audit writable in exactly two cases),
                                        storage layout, migration, seeding context per role,
                                        SSE broker key change.

docs/specs/type-contracts-v2.md       — All Python + TypeScript types. NodeWorkflowSummary extensions,
                                        DetailStateResponse shape, ChatSession with thread_role,
                                        new API endpoints.

docs/specs/review-node-checkpoint.md  — Review nodes, checkpoint chain, three-layer review model.
                                        (Less relevant for Phase 3, critical for Phase 4.)

docs/specs/lazy-sibling-creation.md   — Pending sibling manifest, activation triggers.
                                        (Phase 4 scope, but good to know context.)
```

### 2. Plan — implementation structure

The full implementation plan is at:
```
C:\Users\Thong\.claude\plans\cozy-questing-firefly.md
```
Phase 3 starts at the "## Phase 3" heading. The plan has 8 phases total; Phases 1-2 are done. The plan describes WHAT to build in each phase; the specs above define HOW it should behave.

## What's already built (Phase 2)

### Storage stores (all tested, all committed on branch `threadconfig`)

| Store | File | Purpose |
|-------|------|---------|
| `ChatStateStore` | `backend/storage/chat_state_store.py` | Multi-thread: `thread_role` param, directory-based `chat/{node_id}/{role}.json`, lazy flat-file migration |
| `ExecutionStateStore` | `backend/storage/execution_state_store.py` | Per-node at `.planningtree/execution/{node_id}.json`. `read_state()` returns `None` if no file. `exists()` for canonical signal. |
| `ReviewStateStore` | `backend/storage/review_state_store.py` | Per-review-node at `.planningtree/review/{review_node_id}.json`. Checkpoint append, rollup state machine (forward-only: pending→ready→accepted, accepted is final+immutable), pending sibling tracking. |

### Other Phase 2 changes

- `project_store.py`: `_ALLOWED_NODE_KINDS` includes `"review"`, `_ALLOWED_NODE_FIELDS` includes `"review_node_id"`, `_normalize_node()` sanitizes `review_node_id` (trimmed string or null)
- `storage.py`: `execution_state_store` and `review_state_store` registered
- `snapshot_view_service.py`: review nodes keep `node_kind: "review"` (not coerced to "original"), `workflow: null` for review nodes
- `frontend/src/api/types.ts`: `ThreadRole`, `ExecutionStatus`, `RollupStatus`, `ExecutionState`, `CheckpointRecord`, `RollupState`, `PendingSibling`, `ReviewState` types added. `NodeKind` includes `'review'`. `NodeRecord` has optional `review_node_id`. `DetailState` has optional execution/review fields. `ChatSession` has `thread_role`.

### Test counts

- 220 unit tests pass (1 pre-existing failure deselected: `test_split_created_child_documents_are_available`)
- TypeScript compiles clean

## Phase 3 scope (what to build next)

### 3.1 Multi-thread ChatService (`chat_service.py`)
- Add `thread_role` parameter to `get_session()`, `create_message()`, `reset_session()`
- Pass `thread_role` through to `chat_state_store` calls
- Enforce read-only rules per `thread-state-model.md`:
  - `ask_planning`: read-only when `execution_state` exists on node
  - `execution`: only Codex writes, never user
  - `audit`: writable in exactly two cases (local review after execution, package audit after rollup accepted)
- New error: `ThreadReadOnly` (already exists as `AskThreadReadOnly` in `app_errors.py` — check if reusable or needs generalization)
- SSE broker key: `(project_id, node_id, thread_role)` — check `ChatEventBroker` current implementation

### 3.2 FinishTaskService (`backend/services/finish_task_service.py` — new)
- `finish_task(project_id, node_id)`:
  - Preconditions: spec confirmed (`spec.meta.json` has `confirmed_at`), leaf node (`child_ids` empty), status `ready`/`in_progress`, no existing `execution_state`
  - Create execution thread via Codex with automated prompt (see `execution-state-model.md` Finish Task section)
  - Write `execution_state` with `status: "executing"`, `initial_sha` (see SHA source selection rules)
  - Update `node.status = "in_progress"` (NOT `"executing"` — node.status stays coarse)
  - Run Codex in background (pattern: `_run_background_split` in `split_service.py`)
- `complete_execution(project_id, node_id)`:
  - Set `status = "completed"`, record `head_sha`
  - SSE event for completion
- Shaping freeze is implicit: `execution_state` existence = frozen

### 3.3 Extend NodeDetailService (`node_detail_service.py`)
- `build_detail_state()` returns new fields: `execution_started`, `execution_completed`, `shaping_frozen`, `can_finish_task`, `execution_status`, `audit_writable`, `package_audit_ready`, `review_status`
- Derivation logic is in `gating-rules-matrix.md` "Derived UI State" table
- Shaping operations (`save_frame`, `save_spec`, `confirm_frame`, `confirm_clarify`, `confirm_spec`, `generate_*`) must check `shaping_frozen` and raise `ShapingFrozen` if true
- New error type needed: `ShapingFrozen` (409 Conflict per gating-rules-matrix.md)

### 3.4 Extend SnapshotViewService (`snapshot_view_service.py`)
- Already handles review nodes (Phase 2 fix). May need workflow summary to include execution awareness.

### Tests to write
- Unit: ChatService with thread_role routing
- Unit: thread read-only enforcement (ask_planning frozen after execution, audit gating)
- Unit: FinishTaskService precondition validation (each failing precondition)
- Unit: execution completion state transition
- Integration: POST /finish-task route (can wait for Phase 5, or do a minimal route now)

## Key design decisions to remember

1. **`node.status` stays coarse** — never set to `"executing"` or `"in_review"`. `execution_state.status` is the sole source of truth for execution/review lifecycle.
2. **SHA = workspace/subtree state** — not artifact fingerprint. Placeholder: `sha256:<hex>` of workspace directory tree. See `execution-state-model.md` "initial_sha Source Selection".
3. **Execution is automated** — Codex runs from confirmed spec, user monitors read-only. Not interactive chat.
4. **`execution_state.json` existence = shaping frozen** — no separate flag needed.
5. **Rollup accepted is final and immutable** — `set_rollup()` rejects all calls once status is `"accepted"`.

## Current branch and commit state

```
Branch: threadconfig
Latest commit: ccdf04e threadconfig-phase-2.3
All work committed. No uncommitted changes.
```

## Code files to read (after reading specs)

```
backend/services/chat_service.py          — current chat service to extend with thread_role
backend/services/node_detail_service.py   — current detail state builder to extend
backend/services/split_service.py         — background job pattern reference (_run_background_split)
backend/errors/app_errors.py             — existing error types (add ShapingFrozen, ThreadReadOnly, FinishTaskNotAllowed)
backend/services/chat_event_broker.py     — SSE broker (check current key structure for thread_role extension)
backend/storage/execution_state_store.py  — Phase 2 store you'll call from FinishTaskService
backend/storage/chat_state_store.py       — Phase 2 store with thread_role support already built
```

## Pre-existing test failures (not caused by this work)

- `test_split_created_child_documents_are_available` — fails with 409/SplitNotAllowed in both unit and integration. Pre-existing, deselect with `--deselect`.
