"""Integration tests for the git checkpoint lifecycle.

Covers:
  1. Full flow: init git -> confirm spec -> finish task -> verify commit & detail-state -> reset
  2. Dirty tree is allowed during finish task
  3. No-diff execution (Codex makes no changes)
  4. Reset to initial and reset to head
  5. probe_git_initialized subfolder behavior
  6. Init blocks nested repo
  7. Failed execution retry
  8. Failed execution does not freeze shaping
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.services import planningtree_workspace
from backend.services.thread_lineage_service import _ROLLOUT_BOOTSTRAP_PROMPT
from backend.tests.conftest import init_git_repo


# ---------------------------------------------------------------------------
# Fake Codex clients
# ---------------------------------------------------------------------------

class _ExecutionCodex:
    """Fake Codex client that writes a file in workspace and returns."""

    def __init__(self, *, create_file: str = "output.txt", fail: bool = False) -> None:
        self._create_file = create_file
        self._fail = fail
        self.started_threads: list[str] = []
        self.forked_threads: list[dict] = []

    def start_thread(self, **_):
        tid = f"thread-{len(self.started_threads) + 1}"
        self.started_threads.append(tid)
        return {"thread_id": tid}

    def resume_thread(self, thread_id, **_):
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id, **kwargs):
        tid = f"fork-{len(self.forked_threads) + 1}"
        self.forked_threads.append({"thread_id": tid, "source": source_thread_id, **kwargs})
        return {"thread_id": tid}

    def run_turn_streaming(self, prompt, **kwargs):
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": kwargs.get("thread_id", ""), "turn_status": "completed"}
        if self._fail:
            raise RuntimeError("Codex exploded")
        cwd = kwargs.get("cwd")
        if cwd and self._create_file:
            Path(cwd, self._create_file).write_text("generated content\n")
        return {"stdout": "Done.", "thread_id": kwargs.get("thread_id", ""), "turn_status": "completed"}


class _NoDiffCodex(_ExecutionCodex):
    """Fake Codex client that does NOT write any file."""

    def __init__(self):
        super().__init__(create_file="")


class _FailingCodex(_ExecutionCodex):
    """Fake Codex client that always fails."""

    def __init__(self):
        super().__init__(fail=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_project(client: TestClient, workspace_root: Path) -> tuple[str, str]:
    resp = client.post("/v3/projects/attach", json={"folder_path": str(workspace_root)})
    assert resp.status_code == 200
    snap = resp.json()
    return snap["project"]["id"], snap["tree_state"]["root_node_id"]


def _confirm_spec(client: TestClient, project_id: str, node_id: str) -> None:
    client.put(
        f"/v3/projects/{project_id}/nodes/{node_id}/documents/frame",
        json={"content": "# Task Title\nTask\n\n# Objective\nDo it\n"},
    )
    client.post(f"/v3/projects/{project_id}/nodes/{node_id}/confirm-frame")
    client.put(
        f"/v3/projects/{project_id}/nodes/{node_id}/documents/spec",
        json={"content": "# Spec\nImplement it\n"},
    )
    client.post(f"/v3/projects/{project_id}/nodes/{node_id}/confirm-spec")
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = "ready"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)


def _wait_execution(client: TestClient, project_id: str, node_id: str, status: str = "completed", timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        es = client.app.state.storage.execution_state_store.read_state(project_id, node_id)
        if es and es.get("status") == status:
            return es
        time.sleep(0.02)
    raise AssertionError(f"Execution did not reach status={status} in time.")


def _wait_no_live_turns(client: TestClient, project_id: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        chat_service = client.app.state.chat_service
        if chat_service is None or not chat_service.has_live_turns_for_project(project_id):
            return
        time.sleep(0.05)
    raise AssertionError("Live turns did not drain before reset.")


def _set_codex(client: TestClient, codex):
    client.app.state.codex_client = codex
    client.app.state.chat_service._codex_client = codex
    client.app.state.finish_task_service._codex_client = codex
    client.app.state.thread_lineage_service._codex_client = codex
    client.app.state.review_service._codex_client = codex
    client.app.state.thread_query_service_v3._codex_client = codex
    client.app.state.thread_runtime_service_v3._codex_client = codex
    client.app.state.execution_audit_workflow_service._codex_client = codex


def _set_temp_global_git_identity(monkeypatch, workspace_root: Path) -> None:
    """Provide a per-test global git identity without touching the user's config."""
    gitconfig = workspace_root.parent / ".test-global-gitconfig"
    gitconfig.write_text("[user]\n\tname = Test\n\temail = t@t.com\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_full_lifecycle(client: TestClient, workspace_root):
    """Init git -> finish task -> verify commit + detail-state -> reset."""
    init_git_repo(workspace_root)
    codex = _ExecutionCodex()
    _set_codex(client, codex)

    project_id, root_id = _setup_project(client, workspace_root)
    _confirm_spec(client, project_id, root_id)

    # Finish task
    resp = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/finish-task")
    assert resp.status_code == 200

    exec_state = _wait_execution(client, project_id, root_id)
    assert exec_state["initial_sha"] is not None
    assert len(exec_state["initial_sha"]) == 40  # git hex SHA
    assert exec_state["head_sha"] is not None
    assert len(exec_state["head_sha"]) == 40
    assert exec_state["initial_sha"] != exec_state["head_sha"]  # output.txt was created
    assert exec_state["commit_message"] is not None
    assert exec_state["commit_message"].startswith("pt(")

    # Verify changed_files
    assert isinstance(exec_state["changed_files"], list)
    assert len(exec_state["changed_files"]) > 0
    paths = [f["path"] for f in exec_state["changed_files"]]
    assert "output.txt" in paths

    # Verify detail-state
    detail = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/detail-state").json()
    assert detail["initial_sha"] == exec_state["initial_sha"]
    assert detail["head_sha"] == exec_state["head_sha"]
    assert detail["commit_message"] == exec_state["commit_message"]
    assert detail["current_head_sha"] == exec_state["head_sha"]
    assert detail["task_present_in_current_workspace"] is True
    assert detail["git_ready"] is True

    _wait_no_live_turns(client, project_id)

    # Reset to initial
    reset_resp = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/reset-workspace",
        json={"target": "initial"},
    )
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data["target_sha"] == exec_state["initial_sha"]
    assert reset_data["task_present_in_current_workspace"] is False

    # Reset to head
    reset_resp2 = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/reset-workspace",
        json={"target": "head"},
    )
    assert reset_resp2.status_code == 200
    assert reset_resp2.json()["task_present_in_current_workspace"] is True


