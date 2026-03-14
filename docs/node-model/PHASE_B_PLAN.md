# Phase B: Tree Index Migration (state.json → tree.json)

## Goal

Replace monolithic `state.json` with `tree.json` (tree index) + per-node file directories. All existing API behavior and tests preserved. This phase is a compatibility bridge: the authoritative node documents live in per-node files, while `tree.json` is allowed to retain temporary cache fields needed to keep the current backend behavior working during migration.

## Prerequisites

- Phase A complete: `node_files.py`, `node_store.py`, `file_utils.atomic_write_text()` exist and are tested
- Spec reference: [NODE_MODEL_SPEC.md](NODE_MODEL_SPEC.md)

---

## Key Design Decisions for Phase B

### 1. tree.json uses `node_index` (dict), not `node_registry` (array)

**On-disk format**: `tree_state.node_index` is a dict keyed by `node_id`.

**In-memory**: Same dict format. `tree_service.node_index()` returns this dict directly (no array→dict conversion needed).

**Public API**: `SnapshotViewService.to_public_snapshot()` converts dict → array under `node_registry` key for the frontend. Frontend code continues to receive `node_registry: NodeRecord[]`.

### 2. tree.json keeps temporary compatibility caches

Although the target spec moves document/state content into per-node files, Phase B keeps a temporary cache in `tree.json` for fields that existing services still read directly.

**Authoritative sources**:
- `task.md`: `title`, `description` (mapped to `purpose`)
- `state.yaml`: `phase`, `chat_session_id`, `planning_thread_id`, `execution_thread_id`, `planning_thread_forked_from_node`, `planning_thread_bootstrapped_at`

**Temporary Phase B cache fields in tree.json**:
```
node_id, parent_id, child_ids,
title (cache), description (cache),
status, phase (cache),
depth, display_order, hierarchical_number,
node_kind, planning_mode, split_metadata, created_at,
chat_session_id (cache),
planning_thread_id (cache), execution_thread_id (cache),
planning_thread_forked_from_node (cache),
planning_thread_bootstrapped_at (cache)
```

**Cache rules**:
- These cache fields are transitional and do not replace the authoritative per-node files
- Cache fields retain the legacy nullable shape where useful for compatibility (`None` when unset in tree.json, empty string when unset in `state.yaml`)
- Any service that writes an authoritative field in Phase B must keep the corresponding tree cache in sync

### 3. `is_superseded` → `node_kind`

Replace `is_superseded: bool` with `node_kind: "root" | "original" | "superseded"`.

All tree service methods that check `is_superseded` must switch to `node_kind == "superseded"`.

### 4. Backward compatibility approach

The internal snapshot format changes (array → dict, new fields), but:
- The public API (via SnapshotViewService) still returns `node_registry` array
- Existing tests that use the public snapshot continue to work
- Tests that directly access `storage.project_store.load_snapshot()` need updates for the new dict format

### 5. V4 corruption policy

If `tree.json` exists but required node file directories are missing for any node, the project is considered corrupted.

- Phase B should fail fast on missing node file sets
- Phase B should not auto-heal missing node files from cached tree data
- Malformed node documents continue to fail when the relevant file reader is invoked

---

## Step 1: Update ProjectStore — tree.json path and migration

**File**: `backend/storage/project_store.py`

### 1.1: Add `tree_path()` method

```python
def tree_path(self, project_id: str) -> Path:
    return self.project_dir(project_id) / "tree.json"
```

Keep `state_path()` unchanged — it's used for migration detection (if `state.json` exists but `tree.json` does not, migration is needed).

### 1.2: Add migration method `_migrate_v3_to_v4()`

```python
def _migrate_v3_to_v4(self, project_id: str) -> dict[str, Any]:
    """Migrate a v3 state.json project to v4 tree.json + per-node files.

    Called by load_tree() when state.json exists but tree.json does not.
    Runs inside project lock (caller ensures this).
    """
```

**Migration logic**:

