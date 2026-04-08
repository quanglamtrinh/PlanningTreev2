from __future__ import annotations

import copy
from typing import Any

from backend.services.finish_task_service import FinishTaskService


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


class _RecordingGitDiffService:
    def __init__(self, *, diff_for_paths: str, full_diff: str) -> None:
        self.diff_for_paths = diff_for_paths
        self.full_diff = full_diff
        self.calls: list[dict[str, Any]] = []

    def get_diff_for_paths(
        self,
        project_path: Any,
        initial_sha: str,
        head_sha: str,
        paths: list[str],
    ) -> str:
        self.calls.append(
            {
                "kind": "paths",
                "project_path": str(project_path),
                "initial_sha": initial_sha,
                "head_sha": head_sha,
                "paths": list(paths),
            }
        )
        return self.diff_for_paths

    def get_diff(
        self,
        project_path: Any,
        initial_sha: str,
        head_sha: str,
    ) -> str:
        self.calls.append(
            {
                "kind": "full",
                "project_path": str(project_path),
                "initial_sha": initial_sha,
                "head_sha": head_sha,
            }
        )
        return self.full_diff


def _run_hydration(
    *,
    snapshot: dict[str, Any],
    git_service: _RecordingGitDiffService,
    turn_id: str = "exec_turn_1",
    workspace_root: str = r"C:\Users\Thong\Tic tac toe",
) -> _FakeQueryService:
    query_service = _FakeQueryService(snapshot)
    finish_service = object.__new__(FinishTaskService)
    finish_service._thread_runtime_service_v2 = _FakeRuntime(query_service)  # type: ignore[attr-defined]
    finish_service._git_checkpoint_service = git_service  # type: ignore[attr-defined]
    finish_service._hydrate_execution_file_change_diff_v2(
        project_id="project-1",
        node_id="node-1",
        turn_id=turn_id,
        workspace_root=workspace_root,
        initial_sha="a" * 40,
        head_sha="b" * 40,
    )
    return query_service


