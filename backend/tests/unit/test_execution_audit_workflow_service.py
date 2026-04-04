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


def test_hydrate_execution_file_change_diff_from_worktree_persists_patch() -> None:
    snapshot: dict[str, Any] = {
        "threadId": "thread-exec-1",
        "activeTurnId": None,
        "updatedAt": "2026-04-03T00:00:00Z",
        "items": [
            {
                "id": "call_123",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": "exec_turn_1",
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
                "argumentsText": None,
                "outputText": "",
                "outputFiles": [
                    {
                        "path": r"C:\Users\Thong\Tic tac toe\src\render.js",
                        "changeType": "updated",
                        "summary": None,
                    }
                ],
                "exitCode": None,
            }
        ],
    }

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

    class _FakeArtifactService:
        def get_worktree_diff(self, *, workspace_root: str | None, start_sha: str | None, paths: list[str] | None = None) -> str:
            if workspace_root and start_sha and paths:
                return "diff --git a/src/render.js b/src/render.js\n@@ -1 +1 @@\n-old\n+new\n"
            return ""

    query_service = _FakeQueryService(snapshot)
    workflow_service = object.__new__(ExecutionAuditWorkflowService)
    workflow_service._thread_runtime_service_v2 = _FakeRuntime(query_service)  # type: ignore[attr-defined]
    workflow_service._artifact_service = _FakeArtifactService()  # type: ignore[attr-defined]

    workflow_service._hydrate_execution_file_change_diff_from_worktree(
        project_id="project-1",
        node_id="node-1",
        turn_id="exec_turn_1",
        workspace_root=r"C:\Users\Thong\Tic tac toe",
        start_sha="abc123",
    )

    assert len(query_service.persist_calls) == 1
    updated_snapshot, persisted_events = query_service.persist_calls[0]
    updated_items = updated_snapshot.get("items", [])
    assert len(updated_items) == 1
    output_text = str(updated_items[0].get("outputText") or "")
    assert "diff --git a/src/render.js b/src/render.js" in output_text
    assert "old" in output_text and "new" in output_text
    assert len(persisted_events) >= 1
