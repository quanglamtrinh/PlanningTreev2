# Phase A: Storage Layer — Node File I/O

## Goal

Add per-node file read/write utilities for `task.md`, `briefing.md`, `spec.md`, and `state.yaml`. No behavior change to existing system — this phase only adds new code and a new dependency.

## Prerequisites

- Spec reference: [NODE_MODEL_SPEC.md](NODE_MODEL_SPEC.md)
- Checklist: [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md)

---

## Step 1: Add PyYAML dependency

**File**: `pyproject.toml`

Add `"pyyaml>=6.0"` to the `dependencies` list:
```python
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.0.0",
    "openai>=1.0.0",
    "aiofiles>=24.0.0",
    "python-multipart>=0.0.9",
    "pyyaml>=6.0",                   # <-- add
]
```

Then run `uv sync` (or `pip install -e .`) to install.

**Verify**: `python -c "import yaml; print(yaml.__version__)"` succeeds.

---

## Step 2: Add `atomic_write_text` to file_utils.py

**File**: `backend/storage/file_utils.py`

Add a function that follows the exact same atomic-write pattern as `atomic_write_json` but writes plain text (for `.md` and `.yaml` files).

```python
def atomic_write_text(path: Path, content: str) -> None:
    """Atomically write text content to a file."""
    ensure_dir(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)
```

Also add a required-file text reading helper:
```python
def load_text(path: Path) -> str:
    """Read a required text file."""
    with path.open("r", encoding="utf-8") as handle:
        return handle.read()
```

**Rationale**: Reuses the same atomic pattern (write to .tmp, fsync, rename) that `atomic_write_json` already uses. Keeps file I/O consistent across the codebase.

**Read contract**:
- `load_text()` is for required per-node files only
- Missing files raise `FileNotFoundError`
- Empty/default documents come from creation helpers, not from read-time fallback

---

## Step 3: Create `backend/storage/node_files.py`

**File**: `backend/storage/node_files.py` (NEW)

This module provides low-level parse/render functions for the 4 per-node files. It operates on `Path` objects (node directory) and returns/accepts plain dicts.

### 3.1: Markdown section parser

```python
def parse_md_sections(text: str) -> dict[str, str]:
    """Parse canonical markdown text into sections keyed by top-level ## heading.

    Returns a dict where keys are heading text (stripped) and
    values are the content under that heading (stripped).
    Ignores the top-level # heading.
    Raises ValueError on duplicate top-level ## headings.

    Example:
        "# Task\n\n## Title\nFoo\n\n## Purpose\nBar"
        -> {"Title": "Foo", "Purpose": "Bar"}
    """
```

**Implementation logic**:
1. Split text by lines
2. Iterate, looking for lines starting with exactly `## `
3. When a `## ` line is found, save the heading as the current key
4. Accumulate subsequent non-heading lines as the current section's content
5. Strip leading/trailing whitespace from each section's content
6. Skip lines starting with `# ` (top-level heading) — these are structural, not content
7. Treat `### ` and deeper headings as normal section body content
8. If a top-level `## ` heading repeats, raise `ValueError`