def test_dirty_tree_does_not_block_finish_task(client: TestClient, workspace_root):
    """Dirty working tree is temporarily allowed during finish task."""
    init_git_repo(workspace_root)
    codex = _ExecutionCodex()
    _set_codex(client, codex)

    project_id, root_id = _setup_project(client, workspace_root)
    _confirm_spec(client, project_id, root_id)

    # Make workspace dirty
    (workspace_root / "uncommitted.txt").write_text("dirty")

    resp = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/finish-task")
    assert resp.status_code == 200

    _wait_execution(client, project_id, root_id)

    # Detail state should stay git_ready=true even with dirty workspace.
    detail = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/detail-state").json()
    assert detail["git_ready"] is True
    assert detail["git_blocker_message"] is None


def test_no_diff_execution(client: TestClient, workspace_root):
    """Codex makes no changes -> no commit, head_sha = initial_sha."""
    init_git_repo(workspace_root)
    codex = _NoDiffCodex()
    _set_codex(client, codex)

    project_id, root_id = _setup_project(client, workspace_root)
    _confirm_spec(client, project_id, root_id)

    resp = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/finish-task")
    assert resp.status_code == 200

    exec_state = _wait_execution(client, project_id, root_id)
    assert exec_state["head_sha"] == exec_state["initial_sha"]
    assert exec_state["commit_message"] is None
    assert exec_state["changed_files"] == []