1. Read `state.json` → `old_snapshot`
2. Build `node_index` dict from `node_registry` array:
   ```python
    node_registry = old_snapshot["tree_state"].pop("node_registry", [])
    node_index = {}
    root_node_id = old_snapshot["tree_state"]["root_node_id"]

    for node in node_registry:
        node_id = node["node_id"]

        # Read legacy fields
        title = str(node.get("title") or "")
        description = str(node.get("description") or "")
        planning_thread_id = str(node.get("planning_thread_id") or "")
        execution_thread_id = str(node.get("execution_thread_id") or "")
        forked_from_node = str(node.get("planning_thread_forked_from_node") or "")
        bootstrapped_at = str(node.get("planning_thread_bootstrapped_at") or "")
        chat_session_id = str(node.get("chat_session_id") or "")
        is_superseded = node.pop("is_superseded", False)

        # Compute new fields
        if node_id == root_node_id:
            node_kind = "root"
       elif is_superseded:
           node_kind = "superseded"
       else:
           node_kind = "original"

       status = node.get("status", "draft")
       if status == "done":
           phase = "closed"
       elif status == "in_progress":
           phase = "executing"
        else:
            phase = "planning"

        # Normalize tree entry for v4. Keep compatibility caches in tree.json.
        node["node_kind"] = node_kind
        node["title"] = title
        node["description"] = description
        node["phase"] = phase
        node["chat_session_id"] = chat_session_id or None
        node["planning_thread_id"] = planning_thread_id or None
        node["execution_thread_id"] = execution_thread_id or None
        node["planning_thread_forked_from_node"] = forked_from_node or None
        node["planning_thread_bootstrapped_at"] = bootstrapped_at or None

        node_index[node_id] = node

        # Write per-node files
        task = {"title": title, "purpose": description, "responsibility": ""}
       state = {
           "phase": phase,
           "task_confirmed": phase != "planning",
           "briefing_confirmed": phase in ("spec_review", "ready_for_execution", "executing", "closed"),
           "spec_generated": False,
           "spec_confirmed": phase in ("ready_for_execution", "executing", "closed"),
           "planning_thread_id": planning_thread_id,
           "execution_thread_id": execution_thread_id,
           "ask_thread_id": "",
           "planning_thread_forked_from_node": forked_from_node,
           "planning_thread_bootstrapped_at": bootstrapped_at,
           "chat_session_id": chat_session_id,
       }
       self._node_store.create_node_files(
           project_id, node_id,
           task=task,
           briefing=None,  # empty
           spec=None,       # empty
           state=state,
       )
   ```

3. Build new snapshot:
   ```python
   new_snapshot = {
       "schema_version": 4,
       "project": old_snapshot.get("project", {}),
       "tree_state": {
           "root_node_id": root_node_id,
           "active_node_id": old_snapshot["tree_state"].get("active_node_id"),
           "node_index": node_index,
       },
       "updated_at": old_snapshot.get("updated_at", iso_now()),
   }
   ```

4. Write `tree.json`, rename `state.json`:
   ```python
   atomic_write_json(self.tree_path(project_id), new_snapshot)
   state_json = self.state_path(project_id)
   backup = state_json.with_suffix(".json.bak")
   state_json.rename(backup)
   ```

5. Return `new_snapshot`

3.5. Validate the migrated v4 project before returning it:
   ```python
   self._validate_tree_node_files(project_id, new_snapshot)
   ```

### 1.2b: Add `_validate_tree_node_files()`

```python
def _validate_tree_node_files(self, project_id: str, tree: dict[str, Any]) -> None:
    """Fail fast if a v4 tree.json references node directories that do not fully exist."""
```

**Validation logic**:
- Iterate `tree["tree_state"]["node_index"]`
- For each node_id, require `self._node_store.node_exists(project_id, node_id)`
- If any node directory is missing or incomplete, raise `ValueError`
- This validation runs:
  - after migration
  - on normal `load_tree()` when `tree.json` already exists

### 1.3: Update `load_snapshot()` → `load_tree()`

```python
def load_tree(self, project_id: str) -> dict[str, Any]:
    """Load the tree index (tree.json). Auto-migrates v3 state.json if needed."""
    with self.project_lock(project_id):
        tree = load_json(self.tree_path(project_id))
        if tree is not None:
            self._validate_tree_node_files(project_id, tree)
            return tree
        # Migration: state.json exists but tree.json does not
        if self.state_path(project_id).exists():
            return self._migrate_v3_to_v4(project_id)
        raise ProjectNotFound(project_id)
```

Keep `load_snapshot()` as an alias calling `load_tree()` for backward compatibility during the transition:
```python
def load_snapshot(self, project_id: str) -> dict[str, Any]:
    return self.load_tree(project_id)
```

### 1.4: Update `save_snapshot()` → `save_tree()`

```python
def save_tree(self, project_id: str, tree: dict[str, Any]) -> None:
    with self.project_lock(project_id):
        if not self.project_dir(project_id).exists():
            raise ProjectNotFound(project_id)
        atomic_write_json(self.tree_path(project_id), tree)

def save_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> None:
    self.save_tree(project_id, snapshot)
```