**Edge cases to handle**:
- Empty file → return `{}`
- File with only a `# ` heading and no `## ` sections → return `{}`
- Section with no content → value is `""`
- Multiple blank lines between sections → stripped to single content
- Content before any `## ` heading → ignored (it's under the `# ` title)
- `###` and deeper headings remain part of the current section body

### 3.1b: Markdown section validator

```python
def validate_sections(doc_name: str, sections: dict[str, str], allowed: list[str]) -> None:
    """Validate canonical top-level sections for a markdown document."""
```

**Validation rules**:
- Every top-level `##` heading must be in `allowed`
- Every heading in `allowed` must be present exactly once
- Unknown headings raise `ValueError`
- Duplicate headings are rejected by `parse_md_sections()`
- Empty files or files with missing canonical sections raise `ValueError`

### 3.2: Markdown section renderer

```python
def render_md_sections(doc_title: str, sections: dict[str, str]) -> str:
    """Render a dict of sections into markdown with ## headings.

    Args:
        doc_title: The top-level # heading (e.g., "Task", "Briefing")
        sections: Ordered dict of heading -> content

    Returns:
        Markdown string with # title followed by ## sections.
    """
```

**Implementation logic**:
1. Start with `# {doc_title}\n\n`
2. For each (heading, content) in sections:
   - Write `## {heading}\n`
   - If content is non-empty, write `{content}\n`
   - Write a blank line after each section
3. Return the assembled string

### 3.3: Task file operations

```python
TASK_SECTIONS = ["Title", "Purpose", "Responsibility"]

def read_task(node_dir: Path) -> dict[str, str]:
    """Read task.md and return {title, purpose, responsibility}."""
    text = load_text(node_dir / "task.md")
    sections = parse_md_sections(text)
    validate_sections("task.md", sections, TASK_SECTIONS)
    return {
        "title": sections.get("Title", ""),
        "purpose": sections.get("Purpose", ""),
        "responsibility": sections.get("Responsibility", ""),
    }

def write_task(node_dir: Path, task: dict[str, str]) -> None:
    """Write task dict to task.md."""
    sections = {
        "Title": task.get("title", ""),
        "Purpose": task.get("purpose", ""),
        "Responsibility": task.get("responsibility", ""),
    }
    content = render_md_sections("Task", sections)
    atomic_write_text(node_dir / "task.md", content)
```

**Key mapping**:
- `task["title"]` ↔ `## Title` section
- `task["purpose"]` ↔ `## Purpose` section
- `task["responsibility"]` ↔ `## Responsibility` section

**Validation behavior**:
- Missing `task.md` raises `FileNotFoundError`
- Unknown or missing canonical sections raise `ValueError`
- Duplicate top-level `##` sections raise `ValueError`

### 3.4: Briefing file operations

```python
BRIEFING_SECTIONS = [
    "User-Pinned Notes",
    "Business / Product Context",
    "Technical / System Context",
    "Execution Context",
    "Clarified Answers",
]

def read_briefing(node_dir: Path) -> dict[str, str]:
    """Read briefing.md and return dict with 5 sections."""
    text = load_text(node_dir / "briefing.md")
    sections = parse_md_sections(text)
    validate_sections("briefing.md", sections, BRIEFING_SECTIONS)
    return {
        "user_notes": sections.get("User-Pinned Notes", ""),
        "business_context": sections.get("Business / Product Context", ""),
        "technical_context": sections.get("Technical / System Context", ""),
        "execution_context": sections.get("Execution Context", ""),
        "clarified_answers": sections.get("Clarified Answers", ""),
    }

def write_briefing(node_dir: Path, briefing: dict[str, str]) -> None:
    """Write briefing dict to briefing.md."""
    sections = {
        "User-Pinned Notes": briefing.get("user_notes", ""),
        "Business / Product Context": briefing.get("business_context", ""),
        "Technical / System Context": briefing.get("technical_context", ""),
        "Execution Context": briefing.get("execution_context", ""),
        "Clarified Answers": briefing.get("clarified_answers", ""),
    }
    content = render_md_sections("Briefing", sections)
    atomic_write_text(node_dir / "briefing.md", content)
```

**Key mapping**:
- `briefing["user_notes"]` ↔ `## User-Pinned Notes`
- `briefing["business_context"]` ↔ `## Business / Product Context`
- `briefing["technical_context"]` ↔ `## Technical / System Context`
- `briefing["execution_context"]` ↔ `## Execution Context`
- `briefing["clarified_answers"]` ↔ `## Clarified Answers`

**Note on clarified_answers**: In the spec, clarified answers are described as a list of `{summary, context_text}` objects. However, since briefing.md is a markdown file, we store clarified answers as markdown text (e.g., `- **summary**: context_text`). The conversion between list-of-dicts and markdown bullet format happens at the service layer, not here. `node_files.py` treats it as a plain string section.

**Validation behavior**:
- Missing `briefing.md` raises `FileNotFoundError`
- Unknown or missing canonical sections raise `ValueError`
- Duplicate top-level `##` sections raise `ValueError`

### 3.5: Spec file operations

```python
SPEC_SECTIONS = [
    "1. Business / Product Contract",
    "2. Technical Contract",
    "3. Delivery & Acceptance",
    "4. Assumptions",
]

def read_spec(node_dir: Path) -> dict[str, str]:
    """Read spec.md and return dict with 4 sections."""
    text = load_text(node_dir / "spec.md")
    sections = parse_md_sections(text)
    validate_sections("spec.md", sections, SPEC_SECTIONS)
    return {
        "business_contract": sections.get("1. Business / Product Contract", ""),
        "technical_contract": sections.get("2. Technical Contract", ""),
        "delivery_acceptance": sections.get("3. Delivery & Acceptance", ""),
        "assumptions": sections.get("4. Assumptions", ""),
    }

def write_spec(node_dir: Path, spec: dict[str, str]) -> None:
    """Write spec dict to spec.md."""
    sections = {
        "1. Business / Product Contract": spec.get("business_contract", ""),
        "2. Technical Contract": spec.get("technical_contract", ""),
        "3. Delivery & Acceptance": spec.get("delivery_acceptance", ""),
        "4. Assumptions": spec.get("assumptions", ""),
    }
    content = render_md_sections("Spec", sections)
    atomic_write_text(node_dir / "spec.md", content)
```

### 3.6: State file operations

```python
import yaml

STATE_DEFAULTS: dict[str, Any] = {
    "phase": "planning",
    "task_confirmed": False,
    "briefing_confirmed": False,
    "spec_generated": False,
    "spec_confirmed": False,
    "planning_thread_id": "",
    "execution_thread_id": "",
    "ask_thread_id": "",
    "planning_thread_forked_from_node": "",
    "planning_thread_bootstrapped_at": "",
    "chat_session_id": "",
}

def read_state(node_dir: Path) -> dict[str, Any]:
    """Read state.yaml and return dict with state fields.

    Returns a complete state dict by merging the parsed file over STATE_DEFAULTS.
    Raises ValueError if the file is empty, malformed, or does not contain a mapping.
    """
    text = load_text(node_dir / "state.yaml")
    if not text.strip():
        raise ValueError("state.yaml is empty")
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError("state.yaml must contain a mapping")
    result = dict(STATE_DEFAULTS)
    result.update(parsed)
    return result

def write_state(node_dir: Path, state: dict[str, Any]) -> None:
    """Write state dict to state.yaml."""
    # Write a canonical full state file with known fields in a fixed order.
    ordered = dict(STATE_DEFAULTS)
    for key in STATE_DEFAULTS:
        if key in state:
            ordered[key] = state[key]
    content = yaml.safe_dump(ordered, default_flow_style=False, sort_keys=False, allow_unicode=True)
    atomic_write_text(node_dir / "state.yaml", content)
```

**Key behaviors**:
- `read_state` requires an existing `state.yaml`; missing files raise `FileNotFoundError`
- `read_state` merges parsed fields over `STATE_DEFAULTS` so callers always get a complete dict
- Empty, malformed, or non-mapping YAML raises `ValueError`
- `write_state` writes only known fields, merged over `STATE_DEFAULTS`, in a defined order
- Uses `yaml.safe_load` / `yaml.safe_dump` with `sort_keys=False` to preserve field order

### 3.7: Convenience functions

```python
def create_node_directory(node_dir: Path, task: dict, briefing: dict, spec: dict, state: dict) -> None:
    """Create a node directory with all 4 files."""
    if node_dir.exists():
        raise FileExistsError(f"Node directory already exists: {node_dir}")
    ensure_dir(node_dir)
    write_task(node_dir, task)
    write_briefing(node_dir, briefing)
    write_spec(node_dir, spec)
    write_state(node_dir, state)

def load_all(node_dir: Path) -> dict[str, dict]:
    """Read all 4 documents from a node directory."""
    return {
        "task": read_task(node_dir),
        "briefing": read_briefing(node_dir),
        "spec": read_spec(node_dir),
        "state": read_state(node_dir),
    }

def empty_task() -> dict[str, str]:
    return {"title": "", "purpose": "", "responsibility": ""}

def empty_briefing() -> dict[str, str]:
    return {"user_notes": "", "business_context": "", "technical_context": "",
            "execution_context": "", "clarified_answers": ""}

def empty_spec() -> dict[str, str]:
    return {"business_contract": "", "technical_contract": "",
            "delivery_acceptance": "", "assumptions": ""}

def default_state() -> dict[str, Any]:
    return dict(STATE_DEFAULTS)
```

---

## Step 4: Create `backend/storage/node_store.py`

**File**: `backend/storage/node_store.py` (NEW)

This module provides a project-aware wrapper around `node_files.py`. It handles path resolution and integrates with the existing project locking pattern.

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.storage.node_files import (
    create_node_directory,
    default_state,
    empty_briefing,
    empty_spec,
    empty_task,
    load_all as load_all_node_files,
    read_briefing,
    read_spec,
    read_state,
    read_task,
    write_briefing,
    write_spec,
    write_state,
    write_task,
)
from backend.storage.project_ids import normalize_project_id


class NodeStore:
    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    def _project_dir(self, project_id: str) -> Path:
        return self._paths.projects_root / normalize_project_id(project_id)

    def _nodes_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "nodes"

    def node_dir(self, project_id: str, node_id: str) -> Path:
        return self._nodes_dir(project_id) / node_id

    # --- Create ---

    def create_node_files(
        self,
        project_id: str,
        node_id: str,
        task: dict[str, str] | None = None,
        briefing: dict[str, str] | None = None,
        spec: dict[str, str] | None = None,
        state: dict[str, Any] | None = None,
    ) -> Path:
        """Create a node directory with all 4 files. Returns the node directory path."""
        node_path = self.node_dir(project_id, node_id)
        create_node_directory(
            node_path,
            task=task or empty_task(),
            briefing=briefing or empty_briefing(),
            spec=spec or empty_spec(),
            state=state or default_state(),
        )
        return node_path

    # --- Load ---

    def load_all(self, project_id: str, node_id: str) -> dict[str, dict]:
        """Load all 4 documents for a node."""
        return load_all_node_files(self.node_dir(project_id, node_id))

    def load_task(self, project_id: str, node_id: str) -> dict[str, str]:
        return read_task(self.node_dir(project_id, node_id))

    def load_briefing(self, project_id: str, node_id: str) -> dict[str, str]:
        return read_briefing(self.node_dir(project_id, node_id))

    def load_spec(self, project_id: str, node_id: str) -> dict[str, str]:
        return read_spec(self.node_dir(project_id, node_id))

    def load_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        return read_state(self.node_dir(project_id, node_id))

    # --- Save ---

    def save_task(self, project_id: str, node_id: str, task: dict[str, str]) -> None:
        write_task(self.node_dir(project_id, node_id), task)

    def save_briefing(self, project_id: str, node_id: str, briefing: dict[str, str]) -> None:
        write_briefing(self.node_dir(project_id, node_id), briefing)

    def save_spec(self, project_id: str, node_id: str, spec: dict[str, str]) -> None:
        write_spec(self.node_dir(project_id, node_id), spec)

    def save_state(self, project_id: str, node_id: str, state: dict[str, Any]) -> None:
        write_state(self.node_dir(project_id, node_id), state)

    # --- Delete ---

    def delete_node_files(self, project_id: str, node_id: str) -> None:
        """Remove a node's directory and all files."""
        import shutil
        node_path = self.node_dir(project_id, node_id)
        if node_path.exists():
            shutil.rmtree(node_path)

    # --- Query ---

    def node_exists(self, project_id: str, node_id: str) -> bool:
        node_path = self.node_dir(project_id, node_id)
        required_files = ("task.md", "briefing.md", "spec.md", "state.yaml")
        return node_path.is_dir() and all((node_path / name).is_file() for name in required_files)
```

**Design notes**:
- `NodeStore` does NOT take `ProjectLockRegistry` — locking is the caller's responsibility (same as how `ThreadStore` and `ChatStore` are used within locked blocks in the services)
- Methods are simple wrappers that resolve paths and delegate to `node_files.py`
- `create_node_files` accepts optional overrides; defaults to empty documents
- `node_exists()` means the canonical node directory is fully present, not just that the directory exists
- Load methods do not synthesize defaults for missing/corrupt node files

---

## Step 5: Wire NodeStore into Storage

**File**: `backend/storage/storage.py`

Add `NodeStore` as a new attribute:

```python
from backend.storage.node_store import NodeStore

class Storage:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._project_locks = ProjectLockRegistry()
        self.config_store = ConfigStore(paths)
        self.project_store = ProjectStore(paths, self._project_locks)
        self.chat_store = ChatStore(paths, self._project_locks)
        self.thread_store = ThreadStore(paths, self._project_locks)
        self.node_store = NodeStore(paths)             # <-- add
```

---

## Step 6: Write tests

**File**: `backend/tests/unit/test_node_files.py` (NEW)

### Test categories:

**6.1: Markdown parser tests**
```python
def test_parse_md_sections_basic():
    """Parse standard markdown with # title and ## sections."""
    text = "# Task\n\n## Title\nBuild thing\n\n## Purpose\nFor demo\n"
    result = parse_md_sections(text)
    assert result == {"Title": "Build thing", "Purpose": "For demo"}

def test_parse_md_sections_empty():
    """Empty string returns empty dict."""
    assert parse_md_sections("") == {}

def test_parse_md_sections_no_subsections():
    """Only a # heading with no ## sections returns empty dict."""
    assert parse_md_sections("# Task\nSome content\n") == {}

def test_parse_md_sections_empty_section():
    """Section with heading but no content returns empty string."""
    text = "# Task\n\n## Title\n\n## Purpose\nHello\n"
    result = parse_md_sections(text)
    assert result["Title"] == ""
    assert result["Purpose"] == "Hello"

def test_parse_md_sections_multiline_content():
    """Section content spans multiple lines."""
    text = "# Spec\n\n## 1. Business / Product Contract\n- Item 1\n- Item 2\n\nMore text\n"
    result = parse_md_sections(text)
    assert "- Item 1\n- Item 2\n\nMore text" == result["1. Business / Product Contract"]

def test_parse_md_sections_special_characters():
    """Section content with special characters (markdown, unicode)."""
    text = "# Task\n\n## Title\nBuild `thing` with **bold** & émojis\n"
    result = parse_md_sections(text)
    assert result["Title"] == "Build `thing` with **bold** & émojis"

def test_parse_md_sections_duplicate_heading_raises():
    """Duplicate top-level ## headings are invalid."""
    text = "# Task\n\n## Title\nOne\n\n## Title\nTwo\n"
    with pytest.raises(ValueError):
        parse_md_sections(text)
```

**6.2: Markdown renderer tests**
```python
def test_render_md_sections_basic():
    """Render sections into markdown."""
    sections = {"Title": "Foo", "Purpose": "Bar"}
    result = render_md_sections("Task", sections)
    assert "# Task" in result
    assert "## Title\nFoo" in result
    assert "## Purpose\nBar" in result

def test_render_md_sections_empty_content():
    """Empty section content still renders the heading."""
    sections = {"Title": "", "Purpose": "Bar"}
    result = render_md_sections("Task", sections)
    assert "## Title\n" in result
```

**6.3: Round-trip tests for each file type**
```python
def test_task_round_trip(tmp_path):
    """Write task → read task → same data."""
    task = {"title": "Build UI", "purpose": "For demo", "responsibility": "Catalog page"}
    write_task(tmp_path, task)
    assert read_task(tmp_path) == task
    # Verify actual file exists and is readable markdown
    content = (tmp_path / "task.md").read_text()
    assert "## Title" in content
    assert "Build UI" in content

def test_briefing_round_trip(tmp_path):
    briefing = {
        "user_notes": "Keep simple",
        "business_context": "Browse only",
        "technical_context": "React + TS",
        "execution_context": "Code output",
        "clarified_answers": "- **Filter**: Not needed",
    }
    write_briefing(tmp_path, briefing)
    assert read_briefing(tmp_path) == briefing

def test_spec_round_trip(tmp_path):
    spec = {
        "business_contract": "- Show catalog",
        "technical_contract": "- Use existing schema",
        "delivery_acceptance": "- Page loads",
        "assumptions": "- Seeded data OK",
    }
    write_spec(tmp_path, spec)
    assert read_spec(tmp_path) == spec

def test_state_round_trip(tmp_path):
    state = {
        "phase": "briefing_review",
        "task_confirmed": True,
        "briefing_confirmed": False,
        "spec_generated": False,
        "spec_confirmed": False,
        "planning_thread_id": "thread_abc",
        "execution_thread_id": "",
        "ask_thread_id": "",
        "planning_thread_forked_from_node": "node_xyz",
        "planning_thread_bootstrapped_at": "2026-03-12T00:00:00+00:00",
        "chat_session_id": "",
    }
    write_state(tmp_path, state)
    assert read_state(tmp_path) == state
    # Verify YAML file
    content = (tmp_path / "state.yaml").read_text()
    assert "phase: briefing_review" in content
    assert "task_confirmed: true" in content
```

**6.3b: Canonical validation tests**
```python
def test_read_task_rejects_unknown_top_level_heading(tmp_path):
    (tmp_path / "task.md").write_text("# Task\n\n## Title\nA\n\n## Purpose\nB\n\n## Extra\nC\n")
    with pytest.raises(ValueError):
        read_task(tmp_path)

def test_read_briefing_rejects_missing_required_section(tmp_path):
    (tmp_path / "briefing.md").write_text("# Briefing\n\n## User-Pinned Notes\nA\n")
    with pytest.raises(ValueError):
        read_briefing(tmp_path)
```

**6.4: Default/empty factory tests**
```python
def test_empty_task():
    t = empty_task()
    assert t == {"title": "", "purpose": "", "responsibility": ""}

def test_empty_briefing():
    b = empty_briefing()
    assert all(v == "" for v in b.values())

def test_empty_spec():
    s = empty_spec()
    assert all(v == "" for v in s.values())

def test_default_state():
    s = default_state()
    assert s["phase"] == "planning"
    assert s["task_confirmed"] is False
```

**6.5: State read validation tests**
```python
def test_read_state_fills_defaults(tmp_path):
    """Reading a state.yaml with missing fields fills from defaults."""
    (tmp_path / "state.yaml").write_text("phase: executing\n")
    state = read_state(tmp_path)
    assert state["phase"] == "executing"
    assert state["task_confirmed"] is False  # filled from default
    assert state["planning_thread_id"] == ""  # filled from default

def test_read_state_missing_file(tmp_path):
    """Missing state.yaml fails fast."""
    with pytest.raises(FileNotFoundError):
        read_state(tmp_path)

def test_read_state_malformed_yaml(tmp_path):
    """Malformed YAML fails fast."""
    (tmp_path / "state.yaml").write_text("phase: [\n")
    with pytest.raises(ValueError):
        read_state(tmp_path)

def test_read_state_non_mapping_yaml(tmp_path):
    """Non-mapping YAML fails fast."""
    (tmp_path / "state.yaml").write_text("- planning\n- executing\n")
    with pytest.raises(ValueError):
        read_state(tmp_path)
```

**6.6: Create/read-all convenience tests**
```python
def test_create_node_directory_and_read_all(tmp_path):
    node_dir = tmp_path / "test_node"
    task = {"title": "Test", "purpose": "Testing", "responsibility": "Unit test"}
    create_node_directory(node_dir, task, empty_briefing(), empty_spec(), default_state())
    assert node_dir.exists()
    assert (node_dir / "task.md").exists()
    assert (node_dir / "briefing.md").exists()
    assert (node_dir / "spec.md").exists()
    assert (node_dir / "state.yaml").exists()
    docs = load_all(node_dir)
    assert docs["task"] == task
    assert docs["state"]["phase"] == "planning"

def test_create_node_directory_existing_path_raises(tmp_path):
    node_dir = tmp_path / "test_node"
    create_node_directory(node_dir, empty_task(), empty_briefing(), empty_spec(), default_state())
    with pytest.raises(FileExistsError):
        create_node_directory(node_dir, empty_task(), empty_briefing(), empty_spec(), default_state())
```

**File**: `backend/tests/unit/test_node_store.py` (NEW)

```python
def test_create_and_load(tmp_path):
    """NodeStore creates directory and loads documents."""
    paths = AppPaths(data_root=tmp_path, projects_root=tmp_path / "projects", config_root=tmp_path / "config")
    store = NodeStore(paths)
    # Create project dir structure
    (tmp_path / "projects" / "test_project").mkdir(parents=True)
    store.create_node_files("test_project", "node_001", task={"title": "Hello", "purpose": "World", "responsibility": ""})
    assert store.node_exists("test_project", "node_001")
    task = store.load_task("test_project", "node_001")
    assert task["title"] == "Hello"

def test_save_and_reload(tmp_path):
    """Save individual document, reload, verify."""
    paths = AppPaths(data_root=tmp_path, projects_root=tmp_path / "projects", config_root=tmp_path / "config")
    store = NodeStore(paths)
    (tmp_path / "projects" / "test_project").mkdir(parents=True)
    store.create_node_files("test_project", "node_002")
    store.save_briefing("test_project", "node_002", {"user_notes": "Important!", "business_context": "", "technical_context": "", "execution_context": "", "clarified_answers": ""})
    briefing = store.load_briefing("test_project", "node_002")
    assert briefing["user_notes"] == "Important!"

def test_delete_node_files(tmp_path):
    paths = AppPaths(data_root=tmp_path, projects_root=tmp_path / "projects", config_root=tmp_path / "config")
    store = NodeStore(paths)
    (tmp_path / "projects" / "test_project").mkdir(parents=True)
    store.create_node_files("test_project", "node_003")
    assert store.node_exists("test_project", "node_003")
    store.delete_node_files("test_project", "node_003")
    assert not store.node_exists("test_project", "node_003")
```

---

## Step 7: Verify

1. **Install dependency**: `uv sync` or `pip install pyyaml`
2. **Run new tests**: `pytest backend/tests/unit/test_node_files.py backend/tests/unit/test_node_store.py -v`
3. **Run all existing tests**: `pytest backend/tests/` — all must still pass (no existing behavior changed)
4. **Manual smoke test**:
   ```python
   from pathlib import Path
   from backend.storage.node_files import create_node_directory, load_all, empty_briefing, empty_spec, default_state

   node_dir = Path("/tmp/test_node")
   create_node_directory(
       node_dir,
       task={"title": "Test Task", "purpose": "Verify it works", "responsibility": "Phase A"},
       briefing=empty_briefing(),
       spec=empty_spec(),
       state=default_state(),
   )
   # Inspect the files on disk
   print((node_dir / "task.md").read_text())
   print((node_dir / "state.yaml").read_text())
   # Read them back
   docs = load_all(node_dir)
   print(docs)
   ```

---

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | MODIFY | Add `pyyaml>=6.0` |
| `backend/storage/file_utils.py` | MODIFY | Add `atomic_write_text()`, `load_text()` |
| `backend/storage/node_files.py` | CREATE | Markdown/YAML parse+render for 4 file types |
| `backend/storage/node_store.py` | CREATE | Project-aware node file CRUD |
| `backend/storage/storage.py` | MODIFY | Add `node_store: NodeStore` attribute |
| `backend/tests/unit/test_node_files.py` | CREATE | Unit tests for parse/render/round-trip |
| `backend/tests/unit/test_node_store.py` | CREATE | Unit tests for NodeStore CRUD |

**Total**: 2 modified files, 4 new files, 1 dependency added.
