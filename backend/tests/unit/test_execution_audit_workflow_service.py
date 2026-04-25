from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from backend.business.workflow_v2.errors import WorkflowV2Error
from backend.services.execution_audit_workflow_service import (
    ExecutionAuditWorkflowService,
    GitArtifactService,
)


def test_git_artifact_service_normalizes_absolute_paths_for_worktree_diff(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    class _FakeGitService:
        def __init__(self) -> None:
            self.called_project_path: Path | None = None
            self.called_from_sha: str | None = None
            self.called_paths: list[str] | None = None

        def get_worktree_diff_against_sha_for_paths(
            self,
            project_path: Path,
            from_sha: str,
            paths: list[str],
        ) -> str:
            self.called_project_path = project_path
            self.called_from_sha = from_sha
            self.called_paths = list(paths)
            return "diff --git a/src/render.js b/src/render.js\n@@ -0,0 +1 @@\n+ok\n"

    fake_git = _FakeGitService()
    service = GitArtifactService(fake_git)  # type: ignore[arg-type]
    absolute_path = str((workspace_root / "src" / "render.js").resolve())

    diff_text = service.get_worktree_diff(
        workspace_root=str(workspace_root),
        start_sha="abc123",
        paths=[absolute_path],
    )

    assert "diff --git a/src/render.js b/src/render.js" in diff_text
    assert fake_git.called_project_path == workspace_root.resolve()
    assert fake_git.called_from_sha == "abc123"
    assert fake_git.called_paths == ["src/render.js"]


class _FakeQueryService:
    def __init__(self, initial_snapshot: dict[str, Any]) -> None:
        self.snapshot = copy.deepcopy(initial_snapshot)
        self.persist_calls: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

    def get_thread_snapshot(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return copy.deepcopy(self.snapshot)

    def persist_thread_mutation(
        self,
        _project_id: str,
        _node_id: str,
        _thread_role: str,
        updated_snapshot: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        self.snapshot = copy.deepcopy(updated_snapshot)
        self.persist_calls.append((copy.deepcopy(updated_snapshot), copy.deepcopy(events)))


class _FakeRuntime:
    def __init__(self, query_service: _FakeQueryService) -> None:
        self._query_service = query_service


class _RecordingArtifactService:
    def __init__(self, *, path_diff: str, full_diff: str = "") -> None:
        self.path_diff = path_diff
        self.full_diff = full_diff
        self.calls: list[dict[str, Any]] = []

    def get_worktree_diff(
        self,
        *,
        workspace_root: str | None,
        start_sha: str | None,
        paths: list[str] | None = None,
    ) -> str:
        self.calls.append(
            {
                "workspace_root": workspace_root,
                "start_sha": start_sha,
                "paths": copy.deepcopy(paths),
            }
        )
        if paths is None:
            return self.full_diff
        return self.path_diff


def _make_snapshot_for_file_change_item(
    *,
    turn_id: str,
    workspace_root: str,
    output_files: list[dict[str, Any]] | None = None,
    changes: list[dict[str, Any]] | None = None,
    output_text: str = "",
    arguments_text: str | None = None,
) -> dict[str, Any]:
    return {
        "threadId": "thread-exec-1",
        "activeTurnId": None,
        "updatedAt": "2026-04-03T00:00:00Z",
        "items": [
            {
                "id": "call_123",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": turn_id,
                "sequence": 3,
                "createdAt": "2026-04-03T00:00:01Z",
                "updatedAt": "2026-04-03T00:00:01Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "fileChange",
                "title": "fileChange",
                "toolName": None,
                "callId": None,
                "argumentsText": arguments_text,
                "outputText": output_text,
                "outputFiles": output_files
                if output_files is not None
                else [
                    {
                        "path": rf"{workspace_root}\src\render.js",
                        "changeType": "updated",
                        "summary": None,
                    }
                ],
                "changes": changes,
                "exitCode": None,
            }
        ],
    }


def _make_snapshot_for_command_only_item(*, turn_id: str) -> dict[str, Any]:
    return {
        "threadId": "thread-exec-1",
        "activeTurnId": None,
        "updatedAt": "2026-04-03T00:00:00Z",
        "items": [
            {
                "id": "cmd_123",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": turn_id,
                "sequence": 3,
                "createdAt": "2026-04-03T00:00:01Z",
                "updatedAt": "2026-04-03T00:00:01Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "commandExecution",
                "title": 'echo "hello" > src/output.txt',
                "toolName": "bash",
                "callId": "call_123",
                "argumentsText": 'echo "hello" > src/output.txt',
                "outputText": "",
                "outputFiles": [],
                "changes": [],
                "exitCode": 0,
            }
        ],
    }


def _run_hydration(
    *,
    snapshot: dict[str, Any],
    artifact_service: _RecordingArtifactService,
    workspace_root: str,
    start_sha: str = "abc123",
    turn_id: str = "exec_turn_1",
) -> _FakeQueryService:
    query_service = _FakeQueryService(snapshot)
    workflow_service = object.__new__(ExecutionAuditWorkflowService)
    workflow_service._thread_runtime_service_v2 = _FakeRuntime(query_service)  # type: ignore[attr-defined]
    workflow_service._artifact_service = artifact_service  # type: ignore[attr-defined]

    workflow_service._hydrate_execution_file_change_diff_from_worktree(
        project_id="project-1",
        node_id="node-1",
        turn_id=turn_id,
        workspace_root=workspace_root,
        start_sha=start_sha,
    )
    return query_service


def test_hydrate_execution_file_change_diff_from_worktree_replaces_changes_with_per_file_diff() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    render_path = rf"{workspace_root}\src\render.js"
    game_state_path = rf"{workspace_root}\src\game-state.js"
    snapshot = _make_snapshot_for_file_change_item(
        turn_id="exec_turn_1",
        workspace_root=workspace_root,
        output_files=[
            {"path": render_path, "changeType": "updated", "summary": None},
            {"path": game_state_path, "changeType": "updated", "summary": None},
        ],
    )
    artifact_service = _RecordingArtifactService(
        path_diff=(
            "diff --git a/src/game-state.js b/src/game-state.js\n"
            "@@ -1 +1 @@\n"
            "-oldGame\n"
            "+newGame\n"
            "diff --git a/src/render.js b/src/render.js\n"
            "@@ -1 +1 @@\n"
            "-oldRender\n"
            "+newRender\n"
        ),
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        artifact_service=artifact_service,
        workspace_root=workspace_root,
    )

    assert len(query_service.persist_calls) == 1
    updated_snapshot, persisted_events = query_service.persist_calls[0]
    assert len(persisted_events) >= 1
    updated_items = updated_snapshot.get("items", [])
    assert len(updated_items) == 1

    updated_item = updated_items[0]
    changes = updated_item.get("changes") if isinstance(updated_item.get("changes"), list) else []
    assert len(changes) == 2
    changes_by_path = {str(change.get("path") or ""): change for change in changes if isinstance(change, dict)}
    assert "newRender" in str(changes_by_path[render_path].get("diff") or "")
    assert "newGame" in str(changes_by_path[game_state_path].get("diff") or "")
    assert str(updated_item.get("outputText") or "") == ""

    mirrored_files = updated_item.get("outputFiles") if isinstance(updated_item.get("outputFiles"), list) else []
    assert len(mirrored_files) == 2
    mirrored_by_path = {str(file.get("path") or ""): file for file in mirrored_files if isinstance(file, dict)}
    assert "newRender" in str(mirrored_by_path[render_path].get("diff") or "")
    assert "newGame" in str(mirrored_by_path[game_state_path].get("diff") or "")


def test_hydrate_execution_file_change_diff_from_worktree_falls_back_to_full_diff_when_path_diff_is_empty() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    render_path = rf"{workspace_root}\src\render.js"
    snapshot = _make_snapshot_for_file_change_item(
        turn_id="exec_turn_1",
        workspace_root=workspace_root,
        output_files=[{"path": render_path, "changeType": "updated", "summary": None}],
    )
    artifact_service = _RecordingArtifactService(
        path_diff="",
        full_diff=(
            "diff --git a/src/render.js b/src/render.js\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+after\n"
        ),
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        artifact_service=artifact_service,
        workspace_root=workspace_root,
    )

    assert len(artifact_service.calls) == 2
    assert artifact_service.calls[0]["paths"] == [render_path]
    assert artifact_service.calls[1]["paths"] is None

    assert len(query_service.persist_calls) == 1
    updated_snapshot, _events = query_service.persist_calls[0]
    updated_item = updated_snapshot["items"][0]
    changes = updated_item.get("changes") if isinstance(updated_item.get("changes"), list) else []
    assert len(changes) == 1
    assert "after" in str(changes[0].get("diff") or "")


def test_hydrate_execution_file_change_diff_from_worktree_skips_when_item_already_has_structured_change_diff() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    render_path = rf"{workspace_root}\src\render.js"
    snapshot = _make_snapshot_for_file_change_item(
        turn_id="exec_turn_1",
        workspace_root=workspace_root,
        output_files=[{"path": render_path, "changeType": "updated", "summary": None}],
        changes=[
            {
                "path": render_path,
                "kind": "modify",
                "summary": None,
                "diff": "diff --git a/src/render.js b/src/render.js\n@@ -1 +1 @@\n-old\n+new\n",
            }
        ],
    )
    artifact_service = _RecordingArtifactService(
        path_diff="diff --git a/src/render.js b/src/render.js\n@@ -1 +1 @@\n-old\n+new\n",
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        artifact_service=artifact_service,
        workspace_root=workspace_root,
    )

    assert artifact_service.calls == []
    assert query_service.persist_calls == []


def test_hydrate_execution_file_change_diff_from_worktree_treats_explicit_empty_changes_as_authoritative() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    render_path = rf"{workspace_root}\src\render.js"
    snapshot = _make_snapshot_for_file_change_item(
        turn_id="exec_turn_1",
        workspace_root=workspace_root,
        output_files=[{"path": render_path, "changeType": "updated", "summary": None}],
        changes=[],
    )
    artifact_service = _RecordingArtifactService(
        path_diff="diff --git a/src/render.js b/src/render.js\n@@ -1 +1 @@\n-old\n+new\n",
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        artifact_service=artifact_service,
        workspace_root=workspace_root,
    )

    assert artifact_service.calls == []
    assert query_service.persist_calls == []


def test_hydrate_execution_file_change_diff_from_worktree_matches_same_basename_by_path_suffix() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    src_render_path = rf"{workspace_root}\src\render.js"
    tests_render_path = rf"{workspace_root}\tests\render.js"
    snapshot = _make_snapshot_for_file_change_item(
        turn_id="exec_turn_1",
        workspace_root=workspace_root,
        output_files=[
            {"path": src_render_path, "changeType": "updated", "summary": None},
            {"path": tests_render_path, "changeType": "updated", "summary": None},
        ],
    )
    artifact_service = _RecordingArtifactService(
        path_diff=(
            "diff --git a/src/render.js b/src/render.js\n"
            "@@ -1 +1 @@\n"
            "-old-src\n"
            "+new-src\n"
            "diff --git a/tests/render.js b/tests/render.js\n"
            "@@ -1 +1 @@\n"
            "-old-tests\n"
            "+new-tests\n"
        ),
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        artifact_service=artifact_service,
        workspace_root=workspace_root,
    )

    assert len(query_service.persist_calls) == 1
    updated_snapshot, _events = query_service.persist_calls[0]
    updated_item = updated_snapshot["items"][0]
    changes = updated_item.get("changes") if isinstance(updated_item.get("changes"), list) else []
    assert len(changes) == 2
    changes_by_path = {str(change.get("path") or ""): change for change in changes if isinstance(change, dict)}
    assert "new-src" in str(changes_by_path[src_render_path].get("diff") or "")
    assert "new-tests" in str(changes_by_path[tests_render_path].get("diff") or "")


def test_hydrate_execution_file_change_diff_from_worktree_creates_synthetic_file_change_for_command_only_turn() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    snapshot = _make_snapshot_for_command_only_item(turn_id="exec_turn_1")
    artifact_service = _RecordingArtifactService(
        path_diff="",
        full_diff=(
            "diff --git a/src/output.txt b/src/output.txt\n"
            "new file mode 100644\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/src/output.txt\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
        ),
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        artifact_service=artifact_service,
        workspace_root=workspace_root,
    )

    assert len(artifact_service.calls) == 1
    assert artifact_service.calls[0]["paths"] is None
    assert len(query_service.persist_calls) == 1
    updated_snapshot, _events = query_service.persist_calls[0]
    updated_items = updated_snapshot.get("items", [])
    assert len(updated_items) == 2

    synthetic_item = next(
        item for item in updated_items
        if isinstance(item, dict) and str(item.get("id") or "") == "turn:exec_turn_1:hydrated-file-change"
    )
    assert synthetic_item["toolType"] == "fileChange"
    assert synthetic_item["title"] == "File changes"
    assert synthetic_item["toolName"] == "git-diff-hydrator"

    changes = synthetic_item.get("changes") if isinstance(synthetic_item.get("changes"), list) else []
    assert len(changes) == 1
    assert changes[0]["path"] == "src/output.txt"
    assert changes[0]["kind"] == "add"
    assert "hello" in str(changes[0].get("diff") or "")

    mirrored_files = synthetic_item.get("outputFiles") if isinstance(synthetic_item.get("outputFiles"), list) else []
    assert len(mirrored_files) == 1
    assert mirrored_files[0]["path"] == "src/output.txt"
    assert mirrored_files[0]["changeType"] == "created"


def test_hydrate_execution_file_change_diff_from_worktree_filters_out_planningtree_from_synthetic_changes() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    snapshot = _make_snapshot_for_command_only_item(turn_id="exec_turn_1")
    artifact_service = _RecordingArtifactService(
        path_diff="",
        full_diff=(
            "diff --git a/.planningtree/root/state.json b/.planningtree/root/state.json\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/src/app.ts b/src/app.ts\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+after\n"
        ),
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        artifact_service=artifact_service,
        workspace_root=workspace_root,
    )

    assert len(query_service.persist_calls) == 1
    updated_snapshot, _events = query_service.persist_calls[0]
    synthetic_item = next(
        item for item in updated_snapshot.get("items", [])
        if isinstance(item, dict) and str(item.get("id") or "") == "turn:exec_turn_1:hydrated-file-change"
    )
    changes = synthetic_item.get("changes") if isinstance(synthetic_item.get("changes"), list) else []
    assert len(changes) == 1
    assert changes[0]["path"] == "src/app.ts"
    assert "after" in str(changes[0].get("diff") or "")
    assert all(".planningtree" not in str(change.get("path") or "") for change in changes)


class _FakeGitCommitService:
    def __init__(self, *, initial_sha: str, committed_sha: str | None) -> None:
        self.initial_sha = initial_sha
        self.committed_sha = committed_sha
        self.commit_calls: list[tuple[str, str]] = []

    def capture_head_sha(self, project_path: Path) -> str:
        return self.initial_sha

    def build_commit_message(self, hierarchical_number: str, title: str) -> str:
        return f"pt({hierarchical_number}): {title.lower()}"

    def commit_if_changed(self, project_path: Path, commit_message: str) -> str | None:
        self.commit_calls.append((str(project_path), commit_message))
        return self.committed_sha


def test_git_artifact_service_commit_workspace_returns_metadata_when_diff_exists(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    fake_git = _FakeGitCommitService(initial_sha="a" * 40, committed_sha="b" * 40)
    service = GitArtifactService(fake_git)  # type: ignore[arg-type]

    result = service.commit_workspace(
        workspace_root=str(workspace_root),
        hierarchical_number="1.2",
        title="Build API",
        verb="done",
    )

    assert result == {
        "initialSha": "a" * 40,
        "headSha": "b" * 40,
        "commitMessage": "pt(1.2): done build api",
        "committed": True,
    }
    assert fake_git.commit_calls == [(str(workspace_root.resolve()), "pt(1.2): done build api")]


def test_git_artifact_service_commit_workspace_records_no_diff_as_non_committed(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    fake_git = _FakeGitCommitService(initial_sha="c" * 40, committed_sha=None)
    service = GitArtifactService(fake_git)  # type: ignore[arg-type]

    result = service.commit_workspace(
        workspace_root=str(workspace_root),
        hierarchical_number="1.3",
        title="Review API",
        verb="review",
    )

    assert result == {
        "initialSha": "c" * 40,
        "headSha": "c" * 40,
        "commitMessage": "pt(1.3): review review api",
        "committed": False,
    }
    assert fake_git.commit_calls == [(str(workspace_root.resolve()), "pt(1.3): review review api")]


class _NoopProjectLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _InMemoryWorkflowStateStore:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = copy.deepcopy(state)
        self.write_calls: list[dict[str, Any]] = []

    def read_state(self, _project_id: str, _node_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.state)

    def write_state(self, _project_id: str, _node_id: str, state: dict[str, Any]) -> dict[str, Any]:
        self.state = copy.deepcopy(state)
        self.write_calls.append(copy.deepcopy(state))
        return copy.deepcopy(self.state)


class _InMemoryExecutionRunStore:
    def __init__(self, runs: list[dict[str, Any]]) -> None:
        self.runs = copy.deepcopy(runs)

    def read_runs(self, _project_id: str, _node_id: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.runs)

    def write_runs(self, _project_id: str, _node_id: str, runs: list[dict[str, Any]]) -> None:
        self.runs = copy.deepcopy(runs)


class _InMemoryReviewCycleStore:
    def __init__(self) -> None:
        self.cycles: list[dict[str, Any]] = []

    def append_cycle(self, _project_id: str, _node_id: str, cycle: dict[str, Any]) -> None:
        self.cycles.append(copy.deepcopy(cycle))

    def read_cycles(self, _project_id: str, _node_id: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.cycles)


class _InMemoryStorage:
    def __init__(self, *, state: dict[str, Any], runs: list[dict[str, Any]]) -> None:
        self.workflow_state_store = _InMemoryWorkflowStateStore(state)
        self.execution_run_store = _InMemoryExecutionRunStore(runs)
        self.review_cycle_store = _InMemoryReviewCycleStore()

    def project_lock(self, _project_id: str) -> _NoopProjectLock:
        return _NoopProjectLock()


class _FlowArtifactService:
    def __init__(self, *, commit_result: dict[str, Any]) -> None:
        self.commit_result = copy.deepcopy(commit_result)
        self.commit_calls: list[dict[str, Any]] = []
        self.hash_checks: list[tuple[str | None, str]] = []
        self.head_checks: list[tuple[str | None, str]] = []

    def require_workspace_hash(self, workspace_root: str | None, expected_workspace_hash: str) -> str:
        self.hash_checks.append((workspace_root, expected_workspace_hash))
        return expected_workspace_hash

    def require_head_sha(self, workspace_root: str | None, expected_head_sha: str) -> str:
        self.head_checks.append((workspace_root, expected_head_sha))
        return expected_head_sha

    def commit_workspace(
        self,
        *,
        workspace_root: str | None,
        hierarchical_number: str,
        title: str,
        verb: str,
    ) -> dict[str, Any]:
        self.commit_calls.append(
            {
                "workspace_root": workspace_root,
                "hierarchical_number": hierarchical_number,
                "title": title,
                "verb": verb,
            }
        )
        return copy.deepcopy(self.commit_result)


class _FlowMetadataService:
    def __init__(
        self,
        *,
        workspace_root: str,
        hierarchical_number: str,
        title: str,
        node_id: str = "node-1",
    ) -> None:
        self.workspace_root = workspace_root
        self.hierarchical_number = hierarchical_number
        self.title = title
        self.node_id = node_id
        self.spec_content = "## Spec\n- Implement feature"
        self.frame_content = "## Frame\n- Keep behavior stable"

    def load_execution_metadata(self, _project_id: str, _node_id: str) -> dict[str, Any]:
        snapshot = {
            "tree_state": {
                "root_node_id": "root-1",
                "node_index": {
                    "root-1": {
                        "node_id": "root-1",
                        "parent_id": None,
                        "child_ids": [self.node_id],
                        "node_kind": "root",
                        "hierarchical_number": "1",
                        "title": "Root",
                    },
                    self.node_id: {
                        "node_id": self.node_id,
                        "parent_id": "root-1",
                        "child_ids": [],
                        "node_kind": "original",
                        "hierarchical_number": self.hierarchical_number,
                        "title": self.title,
                    },
                },
            }
        }
        node_payload = copy.deepcopy(snapshot["tree_state"]["node_index"][self.node_id])
        return {
            "workspaceRoot": self.workspace_root,
            "specContent": self.spec_content,
            "frameContent": self.frame_content,
            "node": node_payload,
            "snapshot": snapshot,
        }

    def build_audit_review_prompt(
        self,
        *,
        node: dict[str, Any],
        spec_content: str,
        frame_content: str,
        review_commit_sha: str,
    ) -> str:
        del node
        return (
            "I just completed code for this task.\n"
            f"The task spec is: {spec_content}\n"
            f"The confirmed frame is: {frame_content}\n"
            f"The commit hash is {review_commit_sha}\n"
            "Please review this implementation. Do you have any questions or issues?"
        )


class _FlowThreadRuntimeService:
    def __init__(self) -> None:
        self.begin_turn_calls: list[dict[str, Any]] = []

    def begin_turn(self, **kwargs: Any) -> None:
        self.begin_turn_calls.append(dict(kwargs))


def _legacy_service_without_v2_orchestrator() -> ExecutionAuditWorkflowService:
    service = object.__new__(ExecutionAuditWorkflowService)
    service._workflow_orchestrator_v2 = None  # type: ignore[attr-defined]
    return service


def _assert_requires_workflow_core_v2(callable_action) -> None:
    with pytest.raises(WorkflowV2Error) as exc_info:
        callable_action()
    assert exc_info.value.code == "ERR_WORKFLOW_V2_ORCHESTRATOR_UNAVAILABLE"
    assert exc_info.value.status_code == 503
    assert exc_info.value.details == {"surface": "execution_audit_workflow_service"}


def test_mark_done_from_execution_requires_workflow_core_v2() -> None:
    service = _legacy_service_without_v2_orchestrator()

    _assert_requires_workflow_core_v2(
        lambda: service.mark_done_from_execution(
            "project-1",
            "node-1",
            idempotency_key="idem-1",
            expected_workspace_hash="workspace-hash-1",
        )
    )


def test_review_in_audit_requires_workflow_core_v2() -> None:
    service = _legacy_service_without_v2_orchestrator()

    _assert_requires_workflow_core_v2(
        lambda: service.review_in_audit(
            "project-1",
            "node-1",
            idempotency_key="idem-review-1",
            expected_workspace_hash="workspace-hash-2",
        )
    )


def test_improve_in_execution_requires_workflow_core_v2() -> None:
    service = _legacy_service_without_v2_orchestrator()

    _assert_requires_workflow_core_v2(
        lambda: service.improve_in_execution(
            "project-1",
            "node-1",
            idempotency_key="idem-improve-1",
            expected_review_commit_sha="f" * 40,
        )
    )


def test_mark_done_from_audit_requires_workflow_core_v2() -> None:
    service = _legacy_service_without_v2_orchestrator()

    _assert_requires_workflow_core_v2(
        lambda: service.mark_done_from_audit(
            "project-1",
            "node-1",
            idempotency_key="idem-audit-1",
            expected_review_commit_sha="f" * 40,
        )
    )


def test_finish_task_requires_workflow_core_v2() -> None:
    service = _legacy_service_without_v2_orchestrator()

    _assert_requires_workflow_core_v2(
        lambda: service.finish_task(
            "project-1",
            "node-1",
            idempotency_key="idem-finish-1",
        )
    )


def test_handoff_upsert_creates_replaces_orders_and_is_idempotent(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    handoff_path = workspace_root / "docs" / "handoff.md"

    snapshot = {
        "tree_state": {
            "root_node_id": "root-1",
            "node_index": {
                "root-1": {
                    "node_id": "root-1",
                    "parent_id": None,
                    "child_ids": ["node-a", "node-b", "node-c"],
                    "node_kind": "root",
                    "hierarchical_number": "1",
                    "title": "Root",
                },
                "node-a": {
                    "node_id": "node-a",
                    "parent_id": "root-1",
                    "child_ids": [],
                    "node_kind": "original",
                    "hierarchical_number": "1.1",
                    "title": "A",
                },
                "node-b": {
                    "node_id": "node-b",
                    "parent_id": "root-1",
                    "child_ids": [],
                    "node_kind": "original",
                    "hierarchical_number": "1.2",
                    "title": "B",
                },
                "node-c": {
                    "node_id": "node-c",
                    "parent_id": "root-1",
                    "child_ids": [],
                    "node_kind": "original",
                    "hierarchical_number": "1.3",
                    "title": "C",
                },
            },
        }
    }
    service = object.__new__(ExecutionAuditWorkflowService)

    service._upsert_handoff_summary_locked(  # type: ignore[attr-defined]
        project_id="project-1",
        node_id="node-a",
        workspace_root=str(workspace_root),
        snapshot=snapshot,
        node=snapshot["tree_state"]["node_index"]["node-a"],
        summary_text="Summary A",
    )
    assert handoff_path.exists()
    first_content = handoff_path.read_text(encoding="utf-8")
    assert "<!-- PT_HANDOFF_NODE:node-a -->" in first_content

    service._upsert_handoff_summary_locked(  # type: ignore[attr-defined]
        project_id="project-1",
        node_id="node-a",
        workspace_root=str(workspace_root),
        snapshot=snapshot,
        node=snapshot["tree_state"]["node_index"]["node-a"],
        summary_text="Summary A",
    )
    second_content = handoff_path.read_text(encoding="utf-8")
    assert second_content == first_content

    service._upsert_handoff_summary_locked(  # type: ignore[attr-defined]
        project_id="project-1",
        node_id="node-a",
        workspace_root=str(workspace_root),
        snapshot=snapshot,
        node=snapshot["tree_state"]["node_index"]["node-a"],
        summary_text="Summary A (updated)",
    )
    updated_content = handoff_path.read_text(encoding="utf-8")
    assert "Summary A (updated)" in updated_content
    assert "Summary A\n" not in updated_content

    service._upsert_handoff_summary_locked(  # type: ignore[attr-defined]
        project_id="project-1",
        node_id="node-c",
        workspace_root=str(workspace_root),
        snapshot=snapshot,
        node=snapshot["tree_state"]["node_index"]["node-c"],
        summary_text="Summary C",
    )
    service._upsert_handoff_summary_locked(  # type: ignore[attr-defined]
        project_id="project-1",
        node_id="node-b",
        workspace_root=str(workspace_root),
        snapshot=snapshot,
        node=snapshot["tree_state"]["node_index"]["node-b"],
        summary_text="Summary B",
    )
    ordered_content = handoff_path.read_text(encoding="utf-8")
    index_a = ordered_content.index("<!-- PT_HANDOFF_NODE:node-a -->")
    index_b = ordered_content.index("<!-- PT_HANDOFF_NODE:node-b -->")
    index_c = ordered_content.index("<!-- PT_HANDOFF_NODE:node-c -->")
    assert index_a < index_b < index_c


def test_normalize_review_response_text_extracts_summary_from_json_object() -> None:
    text, from_json = ExecutionAuditWorkflowService._normalize_review_response_text(
        '{"summary":"Local review completed with no blocking issues.","findings":[]}'
    )
    assert from_json is True
    assert text == "Local review completed with no blocking issues."


def test_normalize_review_response_text_extracts_summary_from_json_fence() -> None:
    text, from_json = ExecutionAuditWorkflowService._normalize_review_response_text(
        '```json\n{"summary":"Review passed after checking changed files."}\n```'
    )
    assert from_json is True
    assert text == "Review passed after checking changed files."


def test_normalize_review_response_text_keeps_plain_markdown_when_not_json() -> None:
    text, from_json = ExecutionAuditWorkflowService._normalize_review_response_text(
        "No serious issues found.\n\n- Checked tests\n- Checked diff"
    )
    assert from_json is False
    assert text == "No serious issues found.\n\n- Checked tests\n- Checked diff"