def test_finish_task_hydrate_creates_synthetic_file_change_for_command_only_turn() -> None:
    snapshot = {
        "threadId": "thread-exec-1",
        "items": [
            {
                "id": "cmd_1",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": "exec_turn_1",
                "sequence": 1,
                "createdAt": "2026-04-05T00:00:01Z",
                "updatedAt": "2026-04-05T00:00:01Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "commandExecution",
                "title": 'echo "hello" > src/output.txt',
                "toolName": "bash",
                "callId": "call_1",
                "argumentsText": 'echo "hello" > src/output.txt',
                "outputText": "",
                "outputFiles": [],
                "changes": [],
                "exitCode": 0,
            }
        ],
    }
    git_service = _RecordingGitDiffService(
        diff_for_paths="",
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

    query_service = _run_hydration(snapshot=snapshot, git_service=git_service)

    assert len(git_service.calls) == 1
    assert git_service.calls[0]["kind"] == "full"
    assert len(query_service.persist_calls) == 1
    updated_snapshot, _events = query_service.persist_calls[0]
    synthetic_item = next(
        item for item in updated_snapshot["items"]
        if str(item.get("id") or "") == "turn:exec_turn_1:hydrated-file-change"
    )
    assert synthetic_item["toolType"] == "fileChange"
    changes = synthetic_item.get("changes") if isinstance(synthetic_item.get("changes"), list) else []
    assert len(changes) == 1
    assert changes[0]["path"] == "src/output.txt"
    assert changes[0]["kind"] == "add"
    assert "hello" in str(changes[0].get("diff") or "")


def test_finish_task_hydrate_filters_out_planningtree_from_synthetic_changes() -> None:
    snapshot = {
        "threadId": "thread-exec-1",
        "items": [
            {
                "id": "cmd_1",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": "exec_turn_1",
                "sequence": 1,
                "createdAt": "2026-04-05T00:00:01Z",
                "updatedAt": "2026-04-05T00:00:01Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "commandExecution",
                "title": "update files",
                "toolName": "bash",
                "callId": "call_1",
                "argumentsText": "apply changes",
                "outputText": "",
                "outputFiles": [],
                "changes": [],
                "exitCode": 0,
            }
        ],
    }
    git_service = _RecordingGitDiffService(
        diff_for_paths="",
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

    query_service = _run_hydration(snapshot=snapshot, git_service=git_service)

    assert len(query_service.persist_calls) == 1
    updated_snapshot, _events = query_service.persist_calls[0]
    synthetic_item = next(
        item for item in updated_snapshot["items"]
        if str(item.get("id") or "") == "turn:exec_turn_1:hydrated-file-change"
    )
    changes = synthetic_item.get("changes") if isinstance(synthetic_item.get("changes"), list) else []
    assert len(changes) == 1
    assert changes[0]["path"] == "src/app.ts"
    assert "after" in str(changes[0].get("diff") or "")
    assert all(".planningtree" not in str(change.get("path") or "") for change in changes)


def test_finish_task_hydrate_replaces_file_change_changes_with_per_file_diff() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    render_path = rf"{workspace_root}\src\render.js"
    snapshot = {
        "threadId": "thread-exec-1",
        "items": [
            {
                "id": "file_1",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": "exec_turn_1",
                "sequence": 1,
                "createdAt": "2026-04-05T00:00:01Z",
                "updatedAt": "2026-04-05T00:00:01Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "fileChange",
                "title": "File changes",
                "toolName": None,
                "callId": None,
                "argumentsText": None,
                "outputText": "",
                "outputFiles": [{"path": render_path, "changeType": "updated", "summary": None}],
                "changes": [{"path": render_path, "kind": "modify", "summary": None, "diff": None}],
                "exitCode": None,
            }
        ],
    }
    git_service = _RecordingGitDiffService(
        diff_for_paths=(
            "diff --git a/src/render.js b/src/render.js\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        ),
        full_diff="",
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        git_service=git_service,
        workspace_root=workspace_root,
    )

    assert len(git_service.calls) == 1
    assert git_service.calls[0]["kind"] == "paths"
    assert git_service.calls[0]["paths"] == [render_path]
    assert len(query_service.persist_calls) == 1
    updated_snapshot, _events = query_service.persist_calls[0]
    updated_item = updated_snapshot["items"][0]
    changes = updated_item.get("changes") if isinstance(updated_item.get("changes"), list) else []
    assert len(changes) == 1
    assert "new" in str(changes[0].get("diff") or "")
    output_files = updated_item.get("outputFiles") if isinstance(updated_item.get("outputFiles"), list) else []
    assert len(output_files) == 1
    assert "new" in str(output_files[0].get("diff") or "")


def test_finish_task_hydrate_treats_explicit_empty_changes_as_authoritative() -> None:
    workspace_root = r"C:\Users\Thong\Tic tac toe"
    render_path = rf"{workspace_root}\src\render.js"
    snapshot = {
        "threadId": "thread-exec-1",
        "items": [
            {
                "id": "file_1",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": "exec_turn_1",
                "sequence": 1,
                "createdAt": "2026-04-05T00:00:01Z",
                "updatedAt": "2026-04-05T00:00:01Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "fileChange",
                "title": "File changes",
                "toolName": None,
                "callId": None,
                "argumentsText": None,
                "outputText": "",
                "outputFiles": [{"path": render_path, "changeType": "updated", "summary": None}],
                "changes": [],
                "exitCode": None,
            }
        ],
    }
    git_service = _RecordingGitDiffService(
        diff_for_paths="diff --git a/src/render.js b/src/render.js\n@@ -1 +1 @@\n-old\n+new\n",
        full_diff="diff --git a/src/render.js b/src/render.js\n@@ -1 +1 @@\n-old\n+new\n",
    )

    query_service = _run_hydration(
        snapshot=snapshot,
        git_service=git_service,
        workspace_root=workspace_root,
    )

    assert git_service.calls == []
    assert query_service.persist_calls == []