### 1.5: Update `create_project_files()`

```python
def create_project_files(self, meta: dict[str, Any], snapshot: dict[str, Any]) -> None:
    project_id = str(meta["id"])
    with self.project_lock(project_id):
        project_dir = ensure_dir(self.project_dir(project_id))
        atomic_write_json(project_dir / "meta.json", meta)
        atomic_write_json(project_dir / "tree.json", snapshot)
        atomic_write_json(project_dir / "chat_state.json", {})
        atomic_write_json(project_dir / "thread_state.json", {})
```

### 1.6: Add NodeStore reference

ProjectStore needs access to NodeStore for migration:
```python
def __init__(self, paths: AppPaths, lock_registry: ProjectLockRegistry, node_store: NodeStore) -> None:
    self._paths = paths
    self._lock_registry = lock_registry
    self._node_store = node_store
```

Update Storage class to pass node_store to project_store.

**Affected file**: `backend/storage/storage.py`

```python
class Storage:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._project_locks = ProjectLockRegistry()
        self.node_store = NodeStore(paths)
        self.config_store = ConfigStore(paths)
        self.project_store = ProjectStore(paths, self._project_locks, self.node_store)
        self.chat_store = ChatStore(paths, self._project_locks)
        self.thread_store = ThreadStore(paths, self._project_locks)
```

---

## Step 2: Update ProjectService

**File**: `backend/services/project_service.py`

### 2.1: Update `create_project()` — write tree.json + root node files

Changes to the root_node dict (line 121-140):

```python
root_node_id = uuid4().hex
now = iso_now()

# Tree entry (for tree.json)
root_tree_entry = {
    "node_id": root_node_id,
    "parent_id": None,
    "child_ids": [],
    "title": cleaned_name,     # cache
    "description": cleaned_goal,  # cache
    "status": "draft",
    "phase": "planning",       # cache
    "planning_mode": None,
    "depth": 0,
    "display_order": 0,
    "hierarchical_number": "1",
    "node_kind": "root",
    "split_metadata": None,
    "chat_session_id": None,
    "planning_thread_id": None,
    "execution_thread_id": None,
    "planning_thread_forked_from_node": None,
    "planning_thread_bootstrapped_at": None,
    "created_at": now,
}
```

Build snapshot with `node_index` dict:
```python
snapshot = {
    "schema_version": 4,
    "project": dict(project_record),
    "tree_state": {
        "root_node_id": root_node_id,
        "active_node_id": root_node_id,
        "node_index": {root_node_id: root_tree_entry},
    },
    "updated_at": now,
}
```

After `create_project_files()`, also create root node files:
```python
self.storage.node_store.create_node_files(
    project_id, root_node_id,
    task={"title": cleaned_name, "purpose": cleaned_goal, "responsibility": ""},
)
```

### 2.2: Update `reset_to_root()` — rebuild tree + node files

Changes (lines 60-89):

```python
def reset_to_root(self, project_id: str) -> dict[str, Any]:
    with self.storage.project_lock(project_id):
        snapshot = self.storage.project_store.load_snapshot(project_id)
        tree_state = snapshot.get("tree_state", {})
        root_id = str(tree_state.get("root_node_id") or "").strip()
        node_index = tree_state.get("node_index", {})
        root_node = node_index.get(root_id)

        if root_node is None:
            raise InvalidRequest("Project snapshot is missing its root node.")
        if self._project_has_active_turns(project_id):
            raise ProjectResetNotAllowed(...)

        reset_root = self._build_reset_root_node(root_node)
        snapshot["tree_state"] = {
            "root_node_id": root_id,
            "active_node_id": root_id,
            "node_index": {root_id: reset_root},
        }
        snapshot = self._persist_snapshot(project_id, snapshot)

        # Clean up non-root node directories
        nodes_dir = self.storage.node_store.node_dir(project_id, root_id).parent
        if nodes_dir.exists():
            for child_dir in nodes_dir.iterdir():
                if child_dir.is_dir() and child_dir.name != root_id:
                    import shutil
                    shutil.rmtree(child_dir)

        # Reset root node files in place. Do not call create_node_files() because
        # Phase A guarantees it raises if the node directory already exists.
        root_task = self.storage.node_store.load_task(project_id, root_id)
        self.storage.node_store.save_task(project_id, root_id, root_task)
        self.storage.node_store.save_briefing(project_id, root_id, empty_briefing())
        self.storage.node_store.save_spec(project_id, root_id, empty_spec())
        self.storage.node_store.save_state(project_id, root_id, default_state())

        self.storage.thread_store.write_thread_state(project_id, {})
        self.storage.chat_store.write_chat_state(project_id, {})
    ...
```

