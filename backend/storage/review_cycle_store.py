from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_VALID_LIFECYCLE_STATUSES = {"running", "completed", "failed", "superseded"}


class ReviewCycleStore:
    def __init__(
        self,
        paths: AppPaths,
        workspace_store: WorkspaceStore,
        lock_registry: ProjectLockRegistry,
    ) -> None:
        self._paths = paths
        self._workspace_store = workspace_store
        self._lock_registry = lock_registry

    def _project_dir(self, project_id: str) -> Path:
        folder_path = self._workspace_store.get_folder_path(project_id)
        return Path(folder_path).expanduser().resolve() / ".planningtree"

    def _cycles_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "workflow_v2_review_cycles"

    def path(self, project_id: str, node_id: str) -> Path:
        return self._cycles_dir(project_id) / f"{node_id}.json"

    def read_cycles(self, project_id: str, node_id: str) -> list[dict[str, Any]]:
        with self._lock_registry.for_project(project_id):
            payload = load_json(self.path(project_id, node_id), default=None)
            return self._normalize_cycles(payload)

    def write_cycles(self, project_id: str, node_id: str, cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_cycles({"cycles": cycles})
            target = self.path(project_id, node_id)
            ensure_dir(target.parent)
            atomic_write_json(target, {"cycles": normalized})
            return copy.deepcopy(normalized)

    def append_cycle(self, project_id: str, node_id: str, cycle: dict[str, Any]) -> list[dict[str, Any]]:
        cycles = self.read_cycles(project_id, node_id)
        cycles.append(self._normalize_cycle(cycle))
        return self.write_cycles(project_id, node_id, cycles)

    def upsert_cycle(self, project_id: str, node_id: str, cycle: dict[str, Any]) -> list[dict[str, Any]]:
        normalized = self._normalize_cycle(cycle)
        cycle_id = str(normalized.get("cycleId") or "")
        cycles = self.read_cycles(project_id, node_id)
        replaced = False
        for index, current in enumerate(cycles):
            if str(current.get("cycleId") or "") == cycle_id:
                cycles[index] = normalized
                replaced = True
                break
        if not replaced:
            cycles.append(normalized)
        return self.write_cycles(project_id, node_id, cycles)

    def _normalize_cycles(self, payload: Any) -> list[dict[str, Any]]:
        source = payload if isinstance(payload, dict) else {}
        raw_cycles = source.get("cycles")
        if not isinstance(raw_cycles, list):
            return []
        cycles: list[dict[str, Any]] = []
        for raw in raw_cycles:
            if not isinstance(raw, dict):
                continue
            cycles.append(self._normalize_cycle(raw))
        return cycles

    def _normalize_cycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        lifecycle_status = str(payload.get("lifecycleStatus") or payload.get("lifecycle_status") or "running").strip()
        if lifecycle_status not in _VALID_LIFECYCLE_STATUSES:
            lifecycle_status = "running"
        return {
            "cycleId": _normalize_optional_string(payload.get("cycleId") or payload.get("cycle_id")) or "",
            "projectId": _normalize_optional_string(payload.get("projectId") or payload.get("project_id")) or "",
            "nodeId": _normalize_optional_string(payload.get("nodeId") or payload.get("node_id")) or "",
            "sourceExecutionRunId": _normalize_optional_string(payload.get("sourceExecutionRunId") or payload.get("source_execution_run_id")),
            "auditLineageThreadId": _normalize_optional_string(payload.get("auditLineageThreadId") or payload.get("audit_lineage_thread_id")),
            "reviewThreadId": _normalize_optional_string(payload.get("reviewThreadId") or payload.get("review_thread_id")),
            "reviewTurnId": _normalize_optional_string(payload.get("reviewTurnId") or payload.get("review_turn_id")),
            "reviewCommitSha": _normalize_optional_string(payload.get("reviewCommitSha") or payload.get("review_commit_sha")),
            "clientRequestId": _normalize_optional_string(payload.get("clientRequestId") or payload.get("client_request_id")),
            "lifecycleStatus": lifecycle_status,
            "reviewDisposition": _normalize_optional_string(payload.get("reviewDisposition") or payload.get("review_disposition")),
            "finalReviewText": _normalize_optional_string(payload.get("finalReviewText") or payload.get("final_review_text")),
            "errorMessage": _normalize_optional_string(payload.get("errorMessage") or payload.get("error_message")),
            "startedAt": _normalize_optional_string(payload.get("startedAt") or payload.get("started_at")),
            "completedAt": _normalize_optional_string(payload.get("completedAt") or payload.get("completed_at")),
        }


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
