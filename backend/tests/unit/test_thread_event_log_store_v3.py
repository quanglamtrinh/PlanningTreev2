from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.project_service import ProjectService


def _project_node(storage, workspace_root: Path) -> tuple[str, str]:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    root_snapshot = storage.project_store.load_snapshot(project_id)
    node_id = root_snapshot["tree_state"]["root_node_id"]
    return project_id, node_id


def test_thread_event_log_store_v3_append_read_prune(storage, workspace_root) -> None:
    project_id, node_id = _project_node(storage, workspace_root)
    store = storage.thread_event_log_store_v3

    first = store.append_event_record(
        project_id,
        node_id,
        "execution",
        {
            "logSeq": 1,
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "threadId": "execution-thread-1",
            "eventId": 11,
            "snapshotVersionAtAppend": 3,
            "payload": {
                "event_id": "11",
                "event_type": "conversation.item.upsert.v3",
                "payload": {"item": {"id": "msg-1"}},
            },
            "createdAt": "2026-04-12T00:00:00Z",
        },
    )
    second = store.append_event_record(
        project_id,
        node_id,
        "execution",
        {
            "logSeq": 2,
            "projectId": project_id,
            "nodeId": node_id,
            "threadRole": "execution",
            "threadId": "execution-thread-1",
            "eventId": 12,
            "snapshotVersionAtAppend": 4,
            "payload": {
                "event_id": "12",
                "event_type": "conversation.item.patch.v3",
                "payload": {"itemId": "msg-1", "patch": {"kind": "message"}},
            },
            "createdAt": "2026-04-12T00:00:01Z",
        },
    )

    assert first["logSeq"] == 1
    assert second["logSeq"] == 2

    by_seq = store.read_tail_after_log_seq(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=1,
    )
    assert [record["logSeq"] for record in by_seq] == [2]

    by_snapshot = store.read_tail_after_snapshot_version(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        snapshot_version=3,
    )
    assert [record["eventId"] for record in by_snapshot] == [12]

    assert store.count_entries(project_id, node_id, "execution", thread_id="execution-thread-1") == 2

    removed = store.prune_before_event_id(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        event_id=11,
    )
    assert removed == 1

    remaining = store.read_tail_after_log_seq(
        project_id,
        node_id,
        "execution",
        thread_id="execution-thread-1",
        cursor=0,
    )
    assert [record["eventId"] for record in remaining] == [12]


def test_thread_event_log_store_v3_rejects_invalid_payload(storage, workspace_root) -> None:
    project_id, node_id = _project_node(storage, workspace_root)
    store = storage.thread_event_log_store_v3

    with pytest.raises(ValueError):
        store.append_event_record(
            project_id,
            node_id,
            "execution",
            {
                "logSeq": 1,
                "projectId": project_id,
                "nodeId": node_id,
                "threadRole": "execution",
                "threadId": "execution-thread-1",
                "eventId": 1,
                "snapshotVersionAtAppend": 1,
                "payload": "invalid",
                "createdAt": "2026-04-12T00:00:00Z",
            },
        )