### 2.3: Update `_build_reset_root_node()`

```python
def _build_reset_root_node(self, root_node: dict[str, Any]) -> dict[str, Any]:
    reset_root = dict(root_node)
    reset_root.update({
        "parent_id": None,
        "child_ids": [],
        "status": "draft",
        "phase": "planning",
        "planning_mode": None,
        "depth": 0,
        "display_order": 0,
        "hierarchical_number": "1",
        "node_kind": "root",
        "split_metadata": None,
        "description": root_node.get("description", ""),
        "chat_session_id": None,
        "planning_thread_id": None,
        "execution_thread_id": None,
        "planning_thread_forked_from_node": None,
        "planning_thread_bootstrapped_at": None,
    })
    # Remove the obsolete pre-v4 superseded flag.
    for old_key in ("is_superseded",):
        reset_root.pop(old_key, None)
    return reset_root
```

---

## Step 3: Update TreeService

**File**: `backend/services/tree_service.py`

### 3.1: `node_index()` — read from dict directly

```python
def node_index(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # v4: node_index is already a dict
    node_index = snapshot.get("tree_state", {}).get("node_index")
    if isinstance(node_index, dict):
        return node_index
    # v3 fallback (during migration, if snapshot is still array-based)
    registry = snapshot.get("tree_state", {}).get("node_registry", [])
    return {
        str(node["node_id"]): node
        for node in registry
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
```

### 3.2: Replace `is_superseded` checks with `node_kind`

Every method that checks `node.get("is_superseded")` must change to `node.get("node_kind") == "superseded"`.

**Methods to update**:

| Method | Line | Change |
|--------|------|--------|
| `active_child_ids()` | 22 | `child.get("is_superseded")` → `child.get("node_kind") == "superseded"` |
| `first_actionable_leaf()` | 119 | `root.get("is_superseded")` → `root.get("node_kind") == "superseded"` |
| `_first_actionable_leaf_from()` | 136 | `child.get("is_superseded")` → `child.get("node_kind") == "superseded"` |

**Helper** (optional, for readability):
```python
def _is_superseded(self, node: dict[str, Any]) -> bool:
    return node.get("node_kind") == "superseded"
```

---

## Step 4: Update NodeService

**File**: `backend/services/node_service.py`

### 4.1: `create_child()` — write to node_index dict + create node files

Change line 93 from:
```python
snapshot["tree_state"]["node_registry"].append(child_node)
```
To:
```python
snapshot["tree_state"]["node_index"][new_node_id] = child_node
```

Update `child_node` dict (lines 73-92) to use new fields:
```python
child_node = {
    "node_id": new_node_id,
    "parent_id": parent_id,
    "child_ids": [],
    "title": "New Node",              # cache
    "description": "",                # cache
    "status": child_status,
    "phase": "planning",              # new
    "planning_mode": None,
    "depth": int(parent.get("depth", 0)) + 1,
    "display_order": display_order,
    "hierarchical_number": f"{parent_hnum}.{display_order + 1}",
    "node_kind": "original",          # replaces is_superseded
    "split_metadata": None,
    "chat_session_id": None,
    "planning_thread_id": None,
    "execution_thread_id": None,
    "planning_thread_forked_from_node": None,
    "planning_thread_bootstrapped_at": None,
    "created_at": now,
}
```

After persisting snapshot, create node files:
```python
self.storage.node_store.create_node_files(
    project_id, new_node_id,
    task={"title": "New Node", "purpose": "", "responsibility": ""},
)
```

### 4.2: `update_node()` — sync title cache to tree.json

When title is updated (line 123), also update node files:
```python
if title is not None:
    cleaned = title.strip()
    if not cleaned:
        raise InvalidRequest("Title cannot be empty.")
    node["title"] = cleaned  # tree.json cache
    # Sync to task.md
    task = self.storage.node_store.load_task(project_id, node_id)
    task["title"] = cleaned
    self.storage.node_store.save_task(project_id, node_id, task)
if description is not None:
    cleaned_description = description.strip()
    node["description"] = cleaned_description  # tree.json cache
    task = self.storage.node_store.load_task(project_id, node_id)
    task["purpose"] = cleaned_description
    self.storage.node_store.save_task(project_id, node_id, task)
```

### 4.3: `complete_node()` — update phase in tree.json cache + state.yaml

After setting `node["status"] = "done"`:
```python
node["phase"] = "closed"  # tree.json cache
state = self.storage.node_store.load_state(project_id, node_id)
state["phase"] = "closed"
self.storage.node_store.save_state(project_id, node_id, state)
```

