from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.business.workflow_v2.legacy_transcript_migrator import LegacyTranscriptMigratorV2
from backend.business.workflow_v2.models import NodeWorkflowStateV2, ThreadBinding
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2
from backend.session_core_v2.thread_store import ThreadMetadataStore, ThreadRolloutRecorder, read_native_thread


class _WorkspaceStoreStub:
    def __init__(self, project_id: str, folder_path: str) -> None:
        self._entries = [{"project_id": project_id, "folder_path": folder_path}]

    def list_entries(self) -> list[dict[str, str]]:
        return list(self._entries)


class _StorageStub:
    def __init__(self, project_id: str, folder_path: str, *, chat_state_store: object | None = None) -> None:
        self.workspace_store = _WorkspaceStoreStub(project_id, folder_path)
        if chat_state_store is not None:
            self.chat_state_store = chat_state_store


class _WorkflowRepositoryStub:
    def __init__(self, state: NodeWorkflowStateV2) -> None:
        self._state = state

    def read_state(self, project_id: str, node_id: str) -> NodeWorkflowStateV2:
        assert project_id == self._state.project_id
        assert node_id == self._state.node_id
        return self._state


class _SnapshotStoreStub:
    def __init__(self, snapshot: dict[str, object], *, exists: bool = True) -> None:
        self._snapshot = snapshot
        self._exists = exists

    def exists(self, project_id: str, node_id: str, thread_role: str) -> bool:
        del project_id, node_id, thread_role
        return self._exists

    def read_snapshot(self, project_id: str, node_id: str, thread_role: str) -> dict[str, object]:
        del project_id, node_id, thread_role
        return dict(self._snapshot)


class _FailingSnapshotStoreStub(_SnapshotStoreStub):
    def read_snapshot(self, project_id: str, node_id: str, thread_role: str) -> dict[str, object]:
        del project_id, node_id, thread_role
        raise ValueError("malformed legacy snapshot")


class _ChatStateStoreStub:
    def __init__(self, session: dict[str, object]) -> None:
        self._session = session

    def read_session(self, project_id: str, node_id: str, thread_role: str) -> dict[str, object]:
        del project_id, node_id, thread_role
        return dict(self._session)


def _state(thread_id: str = "thread-legacy-1") -> NodeWorkflowStateV2:
    return NodeWorkflowStateV2(
        project_id="project-1",
        node_id="node-1",
        thread_bindings={
            "execution": ThreadBinding(
                projectId="project-1",
                nodeId="node-1",
                role="execution",
                threadId=thread_id,
                createdFrom="legacy_adopted",
            )
        },
        execution_thread_id=thread_id,
    )


def _snapshot(thread_id: str = "thread-legacy-1") -> dict[str, Any]:
    return {
        "projectId": "project-1",
        "nodeId": "node-1",
        "threadRole": "execution",
        "threadId": thread_id,
        "activeTurnId": "turn-legacy-1",
        "processingState": "idle",
        "snapshotVersion": 3,
        "items": [
            {
                "id": "legacy-item-1",
                "kind": "message",
                "role": "assistant",
                "text": "hello from legacy",
                "turnId": "turn-legacy-1",
                "status": "completed",
                "sequence": 1,
                "createdAt": "2026-04-01T00:00:00Z",
                "updatedAt": "2026-04-01T00:00:00Z",
                "metadata": {},
            }
        ],
        "pendingRequests": [],
    }


def _workspace(root: Path) -> None:
    workflow_dir = root / ".planningtree" / "workflow_core_v2"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "node-1.json").write_text("{}", encoding="utf-8")


def _recorder(root: Path) -> tuple[ThreadMetadataStore, ThreadRolloutRecorder]:
    metadata = ThreadMetadataStore(db_path=root / "thread_metadata.sqlite3", rollout_root=root / "rollouts")
    return metadata, ThreadRolloutRecorder(metadata_store=metadata)


