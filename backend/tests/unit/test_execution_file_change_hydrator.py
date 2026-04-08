from __future__ import annotations

from typing import Any

from backend.services.execution_file_change_hydrator import ExecutionFileChangeHydrator


class _FakeDiffSource:
    mode = "worktree_range"

    def __init__(self, *, full_diff: str, path_diff: str = "") -> None:
        self._full_diff = full_diff
        self._path_diff = path_diff
        self.path_calls: list[list[str]] = []
        self.full_calls = 0

    def get_diff_for_paths(self, paths: list[str]) -> str:
        self.path_calls.append(list(paths))
        return self._path_diff

    def get_full_diff(self) -> str:
        self.full_calls += 1
        return self._full_diff


def _command_only_snapshot(turn_id: str) -> dict[str, Any]:
    return {
        "threadId": "thread-exec-1",
        "items": [
            {
                "id": "cmd_1",
                "kind": "tool",
                "threadId": "thread-exec-1",
                "turnId": turn_id,
                "sequence": 1,
                "createdAt": "2026-04-05T00:00:01Z",
                "updatedAt": "2026-04-05T00:00:01Z",
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "commandExecution",
                "title": "write file",
                "toolName": "bash",
                "callId": "call_1",
                "argumentsText": "echo hello > src/app.txt",
                "outputText": "",
                "outputFiles": [],
                "changes": [],
                "exitCode": 0,
            }
        ],
    }


def _extract_synthetic_item(snapshot: dict[str, Any], turn_id: str) -> dict[str, Any]:
    synthetic_id = f"turn:{turn_id}:hydrated-file-change"
    return next(
        item
        for item in snapshot.get("items", [])
        if isinstance(item, dict) and str(item.get("id") or "") == synthetic_id
    )


def test_refresh_synthetic_from_full_diff_updates_existing_synthetic_item() -> None:
    turn_id = "exec_turn_1"
    hydrator = ExecutionFileChangeHydrator()
    first_source = _FakeDiffSource(
        full_diff=(
            "diff --git a/src/app.txt b/src/app.txt\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
        )
    )
    second_source = _FakeDiffSource(
        full_diff=(
            "diff --git a/src/app.txt b/src/app.txt\n"
            "@@ -0,0 +1 @@\n"
            "+world\n"
        )
    )

    first_snapshot, first_events, _ = hydrator.hydrate_turn_snapshot(
        snapshot=_command_only_snapshot(turn_id),
        turn_id=turn_id,
        diff_source=first_source,
        hydrated_by="test_live_hydrate",
        project_id="project-1",
        node_id="node-1",
        refresh_synthetic_from_full_diff=True,
    )
    assert first_events
    first_item = _extract_synthetic_item(first_snapshot, turn_id)
    first_changes = first_item.get("changes") if isinstance(first_item.get("changes"), list) else []
    assert len(first_changes) == 1
    assert "hello" in str(first_changes[0].get("diff") or "")

    second_snapshot, second_events, _ = hydrator.hydrate_turn_snapshot(
        snapshot=first_snapshot,
        turn_id=turn_id,
        diff_source=second_source,
        hydrated_by="test_live_hydrate",
        project_id="project-1",
        node_id="node-1",
        refresh_synthetic_from_full_diff=True,
    )
    assert second_events
    second_item = _extract_synthetic_item(second_snapshot, turn_id)
    second_changes = second_item.get("changes") if isinstance(second_item.get("changes"), list) else []
    assert len(second_changes) == 1
    assert "world" in str(second_changes[0].get("diff") or "")
    assert "hello" not in str(second_changes[0].get("diff") or "")


def test_without_refresh_synthetic_flag_existing_synthetic_item_is_authoritative() -> None:
    turn_id = "exec_turn_1"
    hydrator = ExecutionFileChangeHydrator()
    first_source = _FakeDiffSource(
        full_diff=(
            "diff --git a/src/app.txt b/src/app.txt\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
        )
    )
    second_source = _FakeDiffSource(
        full_diff=(
            "diff --git a/src/app.txt b/src/app.txt\n"
            "@@ -0,0 +1 @@\n"
            "+world\n"
        )
    )

    first_snapshot, first_events, _ = hydrator.hydrate_turn_snapshot(
        snapshot=_command_only_snapshot(turn_id),
        turn_id=turn_id,
        diff_source=first_source,
        hydrated_by="test_no_refresh",
        project_id="project-1",
        node_id="node-1",
    )
    assert first_events

    second_snapshot, second_events, _ = hydrator.hydrate_turn_snapshot(
        snapshot=first_snapshot,
        turn_id=turn_id,
        diff_source=second_source,
        hydrated_by="test_no_refresh",
        project_id="project-1",
        node_id="node-1",
    )
    assert second_events == []
    second_item = _extract_synthetic_item(second_snapshot, turn_id)
    second_changes = second_item.get("changes") if isinstance(second_item.get("changes"), list) else []
    assert len(second_changes) == 1
    assert "hello" in str(second_changes[0].get("diff") or "")