### 4.4: Replace `is_superseded` checks

Line 52: `parent.get("is_superseded")` → `parent.get("node_kind") == "superseded"`
Line 114: `node.get("is_superseded")` → `node.get("node_kind") == "superseded"`
Line 138: `node.get("is_superseded")` → `node.get("node_kind") == "superseded"`

---

## Step 5: Update SplitService

**File**: `backend/services/split_service.py`

### 5.1: `_make_node()` — use new fields

```python
def _make_node(self, *, node_id, parent_id, title, description, status, depth,
               display_order, hierarchical_number, planning_thread_forked_from_node, now):
    return {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,                    # cache in tree.json
        "description": description,        # cache in tree.json
        "status": status,
        "phase": "planning",               # cache in tree.json
        "planning_mode": None,
        "depth": depth,
        "display_order": display_order,
        "hierarchical_number": hierarchical_number,
        "node_kind": "original",           # replaces is_superseded
        "split_metadata": None,
        "chat_session_id": None,
        "planning_thread_id": None,
        "execution_thread_id": None,
        "planning_thread_forked_from_node": planning_thread_forked_from_node or None,
        "planning_thread_bootstrapped_at": None,
        "created_at": now,
    }
```

### 5.2: After appending to tree, create node files

Everywhere that does `snapshot["tree_state"]["node_registry"].append(child_node)`, change to:
```python
snapshot["tree_state"]["node_index"][child_id] = child_node
```

After each child node is added to tree.json, create its per-node files:
```python
self.storage.node_store.create_node_files(
    project_id, child_id,
    task={"title": title, "purpose": description, "responsibility": ""},
    state={
        **default_state(),
        "planning_thread_forked_from_node": planning_thread_forked_from_node or "",
    },
)
```

**Note**: `description` from the split payload maps to `task.purpose` in the node files.
The child tree entry should keep the same `description` text in its Phase B compatibility cache so current backend consumers stay consistent.

### 5.3: Supersede old children — set `node_kind`

Where the code currently sets `child.get("is_superseded", True)` for replaced children, change to:
```python
old_child["node_kind"] = "superseded"
```

Also update old child's state.yaml:
```python
# No need to update state.yaml for superseded nodes — they're frozen
```

### 5.4: Update all `is_superseded` references

Search the file for `is_superseded` and replace with `node_kind == "superseded"` checks.

---

## Step 6: Update SnapshotViewService

**File**: `backend/services/snapshot_view_service.py`

### 6.1: Convert `node_index` dict → `node_registry` array for public API

The public API must continue to return `node_registry: NodeRecord[]`. The SnapshotViewService converts:

```python
def to_public_snapshot(self, snapshot: dict[str, Any], thread_state: dict[str, Any] | None = None) -> dict[str, Any]:
    public_snapshot = copy.deepcopy(snapshot)
    tree_state = public_snapshot.get("tree_state", {})

    # Convert node_index dict → node_registry array
    node_index = tree_state.pop("node_index", {})
    if not isinstance(node_index, dict):
        # Fallback: might already be array (v3 compat)
        registry = tree_state.get("node_registry", [])
    else:
        # Preserve insertion order from node_index to minimize public payload churn.
        registry = list(node_index.values())
    tree_state["node_registry"] = registry

    thread_state = thread_state or {}
    for raw_node in registry:
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("node_id", ""))
        node_thread_state = thread_state.get(node_id, {}) if isinstance(thread_state, dict) else {}
        planning_state = node_thread_state.get("planning", {}) if isinstance(node_thread_state, dict) else {}
        execution_state = node_thread_state.get("execution", {}) if isinstance(node_thread_state, dict) else {}
        ask_state = node_thread_state.get("ask", {}) if isinstance(node_thread_state, dict) else {}

        # Remove internal-only fields (no longer present, but clean up if they exist)
        raw_node.pop("planning_thread_id", None)
        raw_node.pop("execution_thread_id", None)
        raw_node.pop("planning_thread_forked_from_node", None)
        raw_node.pop("planning_thread_bootstrapped_at", None)

        # Thread presence booleans (unchanged logic)
        resolved_planning_thread_id = planning_state.get("thread_id") if isinstance(planning_state, dict) else None
        resolved_execution_thread_id = execution_state.get("thread_id") if isinstance(execution_state, dict) else None

        raw_node["has_planning_thread"] = isinstance(resolved_planning_thread_id, str) and bool(resolved_planning_thread_id.strip())
        raw_node["has_execution_thread"] = isinstance(resolved_execution_thread_id, str) and bool(resolved_execution_thread_id.strip())
        raw_node["planning_thread_status"] = planning_state.get("status") if isinstance(planning_state, dict) else None
        raw_node["execution_thread_status"] = execution_state.get("status") if isinstance(execution_state, dict) else None
        resolved_ask_thread_id = ask_state.get("thread_id") if isinstance(ask_state, dict) else None
        raw_node["has_ask_thread"] = isinstance(resolved_ask_thread_id, str) and bool(resolved_ask_thread_id.strip())
        raw_node["ask_thread_status"] = ask_state.get("status") if isinstance(ask_state, dict) else None

        # Add backward-compat fields derived from new fields
        raw_node["is_superseded"] = raw_node.get("node_kind") == "superseded"

    return public_snapshot
```

