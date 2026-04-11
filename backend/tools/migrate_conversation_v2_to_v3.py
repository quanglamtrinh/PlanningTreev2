from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from backend.config.app_config import build_app_paths, get_conversation_v3_bridge_mode
from backend.conversation.domain.types_v3 import THREAD_ROLES_V3, ThreadRoleV3, normalize_thread_snapshot_v3
from backend.conversation.projector.thread_event_projector_v3 import project_v2_snapshot_to_v3
from backend.storage.file_utils import atomic_write_json, iso_now
from backend.storage.storage import Storage


@dataclass(frozen=True)
class MigrationOptions:
    all_projects: bool = False
    project_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    thread_roles: tuple[ThreadRoleV3, ...] = ()
    dry_run: bool = False
    fail_fast_threshold: int | None = None


@dataclass(frozen=True)
class MigrationTarget:
    project_id: str
    node_id: str
    thread_role: ThreadRoleV3


def _normalize_ids(values: Iterable[str]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return tuple(unique)


def _discover_node_ids(project_root: Path) -> set[str]:
    nodes: set[str] = set()
    planningtree_dir = project_root / ".planningtree"
    for store_name in ("conversation_v2", "conversation_v3"):
        conversation_dir = planningtree_dir / store_name
        if not conversation_dir.exists() or not conversation_dir.is_dir():
            continue
        for child in conversation_dir.iterdir():
            if child.is_dir():
                nodes.add(child.name)
    return nodes


def _discover_thread_roles(project_root: Path, node_id: str) -> set[ThreadRoleV3]:
    roles: set[ThreadRoleV3] = set()
    planningtree_dir = project_root / ".planningtree"
    for store_name in ("conversation_v2", "conversation_v3"):
        node_dir = planningtree_dir / store_name / node_id
        if not node_dir.exists() or not node_dir.is_dir():
            continue
        for thread_role in THREAD_ROLES_V3:
            if (node_dir / f"{thread_role}.json").exists():
                roles.add(thread_role)
    return roles


def _resolve_project_ids(storage: Storage, options: MigrationOptions) -> tuple[list[str], list[dict[str, str]]]:
    entries = storage.workspace_store.list_entries()
    known_project_ids = {entry["project_id"] for entry in entries}
    errors: list[dict[str, str]] = []

    if options.all_projects:
        return sorted(known_project_ids), errors

    requested = list(options.project_ids)
    resolved: list[str] = []
    for project_id in requested:
        if project_id in known_project_ids:
            resolved.append(project_id)
            continue
        errors.append(
            {
                "project_id": project_id,
                "node_id": "*",
                "thread_role": "*",
                "error_type": "project_not_found",
                "message": f"Project {project_id!r} is not registered in workspace store.",
            }
        )
    return sorted(resolved), errors


def discover_targets(storage: Storage, *, options: MigrationOptions) -> tuple[list[MigrationTarget], list[dict[str, str]]]:
    project_ids, errors = _resolve_project_ids(storage, options)
    targets: list[MigrationTarget] = []
    explicit_node_ids = set(options.node_ids)
    explicit_roles = set(options.thread_roles)

    for project_id in project_ids:
        try:
            project_root = Path(storage.workspace_store.get_folder_path(project_id)).expanduser().resolve()
        except Exception as exc:
            errors.append(
                {
                    "project_id": project_id,
                    "node_id": "*",
                    "thread_role": "*",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            continue

        node_ids = explicit_node_ids or _discover_node_ids(project_root)
        for node_id in sorted(node_ids):
            roles = explicit_roles or _discover_thread_roles(project_root, node_id)
            for thread_role in sorted(roles):
                targets.append(
                    MigrationTarget(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role=thread_role,
                    )
                )

    return targets, errors


def _migrate_target(storage: Storage, target: MigrationTarget, *, dry_run: bool) -> str:
    snapshot_store_v3 = storage.thread_snapshot_store_v3
    snapshot_store_v2 = storage.thread_snapshot_store_v2

    if snapshot_store_v3.exists(target.project_id, target.node_id, target.thread_role):
        # Read to catch malformed JSON early while still treating existing V3 as skip_existing.
        snapshot_store_v3.read_snapshot(target.project_id, target.node_id, target.thread_role)
        return "skip_existing"

    if not snapshot_store_v2.exists(target.project_id, target.node_id, target.thread_role):
        return "skip_missing_v2"

    legacy_snapshot = snapshot_store_v2.read_snapshot(target.project_id, target.node_id, target.thread_role)
    projected_snapshot = project_v2_snapshot_to_v3(legacy_snapshot)
    normalized_snapshot = normalize_thread_snapshot_v3(
        projected_snapshot,
        project_id=target.project_id,
        node_id=target.node_id,
        thread_role=target.thread_role,
    )
    if not dry_run:
        snapshot_store_v3.write_snapshot(
            target.project_id,
            target.node_id,
            target.thread_role,
            normalized_snapshot,
        )
    return "migrated"


def _init_totals() -> dict[str, int]:
    return {
        "scanned": 0,
        "migrated": 0,
        "skip_existing": 0,
        "skip_missing_v2": 0,
        "failed": 0,
    }


def _build_checksum(rows: list[str]) -> dict[str, Any]:
    payload = "\n".join(sorted(rows))
    return {
        "algorithm": "sha256",
        "targets_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "target_count": len(rows),
    }


def run_migration(storage: Storage, *, options: MigrationOptions) -> dict[str, Any]:
    started_at = iso_now()
    run_id = f"convv3mig_{uuid4().hex[:12]}"
    bridge_mode = get_conversation_v3_bridge_mode()

    targets, discovery_errors = discover_targets(storage, options=options)
    totals = _init_totals()
    errors: list[dict[str, str]] = list(discovery_errors)
    results: list[dict[str, str]] = []
    checksum_rows: list[str] = []

    for discovery_error in discovery_errors:
        totals["failed"] += 1
        checksum_rows.append(
            f"{discovery_error.get('project_id', '*')}:{discovery_error.get('node_id', '*')}:"
            f"{discovery_error.get('thread_role', '*')}:failed"
        )

    stopped_early = False
    for target in targets:
        totals["scanned"] += 1
        status = "failed"
        try:
            status = _migrate_target(storage, target, dry_run=options.dry_run)
            totals[status] += 1
        except Exception as exc:  # pragma: no cover - exercised through integration-like unit tests
            totals["failed"] += 1
            errors.append(
                {
                    "project_id": target.project_id,
                    "node_id": target.node_id,
                    "thread_role": target.thread_role,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )

        results.append(
            {
                "project_id": target.project_id,
                "node_id": target.node_id,
                "thread_role": target.thread_role,
                "status": status,
            }
        )
        checksum_rows.append(f"{target.project_id}:{target.node_id}:{target.thread_role}:{status}")

        if options.fail_fast_threshold is not None and totals["failed"] > options.fail_fast_threshold:
            stopped_early = True
            break

    ended_at = iso_now()
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "mode": "dry-run" if options.dry_run else "apply",
        "bridge_mode": bridge_mode,
        "filters": {
            "all_projects": options.all_projects,
            "project_ids": list(options.project_ids),
            "node_ids": list(options.node_ids),
            "thread_roles": list(options.thread_roles),
        },
        "totals": totals,
        "checksum": _build_checksum(checksum_rows),
        "errors": errors,
        "results": results,
        "stopped_early": stopped_early,
        "fail_fast_threshold": options.fail_fast_threshold,
    }
    return report


def _render_summary(report: dict[str, Any], report_path: Path | None) -> str:
    totals = report["totals"]
    lines = [
        f"run_id: {report['run_id']}",
        f"mode: {report['mode']}",
        f"bridge_mode: {report['bridge_mode']}",
        (
            "totals: "
            f"scanned={totals['scanned']} "
            f"migrated={totals['migrated']} "
            f"skip_existing={totals['skip_existing']} "
            f"skip_missing_v2={totals['skip_missing_v2']} "
            f"failed={totals['failed']}"
        ),
        f"checksum.targets_hash: {report['checksum']['targets_hash']}",
    ]
    if report.get("stopped_early"):
        lines.append("stopped_early: true")
    if report_path is not None:
        lines.append(f"report_json: {report_path}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch migrate PlanningTree conversation snapshots from V2 to V3.",
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--all-projects",
        action="store_true",
        help="Scan all projects listed in workspace config.",
    )
    scope.add_argument(
        "--project-id",
        action="append",
        default=[],
        help="Project id to migrate. Can be repeated.",
    )
    parser.add_argument(
        "--node-id",
        action="append",
        default=[],
        help="Optional node id filter. Can be repeated.",
    )
    parser.add_argument(
        "--thread-role",
        action="append",
        choices=THREAD_ROLES_V3,
        default=[],
        help="Optional thread role filter. Can be repeated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write V3 files, only compute migration outcomes.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Write full migration report JSON to this path.",
    )
    parser.add_argument(
        "--fail-fast-threshold",
        type=int,
        default=None,
        help="Stop batch and return non-zero if failed count exceeds this value.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Optional PlanningTree app data root override.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.fail_fast_threshold is not None and int(args.fail_fast_threshold) < 0:
        print("--fail-fast-threshold must be >= 0", file=sys.stderr)
        return 2

    project_ids = _normalize_ids(args.project_id or [])
    node_ids = _normalize_ids(args.node_id or [])
    thread_roles = tuple(args.thread_role or ())
    options = MigrationOptions(
        all_projects=bool(args.all_projects),
        project_ids=project_ids,
        node_ids=node_ids,
        thread_roles=thread_roles,
        dry_run=bool(args.dry_run),
        fail_fast_threshold=args.fail_fast_threshold,
    )

    storage = Storage(build_app_paths(args.data_root))
    report = run_migration(storage, options=options)

    if args.report_json is not None:
        atomic_write_json(args.report_json, report)

    print(_render_summary(report, args.report_json))
    if options.fail_fast_threshold is not None and int(report["totals"]["failed"]) > options.fail_fast_threshold:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
