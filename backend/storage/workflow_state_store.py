from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_VALID_PHASES = {
    "idle",
    "execution_running",
    "execution_decision_pending",
    "audit_running",
    "audit_decision_pending",
    "done",
    "failed",
}
_VALID_LATEST_COMMIT_ACTIONS = {
    "split",
    "mark_done_from_execution",
    "review_in_audit",
}

_DEFAULT_STATE: dict[str, Any] = {
    "nodeId": "",
    "workflowPhase": "idle",
    "askThreadId": None,
    "executionThreadId": None,
    "auditLineageThreadId": None,
    "reviewThreadId": None,
    "activeExecutionRunId": None,
    "latestExecutionRunId": None,
    "activeReviewCycleId": None,
    "latestReviewCycleId": None,
    "currentExecutionDecision": None,
    "currentAuditDecision": None,
    "acceptedSha": None,
    "latestCommit": None,
    "runtimeBlock": None,
    "mutationCache": {},
    "createdAt": None,
    "updatedAt": None,
}


class WorkflowStateStore:
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

    def _workflow_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "workflow_v2"

    def path(self, project_id: str, node_id: str) -> Path:
        return self._workflow_dir(project_id) / f"{node_id}.json"

    def exists(self, project_id: str, node_id: str) -> bool:
        return self.path(project_id, node_id).exists()

    def read_state(self, project_id: str, node_id: str) -> dict[str, Any] | None:
        with self._lock_registry.for_project(project_id):
            target = self.path(project_id, node_id)
            if not target.exists():
                return None
            payload = load_json(target, default=None)
            return self._normalize_state(payload, node_id=node_id)

    def write_state(self, project_id: str, node_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_state(state, node_id=node_id)
            if not normalized["createdAt"]:
                normalized["createdAt"] = iso_now()
            normalized["updatedAt"] = iso_now()
            target = self.path(project_id, node_id)
            ensure_dir(target.parent)
            atomic_write_json(target, normalized)
            return copy.deepcopy(normalized)

    def default_state(self, node_id: str) -> dict[str, Any]:
        payload = copy.deepcopy(_DEFAULT_STATE)
        payload["nodeId"] = node_id
        now = iso_now()
        payload["createdAt"] = now
        payload["updatedAt"] = now
        return payload

    def _normalize_state(self, payload: Any, *, node_id: str) -> dict[str, Any]:
        source = payload if isinstance(payload, dict) else {}
        phase = str(source.get("workflowPhase") or source.get("workflow_phase") or "idle").strip()
        if phase not in _VALID_PHASES:
            phase = "idle"
        current_execution_decision = source.get("currentExecutionDecision")
        current_audit_decision = source.get("currentAuditDecision")
        mutation_cache = source.get("mutationCache")
        latest_commit = self._normalize_latest_commit(
            source.get("latestCommit") if source.get("latestCommit") is not None else source.get("latest_commit")
        )
        return {
            "nodeId": str(source.get("nodeId") or source.get("node_id") or node_id),
            "workflowPhase": phase,
            "askThreadId": _normalize_optional_string(source.get("askThreadId") or source.get("ask_thread_id")),
            "executionThreadId": _normalize_optional_string(source.get("executionThreadId") or source.get("execution_thread_id")),
            "auditLineageThreadId": _normalize_optional_string(source.get("auditLineageThreadId") or source.get("audit_lineage_thread_id")),
            "reviewThreadId": _normalize_optional_string(source.get("reviewThreadId") or source.get("review_thread_id")),
            "activeExecutionRunId": _normalize_optional_string(source.get("activeExecutionRunId") or source.get("active_execution_run_id")),
            "latestExecutionRunId": _normalize_optional_string(source.get("latestExecutionRunId") or source.get("latest_execution_run_id")),
            "activeReviewCycleId": _normalize_optional_string(source.get("activeReviewCycleId") or source.get("active_review_cycle_id")),
            "latestReviewCycleId": _normalize_optional_string(source.get("latestReviewCycleId") or source.get("latest_review_cycle_id")),
            "currentExecutionDecision": copy.deepcopy(current_execution_decision) if isinstance(current_execution_decision, dict) else None,
            "currentAuditDecision": copy.deepcopy(current_audit_decision) if isinstance(current_audit_decision, dict) else None,
            "acceptedSha": _normalize_optional_string(source.get("acceptedSha") or source.get("accepted_sha")),
            "latestCommit": latest_commit,
            "runtimeBlock": copy.deepcopy(source.get("runtimeBlock")) if isinstance(source.get("runtimeBlock"), dict) else None,
            "mutationCache": copy.deepcopy(mutation_cache) if isinstance(mutation_cache, dict) else {},
            "createdAt": _normalize_optional_string(source.get("createdAt") or source.get("created_at")),
            "updatedAt": _normalize_optional_string(source.get("updatedAt") or source.get("updated_at")),
        }

    def _normalize_latest_commit(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        source_action = _normalize_optional_string(payload.get("sourceAction") or payload.get("source_action"))
        if source_action not in _VALID_LATEST_COMMIT_ACTIONS:
            source_action = None

        committed = payload.get("committed")
        if not isinstance(committed, bool):
            committed = None

        normalized = {
            "sourceAction": source_action,
            "initialSha": _normalize_optional_string(payload.get("initialSha") or payload.get("initial_sha")),
            "headSha": _normalize_optional_string(payload.get("headSha") or payload.get("head_sha")),
            "commitMessage": _normalize_optional_string(payload.get("commitMessage") or payload.get("commit_message")),
            "committed": committed,
            "recordedAt": _normalize_optional_string(payload.get("recordedAt") or payload.get("recorded_at")),
        }
        if all(value is None for value in normalized.values()):
            return None
        return normalized


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
