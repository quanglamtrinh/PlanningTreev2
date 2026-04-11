from __future__ import annotations

from pathlib import Path

from backend.conversation.domain.types import default_thread_snapshot
from backend.services.project_service import ProjectService
from backend.storage.file_utils import ensure_dir
from backend.tools.migrate_conversation_v2_to_v3 import MigrationOptions, run_migration


def _attach_project(storage, workspace_root: Path) -> str:
    payload = ProjectService(storage).attach_project_folder(str(workspace_root))
    return str(payload["project"]["id"])


def _write_v2_snapshot(storage, project_id: str, node_id: str, thread_role: str) -> None:
    snapshot = default_thread_snapshot(project_id, node_id, thread_role)  # type: ignore[arg-type]
    snapshot["threadId"] = f"{thread_role}-thread-{node_id}"
    snapshot["snapshotVersion"] = 5
    snapshot["items"] = [
        {
            "id": f"msg-{node_id}",
            "kind": "message",
            "threadId": str(snapshot.get("threadId") or ""),
            "turnId": "turn-1",
            "sequence": 1,
            "createdAt": "2026-04-10T00:00:00Z",
            "updatedAt": "2026-04-10T00:00:00Z",
            "status": "completed",
            "source": "upstream",
            "tone": "neutral",
            "metadata": {},
            "role": "assistant",
            "text": "legacy v2 snapshot",
            "format": "markdown",
        }
    ]
    storage.thread_snapshot_store_v2.write_snapshot(project_id, node_id, thread_role, snapshot)  # type: ignore[arg-type]


def test_migration_dry_run_does_not_write_v3(storage, workspace_root) -> None:
    project_id = _attach_project(storage, workspace_root)
    _write_v2_snapshot(storage, project_id, "node-1", "execution")

    report = run_migration(
        storage,
        options=MigrationOptions(
            all_projects=True,
            dry_run=True,
        ),
    )

    assert report["mode"] == "dry-run"
    assert report["totals"]["migrated"] == 1
    assert report["totals"]["failed"] == 0
    assert report["checksum"]["target_count"] == report["totals"]["scanned"]
    assert storage.thread_snapshot_store_v3.exists(project_id, "node-1", "execution") is False


def test_migration_apply_writes_canonical_v3_and_never_backwrites_v2(storage, workspace_root) -> None:
    project_id = _attach_project(storage, workspace_root)
    _write_v2_snapshot(storage, project_id, "node-1", "execution")

    def _forbidden_write(*args, **kwargs):
        raise AssertionError("V2 write should not be used by batch migration.")

    storage.thread_snapshot_store_v2.write_snapshot = _forbidden_write  # type: ignore[method-assign]

    report = run_migration(
        storage,
        options=MigrationOptions(
            all_projects=True,
            dry_run=False,
        ),
    )

    migrated = storage.thread_snapshot_store_v3.read_snapshot(project_id, "node-1", "execution")
    assert report["mode"] == "apply"
    assert report["totals"]["migrated"] == 1
    assert migrated["threadRole"] == "execution"
    assert "lane" not in migrated


def test_migration_is_idempotent_on_rerun(storage, workspace_root) -> None:
    project_id = _attach_project(storage, workspace_root)
    _write_v2_snapshot(storage, project_id, "node-1", "execution")

    first = run_migration(
        storage,
        options=MigrationOptions(
            all_projects=True,
        ),
    )
    second = run_migration(
        storage,
        options=MigrationOptions(
            all_projects=True,
        ),
    )

    assert first["totals"]["migrated"] == 1
    assert first["totals"]["failed"] == 0
    assert second["totals"]["migrated"] == 0
    assert second["totals"]["skip_existing"] == 1
    assert second["totals"]["failed"] == 0


def test_migration_marks_skip_missing_v2_for_explicit_filtered_target(storage, workspace_root) -> None:
    _attach_project(storage, workspace_root)

    report = run_migration(
        storage,
        options=MigrationOptions(
            all_projects=True,
            node_ids=("missing-node",),
            thread_roles=("execution",),
        ),
    )

    assert report["totals"]["scanned"] == 1
    assert report["totals"]["skip_missing_v2"] == 1
    assert report["totals"]["failed"] == 0


def test_migration_isolates_failures_and_continues(storage, workspace_root) -> None:
    project_id = _attach_project(storage, workspace_root)
    _write_v2_snapshot(storage, project_id, "good-node", "execution")

    malformed_path = storage.thread_snapshot_store_v2.path(project_id, "bad-node", "execution")
    ensure_dir(malformed_path.parent)
    malformed_path.write_text("{malformed-json", encoding="utf-8")

    report = run_migration(
        storage,
        options=MigrationOptions(
            all_projects=True,
        ),
    )

    assert report["totals"]["scanned"] == 2
    assert report["totals"]["migrated"] == 1
    assert report["totals"]["failed"] == 1
    assert storage.thread_snapshot_store_v3.exists(project_id, "good-node", "execution") is True
    assert len(report["errors"]) == 1
    assert report["errors"][0]["node_id"] == "bad-node"
    assert report["errors"][0]["thread_role"] == "execution"


def test_migration_stops_when_fail_fast_threshold_exceeded(storage, workspace_root) -> None:
    project_id = _attach_project(storage, workspace_root)
    _write_v2_snapshot(storage, project_id, "z-good-node", "execution")

    malformed_path = storage.thread_snapshot_store_v2.path(project_id, "a-bad-node", "execution")
    ensure_dir(malformed_path.parent)
    malformed_path.write_text("{malformed-json", encoding="utf-8")

    report = run_migration(
        storage,
        options=MigrationOptions(
            all_projects=True,
            fail_fast_threshold=0,
        ),
    )

    assert report["stopped_early"] is True
    assert report["totals"]["scanned"] == 1
    assert report["totals"]["failed"] == 1
    assert report["totals"]["migrated"] == 0
    assert storage.thread_snapshot_store_v3.exists(project_id, "z-good-node", "execution") is False

