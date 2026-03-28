from __future__ import annotations

from backend.conversation.domain.types import default_thread_registry_entry, default_thread_snapshot
from backend.services.project_service import ProjectService


def test_thread_snapshot_store_v2_roundtrip(storage, workspace_root) -> None:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    snapshot = default_thread_snapshot(project_id, "node-1", "ask_planning")
    snapshot["threadId"] = "thread-1"
    snapshot["snapshotVersion"] = 7

    written = storage.thread_snapshot_store_v2.write_snapshot(project_id, "node-1", "ask_planning", snapshot)
    loaded = storage.thread_snapshot_store_v2.read_snapshot(project_id, "node-1", "ask_planning")

    assert written["threadId"] == "thread-1"
    assert loaded["threadId"] == "thread-1"
    assert loaded["snapshotVersion"] == 7
    assert storage.thread_snapshot_store_v2.path(project_id, "node-1", "ask_planning").exists()


def test_thread_registry_store_v2_roundtrip(storage, workspace_root) -> None:
    project_id = ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]
    entry = default_thread_registry_entry(project_id, "node-1", "audit")
    entry["threadId"] = "audit-thread-1"
    entry["lineageRootThreadId"] = "root-thread-1"

    written = storage.thread_registry_store.write_entry(project_id, "node-1", "audit", entry)
    loaded = storage.thread_registry_store.read_entry(project_id, "node-1", "audit")

    assert written["threadId"] == "audit-thread-1"
    assert loaded["threadId"] == "audit-thread-1"
    assert loaded["lineageRootThreadId"] == "root-thread-1"
    assert storage.thread_registry_store.path(project_id, "node-1", "audit").exists()

