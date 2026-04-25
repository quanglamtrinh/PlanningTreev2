from __future__ import annotations

import tempfile
from pathlib import Path

from backend.business.workflow_v2.legacy_transcript_migrator import LegacyTranscriptMigratorV2
from backend.business.workflow_v2.models import NodeWorkflowStateV2, ThreadBinding
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2


class _WorkspaceStoreStub:
    def __init__(self, project_id: str, folder_path: str) -> None:
        self._entries = [{"project_id": project_id, "folder_path": folder_path}]

    def list_entries(self) -> list[dict[str, str]]:
        return list(self._entries)


class _StorageStub:
    def __init__(self, project_id: str, folder_path: str) -> None:
        self.workspace_store = _WorkspaceStoreStub(project_id, folder_path)


class _WorkflowRepositoryStub:
    def __init__(self, state: NodeWorkflowStateV2) -> None:
        self._state = state

    def read_state(self, project_id: str, node_id: str) -> NodeWorkflowStateV2:
        assert project_id == self._state.project_id
        assert node_id == self._state.node_id
        return self._state


class _SnapshotStoreStub:
    def __init__(self, snapshot: dict[str, object]) -> None:
        self._snapshot = snapshot

    def exists(self, project_id: str, node_id: str, thread_role: str) -> bool:
        del project_id, node_id, thread_role
        return True

    def read_snapshot(self, project_id: str, node_id: str, thread_role: str) -> dict[str, object]:
        del project_id, node_id, thread_role
        return dict(self._snapshot)


def test_legacy_transcript_migrator_imports_snapshot_into_native_journal_and_marks_thread() -> None:
    with tempfile.TemporaryDirectory(prefix="legacy-migrator-") as tmp:
        root = Path(tmp)
        workflow_dir = root / ".planningtree" / "workflow_core_v2"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        (workflow_dir / "node-1.json").write_text("{}", encoding="utf-8")

        state = NodeWorkflowStateV2(
            project_id="project-1",
            node_id="node-1",
            thread_bindings={
                "execution": ThreadBinding(
                    projectId="project-1",
                    nodeId="node-1",
                    role="execution",
                    threadId="thread-legacy-1",
                    createdFrom="legacy_adopted",
                )
            },
            execution_thread_id="thread-legacy-1",
        )
        snapshot = {
            "projectId": "project-1",
            "nodeId": "node-1",
            "threadRole": "execution",
            "threadId": "thread-legacy-1",
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

        runtime_store = RuntimeStoreV2()
        migrator = LegacyTranscriptMigratorV2(
            storage=_StorageStub("project-1", str(root)),  # type: ignore[arg-type]
            workflow_repository=_WorkflowRepositoryStub(state),  # type: ignore[arg-type]
            snapshot_store=_SnapshotStoreStub(snapshot),  # type: ignore[arg-type]
            runtime_store=runtime_store,
        )

        summary = migrator.migrate_all()
        assert summary["candidates"] == 1
        assert summary["migrated"] == 1
        assert summary["failed"] == 0
        assert runtime_store.has_legacy_migration_marker(thread_id="thread-legacy-1") is True

        journal = runtime_store.read_thread_journal("thread-legacy-1")
        methods = [str(event.get("method") or "") for event in journal]
        assert "turn/started" in methods
        assert "item/completed" in methods
        assert "turn/completed" in methods
        item_events = [event for event in journal if str(event.get("method") or "") == "item/completed"]
        assert item_events
        migrated_payload = item_events[0]["params"]["item"]
        assert migrated_payload["metadata"]["legacyMigrated"] is True
        assert migrated_payload["kind"] == "agentMessage"
