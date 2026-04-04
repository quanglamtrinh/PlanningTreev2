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
