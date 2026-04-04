from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_VALID_STATUSES = {"running", "completed", "failed"}
_VALID_TRIGGERS = {"finish_task", "follow_up_message", "improve_from_review"}


class ExecutionRunStore:
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

    def _runs_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "workflow_v2_execution_runs"

    def path(self, project_id: str, node_id: str) -> Path:
        return self._runs_dir(project_id) / f"{node_id}.json"

    def read_runs(self, project_id: str, node_id: str) -> list[dict[str, Any]]:
        with self._lock_registry.for_project(project_id):
            payload = load_json(self.path(project_id, node_id), default=None)
            return self._normalize_runs(payload)

    def write_runs(self, project_id: str, node_id: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_runs({"runs": runs})
            target = self.path(project_id, node_id)
            ensure_dir(target.parent)
            atomic_write_json(target, {"runs": normalized})
            return copy.deepcopy(normalized)

    def append_run(self, project_id: str, node_id: str, run: dict[str, Any]) -> list[dict[str, Any]]:
        runs = self.read_runs(project_id, node_id)
        runs.append(self._normalize_run(run))
        return self.write_runs(project_id, node_id, runs)

    def upsert_run(self, project_id: str, node_id: str, run: dict[str, Any]) -> list[dict[str, Any]]:
        normalized = self._normalize_run(run)
        runs = self.read_runs(project_id, node_id)
        run_id = str(normalized.get("runId") or "")
        replaced = False
        for index, current in enumerate(runs):
            if str(current.get("runId") or "") == run_id:
                runs[index] = normalized
                replaced = True
                break
        if not replaced:
            runs.append(normalized)
        return self.write_runs(project_id, node_id, runs)

    def _normalize_runs(self, payload: Any) -> list[dict[str, Any]]:
        source = payload if isinstance(payload, dict) else {}
        raw_runs = source.get("runs")
        if not isinstance(raw_runs, list):
            return []
        runs: list[dict[str, Any]] = []
        for raw in raw_runs:
            if not isinstance(raw, dict):
                continue
            runs.append(self._normalize_run(raw))
        return runs

    def _normalize_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        status = str(payload.get("status") or "running").strip()
        if status not in _VALID_STATUSES:
            status = "running"
        trigger = str(payload.get("triggerKind") or payload.get("trigger_kind") or "finish_task").strip()
        if trigger not in _VALID_TRIGGERS:
            trigger = "finish_task"
        return {
            "runId": _normalize_optional_string(payload.get("runId") or payload.get("run_id")) or "",
            "projectId": _normalize_optional_string(payload.get("projectId") or payload.get("project_id")) or "",
            "nodeId": _normalize_optional_string(payload.get("nodeId") or payload.get("node_id")) or "",
            "executionThreadId": _normalize_optional_string(payload.get("executionThreadId") or payload.get("execution_thread_id")),
            "executionTurnId": _normalize_optional_string(payload.get("executionTurnId") or payload.get("execution_turn_id")),
            "clientRequestId": _normalize_optional_string(payload.get("clientRequestId") or payload.get("client_request_id")),
            "triggerKind": trigger,
            "sourceReviewCycleId": _normalize_optional_string(payload.get("sourceReviewCycleId") or payload.get("source_review_cycle_id")),
            "startSha": _normalize_optional_string(payload.get("startSha") or payload.get("start_sha")),
            "candidateWorkspaceHash": _normalize_optional_string(payload.get("candidateWorkspaceHash") or payload.get("candidate_workspace_hash")),
            "committedHeadSha": _normalize_optional_string(payload.get("committedHeadSha") or payload.get("committed_head_sha")),
            "status": status,
            "decision": _normalize_optional_string(payload.get("decision")),
            "summaryText": _normalize_optional_string(payload.get("summaryText") or payload.get("summary_text")),
            "errorMessage": _normalize_optional_string(payload.get("errorMessage") or payload.get("error_message")),
            "startedAt": _normalize_optional_string(payload.get("startedAt") or payload.get("started_at")),
            "completedAt": _normalize_optional_string(payload.get("completedAt") or payload.get("completed_at")),
            "decidedAt": _normalize_optional_string(payload.get("decidedAt") or payload.get("decided_at")),
        }


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