**Key points**:
- `node_index` dict → `node_registry` array conversion
- `is_superseded` boolean computed from `node_kind` for frontend backward compat
- `description` continues to come from the temporary tree cache in Phase B
- `phase` and `node_kind` are exposed in the public snapshot
- Thread presence booleans computed same as before

---

## Step 7: Update Frontend Types

**File**: `frontend/src/api/types.ts`

### 7.1: Add new fields to NodeRecord

```typescript
export interface NodeRecord {
  node_id: string
  parent_id: string | null
  child_ids: string[]
  title: string
  description: string
  status: NodeStatus
  phase: NodePhase                    // NEW
  node_kind: NodeKind                 // NEW
  planning_mode: 'walking_skeleton' | 'slice' | null
  depth: number
  display_order: number
  hierarchical_number: string
  split_metadata: Record<string, unknown> | null
  chat_session_id: string | null
  has_planning_thread: boolean
  has_execution_thread: boolean
  planning_thread_status: 'idle' | 'active' | null
  execution_thread_status: 'idle' | 'active' | null
  has_ask_thread: boolean
  ask_thread_status: 'idle' | 'active' | null
  is_superseded: boolean              // kept for backward compat
  created_at: string
}
```

### 7.2: Add new type aliases

```typescript
export type NodePhase = 'planning' | 'briefing_review' | 'spec_review' | 'ready_for_execution' | 'executing' | 'closed'

export type NodeKind = 'root' | 'original' | 'superseded'
```

### 7.3: Add document interfaces (for future use in Phase C)

```typescript
export interface NodeTask {
  title: string
  purpose: string
  responsibility: string
}

export interface NodeBriefing {
  user_notes: string
  business_context: string
  technical_context: string
  execution_context: string
  clarified_answers: string
}

export interface NodeSpec {
  business_contract: string
  technical_contract: string
  delivery_acceptance: string
  assumptions: string
}

export interface NodeDocuments {
  task: NodeTask
  briefing: NodeBriefing
  spec: NodeSpec
  state: Record<string, unknown>
}
```

---

## Step 8: Update additional backend consumers

### 8.1: `backend/services/ask_service.py`

`ask_service.py` still reads internal snapshot nodes and checks the legacy superseded flag.

**Required updates**:
- Replace every internal `node.get("is_superseded")` check with `node.get("node_kind") == "superseded"`
- No thread-id refactor is required in Phase B because the relevant thread fields remain cached in `tree.json`
- No description refactor is required in Phase B because `description` remains cached in `tree.json`

### 8.2: `backend/ai/split_context_builder.py`

**Required updates**:
- Line 65: `sibling.get("is_superseded")` → `sibling.get("node_kind") == "superseded"`
- Line 105: `child.get("is_superseded")` → `child.get("node_kind") == "superseded"`

**Description access**:
- `_format_node_prompt()` and sibling summaries continue to read `node["description"]` from the Phase B compatibility cache
- No `NodeStore` dependency should be introduced into `split_context_builder.py` in Phase B

### 8.3: Services that do not need direct refactors in Phase B

Because Phase B keeps compatibility caches in `tree.json`, these services can continue to read cached values after `TreeService.node_index()` switches to dict-backed snapshots:
- `backend/services/thread_service.py`
- `backend/services/chat_service.py`

If a service in this group still has a direct `is_superseded` check, update that check to `node_kind` during implementation.

---

## Step 9: Update existing tests

### Tests that directly access internal snapshot format

These tests call `storage.project_store.load_snapshot()` and access `node_registry` array. They need updating to use `node_index` dict.

**File**: `backend/tests/unit/test_node_service.py`