def test_probe_git_initialized_subfolder(client: TestClient, tmp_path):
    """Subfolder of parent repo -> git_initialized = false."""
    parent = tmp_path / "parent"
    parent.mkdir()
    init_git_repo(parent)

    subfolder = parent / "child_project"
    subfolder.mkdir()

    resp = client.post("/v3/projects/attach", json={"folder_path": str(subfolder)})
    assert resp.status_code == 200
    project_id = resp.json()["project"]["id"]

    projects = client.get("/v3/projects").json()
    project = next(p for p in projects if p["id"] == project_id)
    assert project.get("git_initialized") is False


def test_init_blocks_nested_repo(client: TestClient, tmp_path):
    """git init inside subfolder of existing repo -> 400."""
    parent = tmp_path / "parent_repo"
    parent.mkdir()
    init_git_repo(parent)

    subfolder = parent / "nested_project"
    subfolder.mkdir()

    resp = client.post("/v3/projects/attach", json={"folder_path": str(subfolder)})
    assert resp.status_code == 200
    project_id = resp.json()["project"]["id"]

    init_resp = client.post(f"/v3/projects/{project_id}/git/init")
    assert init_resp.status_code == 400
    assert "inside" in init_resp.json()["message"].lower()


def test_init_git_success(client: TestClient, workspace_root, monkeypatch):
    """git init on a fresh project -> success."""
    project_id, root_id = _setup_project(client, workspace_root)

    # Before init: git_initialized = false
    projects = client.get("/v3/projects").json()
    project = next(p for p in projects if p["id"] == project_id)
    assert project.get("git_initialized") is False

    # Configure git identity for this test only; do not mutate the real global config.
    _set_temp_global_git_identity(monkeypatch, workspace_root)

    init_resp = client.post(f"/v3/projects/{project_id}/git/init")
    assert init_resp.status_code == 200
    body = init_resp.json()
    assert body["status"] == "initialized"
    assert len(body["head_sha"]) == 40

    # After init: git_initialized = true
    projects = client.get("/v3/projects").json()
    project = next(p for p in projects if p["id"] == project_id)
    assert project.get("git_initialized") is True


def test_failed_execution_retry(client: TestClient, workspace_root):
    """Execution fails -> status=failed -> retry succeeds."""
    init_git_repo(workspace_root)
    failing_codex = _FailingCodex()
    _set_codex(client, failing_codex)

    project_id, root_id = _setup_project(client, workspace_root)
    _confirm_spec(client, project_id, root_id)

    # First attempt: fails
    resp = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/finish-task")
    assert resp.status_code == 200

    exec_state = _wait_execution(client, project_id, root_id, status="failed")
    assert exec_state["status"] == "failed"
    assert exec_state["error_message"] is not None

    # Retry with working codex
    good_codex = _ExecutionCodex()
    _set_codex(client, good_codex)

    resp2 = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/finish-task")
    assert resp2.status_code == 200

    exec_state2 = _wait_execution(client, project_id, root_id, status="completed")
    assert exec_state2["status"] == "completed"
    assert exec_state2["head_sha"] is not None


def test_failed_execution_does_not_freeze_shaping(client: TestClient, workspace_root):
    """Failed execution -> shaping is NOT frozen -> frame/spec still editable."""
    init_git_repo(workspace_root)
    failing_codex = _FailingCodex()
    _set_codex(client, failing_codex)

    project_id, root_id = _setup_project(client, workspace_root)
    _confirm_spec(client, project_id, root_id)

    resp = client.post(f"/v3/projects/{project_id}/nodes/{root_id}/finish-task")
    assert resp.status_code == 200

    _wait_execution(client, project_id, root_id, status="failed")

    # Shaping should not be frozen — detail-state should allow editing
    detail = client.get(f"/v3/projects/{project_id}/nodes/{root_id}/detail-state").json()
    assert detail.get("shaping_frozen") is not True


def test_reset_no_exec_state(client: TestClient, workspace_root):
    """Reset on node with no execution state -> 400."""
    init_git_repo(workspace_root)
    project_id, root_id = _setup_project(client, workspace_root)

    resp = client.post(
        f"/v3/projects/{project_id}/nodes/{root_id}/reset-workspace",
        json={"target": "initial"},
    )
    assert resp.status_code == 400
