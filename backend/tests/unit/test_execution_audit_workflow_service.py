from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

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
    def __init__(self, *, workspace_root: str, hierarchical_number: str, title: str) -> None:
        self.workspace_root = workspace_root
        self.hierarchical_number = hierarchical_number
        self.title = title

    def load_execution_metadata(self, _project_id: str, _node_id: str) -> dict[str, Any]:
        return {
            "workspaceRoot": self.workspace_root,
            "node": {
                "hierarchical_number": self.hierarchical_number,
                "title": self.title,
            },
        }


class _FlowThreadRuntimeService:
    def __init__(self) -> None:
        self.begin_turn_calls: list[dict[str, Any]] = []

    def begin_turn(self, **kwargs: Any) -> None:
        self.begin_turn_calls.append(dict(kwargs))


def test_mark_done_from_execution_writes_latest_commit_metadata() -> None:
    state = {
        "workflowPhase": "execution_decision_pending",
        "currentExecutionDecision": {"sourceExecutionRunId": "run-1"},
        "mutationCache": {},
    }
    runs = [{"runId": "run-1", "summaryText": "Execution summary"}]
    storage = _InMemoryStorage(state=state, runs=runs)
    artifact_service = _FlowArtifactService(
        commit_result={
            "initialSha": "a" * 40,
            "headSha": "b" * 40,
            "commitMessage": "pt(1.1): done build feature",
            "committed": True,
        }
    )
    metadata_service = _FlowMetadataService(
        workspace_root=r"C:\repo\workspace",
        hierarchical_number="1.1",
        title="Build Feature",
    )
    progression_calls: list[dict[str, Any]] = []

    service = object.__new__(ExecutionAuditWorkflowService)
    service._storage = storage  # type: ignore[attr-defined]
    service._artifact_service = artifact_service  # type: ignore[attr-defined]
    service._metadata_service = metadata_service  # type: ignore[attr-defined]
    service._ensure_workflow_state_locked = lambda _project_id, _node_id: storage.workflow_state_store.state  # type: ignore[attr-defined]
    service._get_cached_mutation = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    service._store_cached_mutation = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    service._publish_workflow_refresh = lambda **_kwargs: None  # type: ignore[attr-defined]
    service.get_workflow_state = lambda _project_id, _node_id: copy.deepcopy(storage.workflow_state_store.state)  # type: ignore[attr-defined]
    service._complete_node_progression = lambda _project_id, _node_id, *, accepted_sha, summary_text: progression_calls.append(  # type: ignore[attr-defined]
        {"accepted_sha": accepted_sha, "summary_text": summary_text}
    )

    response = service.mark_done_from_execution(
        "project-1",
        "node-1",
        idempotency_key="idem-1",
        expected_workspace_hash="workspace-hash-1",
    )

    assert response["acceptedSha"] == "b" * 40
    assert response["workflowPhase"] == "done"
    latest_commit = storage.workflow_state_store.state.get("latestCommit")
    assert isinstance(latest_commit, dict)
    assert latest_commit["sourceAction"] == "mark_done_from_execution"
    assert latest_commit["initialSha"] == "a" * 40
    assert latest_commit["headSha"] == "b" * 40
    assert latest_commit["commitMessage"] == "pt(1.1): done build feature"
    assert latest_commit["committed"] is True
    assert isinstance(latest_commit["recordedAt"], str) and latest_commit["recordedAt"]
    assert storage.execution_run_store.runs[0]["committedHeadSha"] == "b" * 40
    assert storage.execution_run_store.runs[0]["decision"] == "marked_done"
    assert progression_calls == [{"accepted_sha": "b" * 40, "summary_text": "Execution summary"}]


