from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.business.workflow_v2.legacy_transcript_migrator import LegacyTranscriptMigratorV2
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.config.app_config import build_app_paths
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2
from backend.session_core_v2.thread_store import ThreadMetadataStore, ThreadRolloutRecorder
from backend.storage.storage import Storage


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate legacy PlanningTree thread history into native Session Core V2 rollout JSONL."
    )
    parser.add_argument("--data-root", type=Path, default=None, help="PlanningTree data root. Defaults to app config.")
    parser.add_argument("--dry-run", action="store_true", help="Plan and validate migration without writing files.")
    parser.add_argument("--force", action="store_true", help="Re-run migration even when marker or valid rollout exists.")
    parser.add_argument("--project-id", default=None, help="Only migrate candidates for this project id.")
    parser.add_argument("--thread-id", default=None, help="Only migrate this thread id.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of candidates to process.")
    args = parser.parse_args()

    paths = build_app_paths(args.data_root)
    storage = Storage(paths)
    workflow_repository = WorkflowStateRepositoryV2(storage)
    runtime_store = RuntimeStoreV2(db_path=paths.data_root / "session_core_v2.sqlite3")
    native_root = paths.data_root / "session_core_v2"
    metadata_store = ThreadMetadataStore(
        db_path=native_root / "thread_metadata.sqlite3",
        rollout_root=native_root / "rollouts",
    )
    rollout_recorder = ThreadRolloutRecorder(metadata_store=metadata_store)

    migrator = LegacyTranscriptMigratorV2(
        storage=storage,
        workflow_repository=workflow_repository,
        snapshot_store_v2=storage.thread_snapshot_store_v2,
        snapshot_store_v3=storage.thread_snapshot_store_v3,
        runtime_store=runtime_store,
        thread_rollout_recorder=rollout_recorder,
        dry_run=args.dry_run,
        force=args.force,
        project_id_filter=args.project_id,
        thread_id_filter=args.thread_id,
        limit=args.limit,
    )
    summary = migrator.migrate_all()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if summary.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