def test_legacy_transcript_migrator_imports_snapshot_into_native_rollout_and_marks_thread(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    metadata, recorder = _recorder(tmp_path / "native")
    runtime_store = RuntimeStoreV2()
    migrator = LegacyTranscriptMigratorV2(
        storage=_StorageStub("project-1", str(root)),  # type: ignore[arg-type]
        workflow_repository=_WorkflowRepositoryStub(_state()),  # type: ignore[arg-type]
        snapshot_store_v2=_SnapshotStoreStub(_snapshot()),  # type: ignore[arg-type]
        runtime_store=runtime_store,
        thread_rollout_recorder=recorder,
    )

    summary = migrator.migrate_all()
    assert summary["candidates"] == 1
    assert summary["migrated"] == 1
    assert summary["failed"] == 0
    assert summary["rolloutsCreated"] == 1
    assert runtime_store.has_legacy_migration_marker(thread_id="thread-legacy-1") is True
    assert runtime_store.read_thread_journal("thread-legacy-1") == []

    read = read_native_thread(
        metadata_store=metadata,
        rollout_recorder=recorder,
        thread_id="thread-legacy-1",
        include_history=True,
    )
    turns = read["thread"]["turns"]
    assert turns[0]["id"] == "turn-legacy-1"
    assert turns[0]["status"] == "completed"
    migrated_payload = turns[0]["items"][0]
    assert migrated_payload["metadata"]["legacyMigrated"] is True
    assert migrated_payload["kind"] == "agentMessage"
    metadata.close()


def test_legacy_transcript_migrator_prefers_v3_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    metadata, recorder = _recorder(tmp_path / "native")
    v3_snapshot = _snapshot()
    v3_snapshot["items"][0]["text"] = "from v3"
    v2_snapshot = _snapshot()
    v2_snapshot["items"][0]["text"] = "from v2"

    migrator = LegacyTranscriptMigratorV2(
        storage=_StorageStub("project-1", str(root)),  # type: ignore[arg-type]
        workflow_repository=_WorkflowRepositoryStub(_state()),  # type: ignore[arg-type]
        snapshot_store_v2=_SnapshotStoreStub(v2_snapshot),  # type: ignore[arg-type]
        snapshot_store_v3=_SnapshotStoreStub(v3_snapshot),  # type: ignore[arg-type]
        runtime_store=RuntimeStoreV2(),
        thread_rollout_recorder=recorder,
    )

    assert migrator.migrate_all()["migrated"] == 1
    turns = read_native_thread(
        metadata_store=metadata,
        rollout_recorder=recorder,
        thread_id="thread-legacy-1",
        include_history=True,
    )["thread"]["turns"]
    assert turns[0]["items"][0]["text"] == "from v3"
    metadata.close()


def test_legacy_transcript_migrator_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    metadata, recorder = _recorder(tmp_path / "native")
    runtime_store = RuntimeStoreV2()
    migrator = LegacyTranscriptMigratorV2(
        storage=_StorageStub("project-1", str(root)),  # type: ignore[arg-type]
        workflow_repository=_WorkflowRepositoryStub(_state()),  # type: ignore[arg-type]
        snapshot_store_v2=_SnapshotStoreStub(_snapshot()),  # type: ignore[arg-type]
        runtime_store=runtime_store,
        thread_rollout_recorder=recorder,
        dry_run=True,
    )

    summary = migrator.migrate_all()
    assert summary["dryRun"] is True
    assert summary["migrated"] == 1
    assert runtime_store.has_legacy_migration_marker(thread_id="thread-legacy-1") is False
    assert recorder.metadata_store.get("thread-legacy-1") is None
    metadata.close()


def test_legacy_transcript_migrator_second_run_does_not_duplicate_rollout_items(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    metadata, recorder = _recorder(tmp_path / "native")
    runtime_store = RuntimeStoreV2()
    kwargs = {
        "storage": _StorageStub("project-1", str(root)),  # type: ignore[arg-type]
        "workflow_repository": _WorkflowRepositoryStub(_state()),  # type: ignore[arg-type]
        "snapshot_store_v2": _SnapshotStoreStub(_snapshot()),  # type: ignore[arg-type]
        "runtime_store": runtime_store,
        "thread_rollout_recorder": recorder,
    }

    first = LegacyTranscriptMigratorV2(**kwargs)
    assert first.migrate_all()["migrated"] == 1
    initial_count = len(recorder.load_items("thread-legacy-1"))

    second = LegacyTranscriptMigratorV2(**kwargs)
    summary = second.migrate_all()
    assert summary["migrated"] == 0
    assert summary["skipped"] == 1
    assert len(recorder.load_items("thread-legacy-1")) == initial_count
    metadata.close()


def test_legacy_transcript_migrator_imports_runtime_journal_into_rollout(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    metadata, recorder = _recorder(tmp_path / "native")
    runtime_store = RuntimeStoreV2()
    runtime_store.append_notification(
        method="turn/completed",
        params={"threadId": "thread-legacy-1", "turn": {"id": "turn-runtime-1", "status": "completed"}},
        thread_id_override="thread-legacy-1",
    )
    migrator = LegacyTranscriptMigratorV2(
        storage=_StorageStub("project-1", str(root)),  # type: ignore[arg-type]
        workflow_repository=_WorkflowRepositoryStub(_state()),  # type: ignore[arg-type]
        snapshot_store_v2=_SnapshotStoreStub(_snapshot(), exists=False),  # type: ignore[arg-type]
        runtime_store=runtime_store,
        thread_rollout_recorder=recorder,
    )

    assert migrator.migrate_all()["migrated"] == 1
    turns = read_native_thread(
        metadata_store=metadata,
        rollout_recorder=recorder,
        thread_id="thread-legacy-1",
        include_history=True,
    )["thread"]["turns"]
    assert turns[0]["id"] == "turn-runtime-1"
    assert turns[0]["status"] == "completed"
    metadata.close()


def test_legacy_transcript_migrator_imports_legacy_chat_session_into_rollout(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    metadata, recorder = _recorder(tmp_path / "native")
    chat_store = _ChatStateStoreStub(
        {
            "thread_id": "thread-legacy-1",
            "active_turn_id": "turn-chat-1",
            "messages": [
                {
                    "message_id": "message-1",
                    "role": "user",
                    "content": "legacy user",
                    "status": "completed",
                    "turn_id": "turn-chat-1",
                },
                {
                    "message_id": "message-2",
                    "role": "assistant",
                    "content": "legacy assistant",
                    "status": "completed",
                    "turn_id": "turn-chat-1",
                },
            ],
        }
    )
    migrator = LegacyTranscriptMigratorV2(
        storage=_StorageStub("project-1", str(root), chat_state_store=chat_store),  # type: ignore[arg-type]
        workflow_repository=_WorkflowRepositoryStub(_state()),  # type: ignore[arg-type]
        snapshot_store_v2=_SnapshotStoreStub(_snapshot(), exists=False),  # type: ignore[arg-type]
        runtime_store=RuntimeStoreV2(),
        thread_rollout_recorder=recorder,
    )

    assert migrator.migrate_all()["migrated"] == 1
    turns = read_native_thread(
        metadata_store=metadata,
        rollout_recorder=recorder,
        thread_id="thread-legacy-1",
        include_history=True,
    )["thread"]["turns"]
    assert [item["type"] for item in turns[0]["items"]] == ["userMessage", "agentMessage"]
    assert turns[0]["items"][1]["text"] == "legacy assistant"
    metadata.close()


def test_legacy_transcript_migrator_reports_malformed_snapshot_without_rollout_corruption(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    metadata, recorder = _recorder(tmp_path / "native")
    migrator = LegacyTranscriptMigratorV2(
        storage=_StorageStub("project-1", str(root)),  # type: ignore[arg-type]
        workflow_repository=_WorkflowRepositoryStub(_state()),  # type: ignore[arg-type]
        snapshot_store_v2=_FailingSnapshotStoreStub(_snapshot()),  # type: ignore[arg-type]
        runtime_store=RuntimeStoreV2(),
        thread_rollout_recorder=recorder,
    )

    summary = migrator.migrate_all()
    assert summary["migrated"] == 0
    assert summary["failed"] == 1
    assert "malformed legacy snapshot" in summary["failures"][0]["error"]
    assert metadata.get("thread-legacy-1") is None
    metadata.close()