Pattern change:
```python
# Before (v3):
persisted = storage.project_store.load_snapshot(project_id)
persisted["tree_state"]["node_registry"][0]["status"] = "ready"

# After (v4):
persisted = storage.project_store.load_snapshot(project_id)
root_id = persisted["tree_state"]["root_node_id"]
persisted["tree_state"]["node_index"][root_id]["status"] = "ready"
```

Pattern change for finding nodes:
```python
# Before:
root = next(n for n in snapshot["tree_state"]["node_registry"] if n["node_id"] == root_id)
children = [n for n in snapshot["tree_state"]["node_registry"] if n["parent_id"] == root_id]

# After (public snapshot still uses node_registry array, so this pattern stays
# for tests that use the public API return value)
```

**Key distinction**:
- Tests using `node_service.create_child()` return value → this is the **public snapshot** (has `node_registry` array) → NO CHANGE needed
- Tests using `storage.project_store.load_snapshot()` directly → this is the **internal format** (has `node_index` dict) → NEED CHANGE

### Tests that check `is_superseded`

Search for `is_superseded` in all test files and update to check `node_kind == "superseded"` where the internal snapshot is accessed. For public snapshot access, `is_superseded` bool is still present (computed by SnapshotViewService).

### Tests that check `state_path().exists()`

```python
# Before:
assert storage.project_store.state_path(project_id).exists()

# After:
assert storage.project_store.tree_path(project_id).exists()
```

**Files to search and update**:
- `backend/tests/unit/test_node_service.py`
- `backend/tests/unit/test_project_service.py`
- `backend/tests/unit/test_split_service.py`
- `backend/tests/unit/test_split_service_lineage.py`
- `backend/tests/unit/test_split_service_preflight.py`
- `backend/tests/integration/test_phase3_flow.py`
- `backend/tests/integration/test_reset_project_api.py`
- Any other test that accesses `node_registry` from internal snapshot

---

## Step 10: New migration test

**File**: `backend/tests/unit/test_schema_migration.py` (NEW)

```python
def test_v3_to_v4_migration_creates_tree_json_and_node_files(
    storage: Storage, workspace_root: Path
):
    """Migrating a v3 state.json creates tree.json + per-node file directories."""
    # Setup: create a v3 project manually
    project_id = "a" * 32
    project_dir = storage.project_store.project_dir(project_id)
    project_dir.mkdir(parents=True)

    v3_snapshot = {
        "schema_version": 3,
        "project": {"id": project_id, "name": "Test", ...},
        "tree_state": {
            "root_node_id": "root_001",
            "active_node_id": "child_001",
            "node_registry": [
                {
                    "node_id": "root_001",
                    "parent_id": None,
                    "child_ids": ["child_001"],
                    "title": "Root Task",
                    "description": "Build something",
                    "status": "draft",
                    "planning_mode": "walking_skeleton",
                    "depth": 0,
                    "display_order": 0,
                    "hierarchical_number": "1",
                    "split_metadata": None,
                    "chat_session_id": None,
                    "planning_thread_id": "thread_abc",
                    "execution_thread_id": None,
                    "planning_thread_forked_from_node": None,
                    "planning_thread_bootstrapped_at": None,
                    "is_superseded": False,
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "node_id": "child_001",
                    "parent_id": "root_001",
                    "child_ids": [],
                    "title": "Child Task",
                    "description": "Do subthing",
                    "status": "ready",
                    "planning_mode": None,
                    "depth": 1,
                    "display_order": 0,
                    "hierarchical_number": "1.1",
                    "split_metadata": None,
                    "chat_session_id": "chat_xyz",
                    "planning_thread_id": "thread_def",
                    "execution_thread_id": "thread_ghi",
                    "planning_thread_forked_from_node": "root_001",
                    "planning_thread_bootstrapped_at": "2026-01-02T00:00:00Z",
                    "is_superseded": False,
                    "created_at": "2026-01-02T00:00:00Z",
                },
            ],
        },
        "updated_at": "2026-01-02T00:00:00Z",
    }
    atomic_write_json(project_dir / "state.json", v3_snapshot)
    atomic_write_json(project_dir / "meta.json", {"id": project_id})
    atomic_write_json(project_dir / "thread_state.json", {})
    atomic_write_json(project_dir / "chat_state.json", {})

    # Act: load triggers migration
    tree = storage.project_store.load_snapshot(project_id)

    # Assert: tree.json format
    assert tree["schema_version"] == 4
    assert "node_index" in tree["tree_state"]
    assert "node_registry" not in tree["tree_state"]
    assert "root_001" in tree["tree_state"]["node_index"]
    assert "child_001" in tree["tree_state"]["node_index"]

    # Assert: node_kind
    assert tree["tree_state"]["node_index"]["root_001"]["node_kind"] == "root"
    assert tree["tree_state"]["node_index"]["child_001"]["node_kind"] == "original"

    # Assert: tree.json file exists, state.json renamed
    assert storage.project_store.tree_path(project_id).exists()
    assert (project_dir / "state.json.bak").exists()
    assert not (project_dir / "state.json").exists()

    # Assert: per-node files exist
    assert storage.node_store.node_exists(project_id, "root_001")
    assert storage.node_store.node_exists(project_id, "child_001")

    # Assert: task.md content
    root_task = storage.node_store.load_task(project_id, "root_001")
    assert root_task["title"] == "Root Task"
    assert root_task["purpose"] == "Build something"

    child_task = storage.node_store.load_task(project_id, "child_001")
    assert child_task["title"] == "Child Task"
    assert child_task["purpose"] == "Do subthing"

    # Assert: state.yaml content
    root_state = storage.node_store.load_state(project_id, "root_001")
    assert root_state["phase"] == "planning"
    assert root_state["planning_thread_id"] == "thread_abc"

    child_state = storage.node_store.load_state(project_id, "child_001")
    assert child_state["phase"] == "planning"
    assert child_state["planning_thread_id"] == "thread_def"
    assert child_state["execution_thread_id"] == "thread_ghi"
    assert child_state["planning_thread_forked_from_node"] == "root_001"
    assert child_state["chat_session_id"] == "chat_xyz"


def test_v4_loads_without_migration(storage: Storage):
    """Already-migrated v4 tree.json loads directly without touching state.json."""
    ...


def test_migration_is_idempotent(storage: Storage):
    """Loading after migration doesn't re-migrate."""
    ...


def test_v4_tree_missing_node_files_fails_fast(storage: Storage):
    """A v4 tree.json that references missing node files is treated as corruption."""
    ...
```

