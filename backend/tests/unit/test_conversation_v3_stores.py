from __future__ import annotations

from backend.conversation.domain.types_v3 import (
    default_thread_snapshot_v3,
    normalize_thread_snapshot_v3,
)
from backend.services.project_service import ProjectService
from backend.storage.file_utils import load_json


def test_thread_snapshot_store_v3_read_missing_returns_default(storage, workspace_root) -> None:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]

    snapshot = storage.thread_snapshot_store_v3.read_snapshot(project_id, "node-1", "ask_planning")

    assert snapshot["projectId"] == project_id
    assert snapshot["nodeId"] == "node-1"
    assert snapshot["threadRole"] == "ask_planning"
    assert snapshot["snapshotVersion"] == 0
    assert snapshot["items"] == []
    assert "lane" not in snapshot


def test_thread_snapshot_store_v3_roundtrip_persists_canonical_thread_role(storage, workspace_root) -> None:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    snapshot = default_thread_snapshot_v3(project_id, "node-1", "execution")
    snapshot["threadId"] = "exec-thread-1"
    snapshot["snapshotVersion"] = 7

    written = storage.thread_snapshot_store_v3.write_snapshot(project_id, "node-1", "execution", snapshot)
    loaded = storage.thread_snapshot_store_v3.read_snapshot(project_id, "node-1", "execution")
    raw_payload = load_json(storage.thread_snapshot_store_v3.path(project_id, "node-1", "execution"), default={})

    assert written["threadRole"] == "execution"
    assert loaded["threadRole"] == "execution"
    assert loaded["threadId"] == "exec-thread-1"
    assert loaded["snapshotVersion"] == 7
    assert storage.thread_snapshot_store_v3.path(project_id, "node-1", "execution").exists()
    assert "lane" not in loaded
    assert isinstance(raw_payload, dict)
    assert raw_payload.get("threadRole") == "execution"
    assert "lane" not in raw_payload


def test_thread_snapshot_store_v3_normalizes_malformed_payload_and_legacy_lane(storage, workspace_root) -> None:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]

    malformed_payload = {
        "projectId": project_id,
        "nodeId": "node-1",
        "lane": "ask",
        "threadId": " ask-thread-1 ",
        "processingState": "invalid_state",
        "snapshotVersion": -10,
        "items": [
            {"id": "msg-2", "kind": "message", "sequence": 2, "text": "world"},
            {"id": "msg-1", "kind": "message", "sequence": 1, "text": "hello"},
            {"kind": "message", "sequence": 3, "text": "missing id"},
            {"id": "bad-kind", "kind": "unknown", "sequence": 4},
        ],
        "uiSignals": {
            "planReady": {
                "planItemId": "plan-1",
                "revision": "oops",
                "ready": 1,
                "failed": 0,
            },
            "activeUserInputRequests": [
                {
                    "requestId": "req-2",
                    "itemId": "item-2",
                    "threadId": "ask-thread-1",
                    "status": "answer_submitted",
                    "createdAt": "2026-04-09T00:00:00Z",
                    "answers": [{"questionId": "q2", "value": "v2"}],
                },
                {
                    "requestId": "req-1",
                    "itemId": "item-1",
                    "threadId": "ask-thread-1",
                    "status": "requested",
                    "createdAt": "2026-04-08T00:00:00Z",
                    "answers": [{"questionId": "q1", "value": "v1"}],
                },
                {"requestId": "", "itemId": "missing-request-id"},
            ],
        },
    }

    written = storage.thread_snapshot_store_v3.write_snapshot(
        project_id,
        "node-1",
        "ask_planning",
        malformed_payload,
    )
    loaded = storage.thread_snapshot_store_v3.read_snapshot(project_id, "node-1", "ask_planning")

    assert written["threadRole"] == "ask_planning"
    assert loaded["threadRole"] == "ask_planning"
    assert loaded["threadId"] == "ask-thread-1"
    assert loaded["processingState"] == "idle"
    assert loaded["snapshotVersion"] == 0
    assert [item["id"] for item in loaded["items"]] == ["msg-1", "msg-2"]
    assert loaded["uiSignals"]["planReady"] == {
        "planItemId": "plan-1",
        "revision": 0,
        "ready": True,
        "failed": False,
    }
    assert [request["requestId"] for request in loaded["uiSignals"]["activeUserInputRequests"]] == ["req-1", "req-2"]
    assert "lane" not in loaded


def test_thread_snapshot_store_v3_clear_snapshot_resets_state(storage, workspace_root) -> None:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    snapshot = default_thread_snapshot_v3(project_id, "node-1", "execution")
    snapshot["threadId"] = "exec-thread-1"
    snapshot["snapshotVersion"] = 9
    snapshot["items"] = [
        {
            "id": "status-1",
            "kind": "status",
            "threadId": "exec-thread-1",
            "turnId": None,
            "sequence": 1,
            "createdAt": "2026-04-09T00:00:00Z",
            "updatedAt": "2026-04-09T00:00:00Z",
            "status": "completed",
            "source": "backend",
            "tone": "neutral",
            "metadata": {},
            "code": "ok",
            "label": "done",
            "detail": None,
        }
    ]
    storage.thread_snapshot_store_v3.write_snapshot(project_id, "node-1", "execution", snapshot)

    cleared = storage.thread_snapshot_store_v3.clear_snapshot(project_id, "node-1", "execution")

    assert cleared["threadRole"] == "execution"
    assert cleared["threadId"] is None
    assert cleared["snapshotVersion"] == 0
    assert cleared["items"] == []
    assert "lane" not in cleared


def test_normalize_thread_snapshot_v3_maps_lane_input_to_thread_role() -> None:
    normalized = normalize_thread_snapshot_v3(
        {
            "projectId": "project-1",
            "nodeId": "node-1",
            "lane": "ask",
            "snapshotVersion": 3,
        },
        project_id="project-1",
        node_id="node-1",
        thread_role="execution",
    )

    assert normalized["threadRole"] == "ask_planning"
    assert normalized["snapshotVersion"] == 3
    assert "lane" not in normalized