def test_review_in_audit_writes_latest_commit_metadata_and_uses_head_sha(monkeypatch) -> None:
    state = {
        "workflowPhase": "execution_decision_pending",
        "currentExecutionDecision": {"sourceExecutionRunId": "run-2"},
        "auditLineageThreadId": "audit-lineage-thread-1",
        "reviewThreadId": None,
        "mutationCache": {},
    }
    runs = [{"runId": "run-2"}]
    storage = _InMemoryStorage(state=state, runs=runs)
    artifact_service = _FlowArtifactService(
        commit_result={
            "initialSha": "c" * 40,
            "headSha": "c" * 40,
            "commitMessage": "pt(1.2): review add tests",
            "committed": False,
        }
    )
    metadata_service = _FlowMetadataService(
        workspace_root=r"C:\repo\workspace",
        hierarchical_number="1.2",
        title="Add Tests",
    )
    runtime_service = _FlowThreadRuntimeService()

    scheduled_threads: list[dict[str, Any]] = []

    class _FakeThread:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            scheduled_threads.append({"args": args, "kwargs": kwargs})

        def start(self) -> None:
            return None

    monkeypatch.setattr("backend.services.execution_audit_workflow_service.threading.Thread", _FakeThread)

    service = object.__new__(ExecutionAuditWorkflowService)
    service._storage = storage  # type: ignore[attr-defined]
    service._artifact_service = artifact_service  # type: ignore[attr-defined]
    service._metadata_service = metadata_service  # type: ignore[attr-defined]
    service._thread_runtime_service_v2 = runtime_service  # type: ignore[attr-defined]
    service._ensure_workflow_state_locked = lambda _project_id, _node_id: storage.workflow_state_store.state  # type: ignore[attr-defined]
    service._ensure_audit_lineage_thread_id = lambda _project_id, _node_id, _workspace_root: "audit-lineage-thread-1"  # type: ignore[attr-defined]
    service._get_cached_mutation = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    service._store_cached_mutation = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    service._publish_workflow_refresh = lambda **_kwargs: None  # type: ignore[attr-defined]
    service._bind_audit_thread_to_review_thread = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]

    response = service.review_in_audit(
        "project-1",
        "node-1",
        idempotency_key="idem-review-1",
        expected_workspace_hash="workspace-hash-2",
    )

    assert response["accepted"] is True
    assert response["workflowPhase"] == "audit_running"
    assert len(storage.review_cycle_store.cycles) == 1
    cycle = storage.review_cycle_store.cycles[0]
    assert cycle["reviewCommitSha"] == "c" * 40
    assert cycle["deliveryKind"] == "detached"
    latest_commit = storage.workflow_state_store.state.get("latestCommit")
    assert isinstance(latest_commit, dict)
    assert latest_commit["sourceAction"] == "review_in_audit"
    assert latest_commit["initialSha"] == "c" * 40
    assert latest_commit["headSha"] == cycle["reviewCommitSha"]
    assert latest_commit["commitMessage"] == "pt(1.2): review add tests"
    assert latest_commit["committed"] is False
    assert isinstance(latest_commit["recordedAt"], str) and latest_commit["recordedAt"]
    assert storage.execution_run_store.runs[0]["committedHeadSha"] == "c" * 40
    assert storage.execution_run_store.runs[0]["decision"] == "sent_to_review"
    assert len(runtime_service.begin_turn_calls) == 1
    assert len(scheduled_threads) == 1
    assert scheduled_threads[0]["kwargs"]["kwargs"]["review_commit_sha"] == "c" * 40


def test_mark_done_from_audit_keeps_existing_latest_commit_metadata() -> None:
    existing_latest_commit = {
        "sourceAction": "review_in_audit",
        "initialSha": "e" * 40,
        "headSha": "f" * 40,
        "commitMessage": "pt(1.3): review verify release",
        "committed": True,
        "recordedAt": "2026-04-04T00:00:00Z",
    }
    state = {
        "workflowPhase": "audit_decision_pending",
        "currentAuditDecision": {"sourceReviewCycleId": "cycle-1"},
        "latestCommit": copy.deepcopy(existing_latest_commit),
        "mutationCache": {},
    }
    storage = _InMemoryStorage(state=state, runs=[])
    storage.review_cycle_store.cycles = [
        {
            "cycleId": "cycle-1",
            "finalReviewText": "Final audit summary",
        }
    ]
    artifact_service = _FlowArtifactService(
        commit_result={
            "initialSha": "ignored",
            "headSha": "ignored",
            "commitMessage": "ignored",
            "committed": False,
        }
    )
    metadata_service = _FlowMetadataService(
        workspace_root=r"C:\repo\workspace",
        hierarchical_number="1.3",
        title="Verify Release",
    )
    progression_calls: list[dict[str, Any]] = []

    service = object.__new__(ExecutionAuditWorkflowService)
    service._storage = storage  # type: ignore[attr-defined]
    service._artifact_service = artifact_service  # type: ignore[attr-defined]
    service._metadata_service = metadata_service  # type: ignore[attr-defined]
    service._ensure_workflow_state_locked = lambda _project_id, _node_id: storage.workflow_state_store.state  # type: ignore[attr-defined]
    service._get_cached_mutation = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    service._store_cached_mutation = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    service._publish_workflow_refresh = lambda **_kwargs: None  # type: ignore[attr-defined]
    service.get_workflow_state = lambda _project_id, _node_id: copy.deepcopy(storage.workflow_state_store.state)  # type: ignore[attr-defined]
    service._complete_node_progression = lambda _project_id, _node_id, *, accepted_sha, summary_text: progression_calls.append(  # type: ignore[attr-defined]
        {"accepted_sha": accepted_sha, "summary_text": summary_text}
    )

    response = service.mark_done_from_audit(
        "project-1",
        "node-1",
        idempotency_key="idem-audit-1",
        expected_review_commit_sha="f" * 40,
    )

    assert response["workflowPhase"] == "done"
    assert storage.workflow_state_store.state["acceptedSha"] == "f" * 40
    assert storage.workflow_state_store.state.get("latestCommit") == existing_latest_commit
    assert artifact_service.head_checks == [(r"C:\repo\workspace", "f" * 40)]
    assert artifact_service.commit_calls == []
    assert progression_calls == [{"accepted_sha": "f" * 40, "summary_text": "Final audit summary"}]
