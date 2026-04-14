from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.project_service import ProjectService


def _project_node(storage, workspace_root: Path) -> tuple[str, str]:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    root_snapshot = storage.project_store.load_snapshot(project_id)
    node_id = root_snapshot["tree_state"]["root_node_id"]
    return project_id, node_id


def test_thread_mini_journal_store_v3_append_read_prune(storage, workspace_root) -> None:
    project_id, node_id = _project_node(storage, workspace_root)
    store = storage.thread_mini_journal_store_v3

    first = store.append_boundary_record(
        project_id,
        node_id,
        "execution",
        {
            "journalSeq": 1,
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "threadId": "execution-thread-1",
            "turnId": "turn-1",
            "eventIdStart": 10,
            "eventIdEnd": 12,
            "boundaryType": "waiting_user_input",
            "snapshotVersionAtWrite": 5,
            "createdAt": "2026-04-12T00:00:00Z",
        },
    )
    second = store.append_boundary_record(
        project_id,
        node_id,
        "execution",
        {
            "journalSeq": 2,
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "threadId": "execution-thread-1",
            "turnId": "turn-1",
            "eventIdStart": 13,
            "eventIdEnd": 14,
            "boundaryType": "turn_completed",
            "snapshotVersionAtWrite": 6,
            "createdAt": "2026-04-12T00:00:01Z",
        },
    )

    assert first["journalSeq"] == 1
    assert second["journalSeq"] == 2

    tail = store.read_tail_after(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=1,
    )
    assert len(tail) == 1
    assert tail[0]["journalSeq"] == 2

    removed = store.prune_before(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=1,
    )
    assert removed == 1
    remaining = store.read_tail_after(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=0,
    )
    assert [record["journalSeq"] for record in remaining] == [2]


def test_thread_mini_journal_store_v3_rejects_invalid_boundary(storage, workspace_root) -> None:
    project_id, node_id = _project_node(storage, workspace_root)
    store = storage.thread_mini_journal_store_v3

    with pytest.raises(ValueError):
        store.append_boundary_record(
            project_id,
            node_id,
            "execution",
            {
                "journalSeq": 1,
                "projectId": project_id,
                "nodeId": node_id,
                "threadRole": "execution",
                "threadId": "execution-thread-1",
                "turnId": "turn-1",
                "eventIdStart": 1,
                "eventIdEnd": 1,
                "boundaryType": "not_allowed",
                "snapshotVersionAtWrite": 1,
                "createdAt": "2026-04-12T00:00:00Z",
            },
        )
