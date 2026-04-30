from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import InvalidRequest, ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_VALID_EXECUTION_STATUSES = {"idle", "executing", "completed", "failed", "review_pending", "review_accepted"}
_VALID_ROLLUP_STATUSES = {"pending", "ready", "accepted"}
_ROLLUP_TRANSITIONS: dict[str, str] = {
    "pending": "ready",
    "ready": "accepted",
}

_DEFAULT_EXECUTION: dict[str, Any] = {
    "status": "idle",
    "initial_sha": None,
    "head_sha": None,
    "started_at": None,
    "completed_at": None,
    "local_review_started_at": None,
    "local_review_prompt_consumed_at": None,
    "commit_message": None,
    "changed_files": [],
    "error_message": None,
    "auto_review": None,
}

_DEFAULT_ROLLUP: dict[str, Any] = {
    "status": "pending",
    "summary": None,
    "sha": None,
    "accepted_at": None,
    "package_review_started_at": None,
    "package_review_prompt_consumed_at": None,
    "draft": {
        "summary": None,
        "sha": None,
        "generated_at": None,
    },
}

_DEFAULT_REVIEW: dict[str, Any] = {
    "checkpoints": [],
    "rollup": copy.deepcopy(_DEFAULT_ROLLUP),
    "pending_siblings": [],
    "k0_git_head_sha": None,
}

_DEFAULT_SPLIT_JOBS: dict[str, Any] = {
    "active_job": None,
    "last_error": None,
    "last_completed": None,
}


