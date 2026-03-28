from __future__ import annotations

from pathlib import Path

from backend.conversation.services.system_message_writer import ConversationSystemMessageWriter
from backend.services.project_service import ProjectService


def _create_project(storage, workspace_root: str) -> tuple[str, str]:
    snapshot = ProjectService(storage).attach_project_folder(workspace_root)
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


class _FakeRuntimeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upsert_system_message(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"ok": True, "delegated": True}


def test_system_message_writer_delegates_to_runtime_service(storage) -> None:
    runtime = _FakeRuntimeService()
    writer = ConversationSystemMessageWriter(storage, runtime_service=runtime)

    result = writer.upsert_system_message(
        project_id="project-1",
        node_id="node-1",
        thread_role="audit",
        item_id="audit-record:frame",
        turn_id=None,
        text="Canonical confirmed frame snapshot",
    )

    assert result == {"ok": True, "delegated": True}
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["project_id"] == "project-1"
    assert runtime.calls[0]["node_id"] == "node-1"
    assert runtime.calls[0]["thread_role"] == "audit"
    assert runtime.calls[0]["item_id"] == "audit-record:frame"
    assert runtime.calls[0]["text"] == "Canonical confirmed frame snapshot"


def test_system_message_writer_fallback_writes_v2_snapshot_item(
    storage,
    workspace_root: Path,
) -> None:
    project_id, node_id = _create_project(storage, str(workspace_root))
    session = storage.chat_state_store.read_session(project_id, node_id, thread_role="audit")
    session["thread_id"] = "audit-thread-1"
    storage.chat_state_store.write_session(project_id, node_id, session, thread_role="audit")

    writer = ConversationSystemMessageWriter(storage)
    writer.upsert_system_message(
        project_id=project_id,
        node_id=node_id,
        thread_role="audit",
        item_id="audit-record:frame",
        turn_id=None,
        text="Canonical confirmed frame snapshot",
    )

    snapshot = storage.thread_snapshot_store_v2.read_snapshot(project_id, node_id, "audit")
    item = next(item for item in snapshot["items"] if item["id"] == "audit-record:frame")

    assert item["kind"] == "message"
    assert item["role"] == "system"
    assert item["threadId"] == "audit-thread-1"
    assert item["text"] == "Canonical confirmed frame snapshot"