---

## Step 11: Verify

1. **Run all tests**: `pytest backend/tests/ -v`
   - All existing tests pass (with the updates from Step 9)
   - New migration tests pass
2. **Manual verification**:
    - Create a new project via API → verify `tree.json` + `nodes/` directory created
    - Check `tree.json` has `node_index` dict format, schema_version 4
    - Check compat cache fields exist in `tree.json` for nodes that existing services still depend on
    - Check `nodes/{root_id}/task.md` exists with correct content
    - Create child node → verify child directory + task.md created
    - Split a node → verify child directories created
    - Load a project → verify API response still has `node_registry` array with all expected fields
3. **Migration test**:
    - Copy an existing v3 project directory
    - Load it via API → verify auto-migration creates tree.json + node files
    - Verify state.json renamed to state.json.bak
    - Delete a migrated node directory and reload → verify Phase B fails fast instead of auto-healing

---

## File Summary

| File | Action | Key Changes |
|------|--------|-------------|
| `backend/storage/project_store.py` | MODIFY | `tree_path()`, `_migrate_v3_to_v4()`, `load_tree()`/`save_tree()`, `create_project_files()` writes tree.json |
| `backend/storage/storage.py` | MODIFY | Add `node_store`, pass to `project_store` |
| `backend/services/project_service.py` | MODIFY | `create_project()` uses node_index + node files, `reset_to_root()` cleans node dirs |
| `backend/services/tree_service.py` | MODIFY | `node_index()` reads dict, replace `is_superseded` with `node_kind` |
| `backend/services/node_service.py` | MODIFY | `create_child()` writes to node_index + node files, `update_node()` syncs cache, `complete_node()` updates state.yaml |
| `backend/services/split_service.py` | MODIFY | `_make_node()` new fields, append to node_index, create node files |
| `backend/services/snapshot_view_service.py` | MODIFY | Dict→array conversion, compute `is_superseded` from `node_kind` |
| `backend/services/ask_service.py` | MODIFY | Replace internal `is_superseded` checks with `node_kind` checks |
| `backend/ai/split_context_builder.py` | MODIFY | Replace `is_superseded` check |
| `frontend/src/api/types.ts` | MODIFY | Add `NodePhase`, `NodeKind`, `NodeTask`, `NodeBriefing`, `NodeSpec`, update `NodeRecord` |
| `backend/tests/unit/test_schema_migration.py` | CREATE | Migration tests |
| Multiple test files | MODIFY | Update `node_registry` → `node_index` in internal snapshot access, `is_superseded` → `node_kind` |

**Total**: 10 modified files, 1 new test file, multiple test file updates.