class WorkflowDomainStore:
    def __init__(
        self,
        paths: AppPaths,
        workspace_store: WorkspaceStore,
        lock_registry: ProjectLockRegistry,
    ) -> None:
        self._paths = paths
        self._workspace_store = workspace_store
        self._lock_registry = lock_registry

    def workflow_dir(self, project_id: str) -> Path:
        folder_path = self._workspace_store.get_folder_path(project_id)
        return Path(folder_path).expanduser().resolve() / ".planningtree" / "workflow_core_v2"

    def node_path(self, project_id: str, node_id: str) -> Path:
        return self.workflow_dir(project_id) / f"{node_id}.json"

    def artifact_jobs_path(self, project_id: str) -> Path:
        return self.workflow_dir(project_id) / "artifact_jobs.json"

    def read_execution(self, project_id: str, node_id: str) -> dict[str, Any] | None:
        with self._lock_registry.for_project(project_id):
            payload = self._read_node_unlocked(project_id, node_id)
            raw = payload.get("executionProjection")
            if raw is None:
                return None
            return self._normalize_execution(raw)

    def execution_exists(self, project_id: str, node_id: str) -> bool:
        return self.read_execution(project_id, node_id) is not None

    def write_execution(self, project_id: str, node_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            self._require_project_dir(project_id)
            payload = self._read_node_unlocked(project_id, node_id)
            normalized = self._normalize_execution(state)
            payload["executionProjection"] = normalized
            self._write_node_unlocked(project_id, node_id, payload)
            return copy.deepcopy(normalized)

    def read_review(self, project_id: str, review_node_id: str) -> dict[str, Any] | None:
        with self._lock_registry.for_project(project_id):
            payload = self._read_node_unlocked(project_id, review_node_id)
            raw = payload.get("reviewPackage")
            if raw is None:
                return None
            return self._normalize_review(raw)

    def write_review(self, project_id: str, review_node_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            self._require_project_dir(project_id)
            payload = self._read_node_unlocked(project_id, review_node_id)
            normalized = self._normalize_review(state)
            payload["reviewPackage"] = normalized
            self._write_node_unlocked(project_id, review_node_id, payload)
            return copy.deepcopy(normalized)

    def default_review(self) -> dict[str, Any]:
        return copy.deepcopy(_DEFAULT_REVIEW)

    def add_review_checkpoint(
        self,
        project_id: str,
        review_node_id: str,
        *,
        sha: str,
        summary: str | None = None,
        source_node_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            state = self._read_review_unlocked(project_id, review_node_id)
            checkpoints = state.get("checkpoints", [])
            checkpoint = {
                "label": f"K{len(checkpoints)}",
                "sha": sha,
                "summary": summary,
                "source_node_id": source_node_id,
                "accepted_at": iso_now(),
            }
            checkpoints.append(checkpoint)
            state["checkpoints"] = checkpoints
            return self._write_review_unlocked(project_id, review_node_id, state)

    def set_review_rollup(
        self,
        project_id: str,
        review_node_id: str,
        status: str,
        summary: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            state = self._read_review_unlocked(project_id, review_node_id)
            rollup = state.get("rollup", copy.deepcopy(_DEFAULT_ROLLUP))
            current = rollup.get("status", "pending")
            if current == "accepted":
                raise InvalidRequest("Rollup is already accepted and immutable. No further transitions allowed.")
            if status != current:
                allowed_next = _ROLLUP_TRANSITIONS.get(current)
                if allowed_next != status:
                    raise InvalidRequest(
                        f"Invalid rollup transition: {current} -> {status}. "
                        f"Allowed: {current} -> {allowed_next}."
                    )
            if status == "accepted":
                if not summary or not summary.strip():
                    raise InvalidRequest("Rollup transition to 'accepted' requires a non-empty summary.")
                if not sha or not sha.strip():
                    raise InvalidRequest("Rollup transition to 'accepted' requires a non-empty sha.")
                rollup["summary"] = summary.strip()
                rollup["sha"] = sha.strip()
                rollup["accepted_at"] = iso_now()
                rollup["draft"] = copy.deepcopy(_DEFAULT_ROLLUP["draft"])
            else:
                if summary is not None:
                    rollup["summary"] = summary
                if sha is not None:
                    rollup["sha"] = sha
            rollup["status"] = status
            state["rollup"] = rollup
            return self._write_review_unlocked(project_id, review_node_id, state)

    def set_review_rollup_draft(
        self,
        project_id: str,
        review_node_id: str,
        *,
        summary: str,
        sha: str,
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            state = self._read_review_unlocked(project_id, review_node_id)
            rollup = state.get("rollup", copy.deepcopy(_DEFAULT_ROLLUP))
            if rollup.get("status") != "ready":
                raise InvalidRequest("Rollup draft can only be stored while rollup status is 'ready'.")
            cleaned_summary = str(summary or "").strip()
            cleaned_sha = str(sha or "").strip()
            if not cleaned_summary:
                raise InvalidRequest("Rollup draft requires a non-empty summary.")
            if not cleaned_sha:
                raise InvalidRequest("Rollup draft requires a non-empty sha.")
            rollup["draft"] = {
                "summary": cleaned_summary,
                "sha": cleaned_sha,
                "generated_at": generated_at.strip() if isinstance(generated_at, str) and generated_at.strip() else iso_now(),
            }
            state["rollup"] = rollup
            return self._write_review_unlocked(project_id, review_node_id, state)

    def open_package_review(self, project_id: str, review_node_id: str) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            state = self._read_review_unlocked(project_id, review_node_id)
            rollup = state.get("rollup", copy.deepcopy(_DEFAULT_ROLLUP))
            rollup["package_review_started_at"] = iso_now()
            rollup["package_review_prompt_consumed_at"] = None
            state["rollup"] = rollup
            return self._write_review_unlocked(project_id, review_node_id, state)

    def mark_package_review_prompt_consumed(self, project_id: str, review_node_id: str) -> dict[str, Any] | None:
        with self._lock_registry.for_project(project_id):
            state = self._read_review_unlocked(project_id, review_node_id)
            rollup = state.get("rollup", copy.deepcopy(_DEFAULT_ROLLUP))
            started_at = rollup.get("package_review_started_at")
            if not isinstance(started_at, str) or not started_at.strip():
                return None
            consumed_at = rollup.get("package_review_prompt_consumed_at")
            if isinstance(consumed_at, str) and consumed_at.strip():
                return state
            rollup["package_review_prompt_consumed_at"] = iso_now()
            state["rollup"] = rollup
            return self._write_review_unlocked(project_id, review_node_id, state)

    def get_next_pending_sibling(self, project_id: str, review_node_id: str) -> dict[str, Any] | None:
        with self._lock_registry.for_project(project_id):
            state = self._read_review_unlocked(project_id, review_node_id)
            for sibling in state.get("pending_siblings", []):
                if sibling.get("materialized_node_id") is None:
                    return copy.deepcopy(sibling)
            return None

    def mark_sibling_materialized(
        self,
        project_id: str,
        review_node_id: str,
        index: int,
        node_id: str,
    ) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            state = self._read_review_unlocked(project_id, review_node_id)
            for sibling in state.get("pending_siblings", []):
                if sibling.get("index") == index:
                    sibling["materialized_node_id"] = node_id
                    break
            return self._write_review_unlocked(project_id, review_node_id, state)

    def read_split_jobs(self, project_id: str) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            payload = load_json(self.artifact_jobs_path(project_id), default=None)
            if not isinstance(payload, dict):
                return copy.deepcopy(_DEFAULT_SPLIT_JOBS)
            return self._normalize_split_jobs(payload.get("split"))

    def write_split_jobs(self, project_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            self._require_project_dir(project_id)
            target = self.artifact_jobs_path(project_id)
            payload = load_json(target, default=None)
            if not isinstance(payload, dict):
                payload = {}
            normalized = self._normalize_split_jobs(state)
            payload["split"] = normalized
            ensure_dir(target.parent)
            atomic_write_json(target, payload)
            return copy.deepcopy(normalized)

    def clear_split_jobs(self, project_id: str) -> dict[str, Any]:
        return self.write_split_jobs(project_id, _DEFAULT_SPLIT_JOBS)

    def _require_project_dir(self, project_id: str) -> None:
        project_dir = self.workflow_dir(project_id).parent
        if not project_dir.exists():
            raise ProjectNotFound(project_id)

    def _read_node_unlocked(self, project_id: str, node_id: str) -> dict[str, Any]:
        payload = load_json(self.node_path(project_id, node_id), default=None)
        if not isinstance(payload, dict):
            return {
                "schema_version": 1,
                "state_version": 0,
                "project_id": project_id,
                "node_id": node_id,
                "phase": "ready_for_execution",
            }
        payload["project_id"] = project_id
        payload["node_id"] = node_id
        payload.setdefault("schema_version", 1)
        payload.setdefault("state_version", 0)
        payload.setdefault("phase", "ready_for_execution")
        return payload

    def _write_node_unlocked(self, project_id: str, node_id: str, payload: dict[str, Any]) -> None:
        target = self.node_path(project_id, node_id)
        ensure_dir(target.parent)
        atomic_write_json(target, payload)

    def _read_review_unlocked(self, project_id: str, review_node_id: str) -> dict[str, Any]:
        payload = self._read_node_unlocked(project_id, review_node_id)
        return self._normalize_review(payload.get("reviewPackage"))

    def _write_review_unlocked(self, project_id: str, review_node_id: str, state: dict[str, Any]) -> dict[str, Any]:
        payload = self._read_node_unlocked(project_id, review_node_id)
        normalized = self._normalize_review(state)
        payload["reviewPackage"] = normalized
        self._write_node_unlocked(project_id, review_node_id, payload)
        return copy.deepcopy(normalized)

    def _normalize_execution(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_EXECUTION)
        return {
            "status": self._string_choice(payload.get("status"), _VALID_EXECUTION_STATUSES, "idle"),
            "initial_sha": self._optional_string(payload.get("initial_sha")),
            "head_sha": self._optional_string(payload.get("head_sha")),
            "started_at": self._optional_string(payload.get("started_at")),
            "completed_at": self._optional_string(payload.get("completed_at")),
            "local_review_started_at": self._optional_string(payload.get("local_review_started_at")),
            "local_review_prompt_consumed_at": self._optional_string(payload.get("local_review_prompt_consumed_at")),
            "commit_message": self._optional_string(payload.get("commit_message")),
            "changed_files": payload.get("changed_files") if isinstance(payload.get("changed_files"), list) else [],
            "error_message": self._optional_string(payload.get("error_message")),
            "auto_review": payload.get("auto_review") if isinstance(payload.get("auto_review"), dict) else None,
        }

    def _normalize_review(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_REVIEW)
        checkpoints = [
            normalized
            for checkpoint in payload.get("checkpoints", [])
            if (normalized := self._normalize_checkpoint(checkpoint)) is not None
        ] if isinstance(payload.get("checkpoints"), list) else []
        siblings = [
            normalized
            for sibling in payload.get("pending_siblings", [])
            if (normalized := self._normalize_pending_sibling(sibling)) is not None
        ] if isinstance(payload.get("pending_siblings"), list) else []
        return {
            "checkpoints": checkpoints,
            "rollup": self._normalize_rollup(payload.get("rollup")),
            "pending_siblings": siblings,
            "k0_git_head_sha": self._optional_string(payload.get("k0_git_head_sha")),
        }

    def _normalize_checkpoint(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        label = self._optional_string(payload.get("label"))
        sha = self._optional_string(payload.get("sha"))
        if label is None or sha is None:
            return None
        return {
            "label": label,
            "sha": sha,
            "summary": self._optional_string(payload.get("summary")),
            "source_node_id": self._optional_string(payload.get("source_node_id")),
            "accepted_at": self._optional_string(payload.get("accepted_at")) or iso_now(),
        }

    def _normalize_rollup(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_ROLLUP)
        return {
            "status": self._string_choice(payload.get("status"), _VALID_ROLLUP_STATUSES, "pending"),
            "summary": self._optional_string(payload.get("summary")),
            "sha": self._optional_string(payload.get("sha")),
            "accepted_at": self._optional_string(payload.get("accepted_at")),
            "package_review_started_at": self._optional_string(payload.get("package_review_started_at")),
            "package_review_prompt_consumed_at": self._optional_string(payload.get("package_review_prompt_consumed_at")),
            "draft": self._normalize_rollup_draft(payload.get("draft")),
        }

    def _normalize_rollup_draft(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_ROLLUP["draft"])
        return {
            "summary": self._optional_string(payload.get("summary")),
            "sha": self._optional_string(payload.get("sha")),
            "generated_at": self._optional_string(payload.get("generated_at")),
        }

    def _normalize_pending_sibling(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        index = payload.get("index")
        title = self._optional_string(payload.get("title"))
        if not isinstance(index, int) or title is None:
            return None
        return {
            "index": index,
            "title": title,
            "objective": self._optional_string(payload.get("objective")),
            "materialized_node_id": self._optional_string(payload.get("materialized_node_id")),
        }

    def _normalize_split_jobs(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_SPLIT_JOBS)
        return {
            "active_job": self._normalize_active_job(payload.get("active_job")),
            "last_error": self._normalize_job_error(payload.get("last_error")),
            "last_completed": self._normalize_completed_job(payload.get("last_completed")),
        }

    def _normalize_active_job(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        job_id = self._optional_string(payload.get("job_id"))
        node_id = self._optional_string(payload.get("node_id"))
        mode = self._optional_string(payload.get("mode"))
        started_at = self._optional_string(payload.get("started_at"))
        if None in (job_id, node_id, mode, started_at):
            return None
        return {"job_id": job_id, "node_id": node_id, "mode": mode, "started_at": started_at}

    def _normalize_job_error(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        error = self._optional_string(payload.get("error"))
        started_at = self._optional_string(payload.get("started_at"))
        completed_at = self._optional_string(payload.get("completed_at"))
        if None in (error, started_at, completed_at):
            return None
        return {
            "job_id": self._optional_string(payload.get("job_id")),
            "node_id": self._optional_string(payload.get("node_id")),
            "mode": self._optional_string(payload.get("mode")),
            "started_at": started_at,
            "completed_at": completed_at,
            "error": error,
        }

    def _normalize_completed_job(self, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        completed_at = self._optional_string(payload.get("completed_at"))
        if completed_at is None:
            return None
        return {
            "job_id": self._optional_string(payload.get("job_id")),
            "node_id": self._optional_string(payload.get("node_id")),
            "mode": self._optional_string(payload.get("mode")),
            "started_at": self._optional_string(payload.get("started_at")),
            "completed_at": completed_at,
        }

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @classmethod
    def _string_choice(cls, value: Any, allowed: set[str], default: str) -> str:
        normalized = cls._optional_string(value)
        return normalized if normalized in allowed else default
