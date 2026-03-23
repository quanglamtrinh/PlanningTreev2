from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import InvalidRequest, ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_VALID_ROLLUP_STATUSES = {"pending", "ready", "accepted"}
_ROLLUP_TRANSITIONS: dict[str, str] = {
    "pending": "ready",
    "ready": "accepted",
}

_DEFAULT_ROLLUP: dict[str, Any] = {
    "status": "pending",
    "summary": None,
    "sha": None,
    "accepted_at": None,
}

_DEFAULT_STATE: dict[str, Any] = {
    "checkpoints": [],
    "rollup": copy.deepcopy(_DEFAULT_ROLLUP),
    "pending_siblings": [],
}


class ReviewStateStore:
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

    def _review_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "review"

    def path(self, project_id: str, review_node_id: str) -> Path:
        return self._review_dir(project_id) / f"{review_node_id}.json"

    def read_state(self, project_id: str, review_node_id: str) -> dict[str, Any] | None:
        """Read review state. Returns None if file does not exist."""
        with self._lock_registry.for_project(project_id):
            p = self.path(project_id, review_node_id)
            if not p.exists():
                return None
            payload = load_json(p, default=None)
            return self._normalize_state(payload)

    def write_state(
        self, project_id: str, review_node_id: str, state: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_state(state)
            target = self.path(project_id, review_node_id)
            ensure_dir(target.parent)
            atomic_write_json(target, normalized)
            return copy.deepcopy(normalized)

    def add_checkpoint(
        self,
        project_id: str,
        review_node_id: str,
        sha: str,
        summary: str | None = None,
        source_node_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a checkpoint to the checkpoint list."""
        with self._lock_registry.for_project(project_id):
            state = self._read_unlocked(project_id, review_node_id)
            checkpoints = state.get("checkpoints", [])
            label = f"K{len(checkpoints)}"
            checkpoint: dict[str, Any] = {
                "label": label,
                "sha": sha,
                "summary": summary,
                "source_node_id": source_node_id,
                "accepted_at": iso_now(),
            }
            checkpoints.append(checkpoint)
            state["checkpoints"] = checkpoints
            return self._write_unlocked(project_id, review_node_id, state)

    def set_rollup(
        self,
        project_id: str,
        review_node_id: str,
        status: str,
        summary: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Update the rollup state. Enforces forward-only transitions:
        pending -> ready -> accepted.  No backward transitions allowed.
        Transitioning to 'accepted' requires both summary and sha."""
        with self._lock_registry.for_project(project_id):
            state = self._read_unlocked(project_id, review_node_id)
            rollup = state.get("rollup", copy.deepcopy(_DEFAULT_ROLLUP))
            current = rollup.get("status", "pending")

            if status != current:
                allowed_next = _ROLLUP_TRANSITIONS.get(current)
                if allowed_next != status:
                    raise InvalidRequest(
                        f"Invalid rollup transition: {current} -> {status}. "
                        f"Allowed: {current} -> {allowed_next}."
                    )

            if status == "accepted":
                if not summary or not summary.strip():
                    raise InvalidRequest(
                        "Rollup transition to 'accepted' requires a non-empty summary."
                    )
                if not sha or not sha.strip():
                    raise InvalidRequest(
                        "Rollup transition to 'accepted' requires a non-empty sha."
                    )
                rollup["summary"] = summary.strip()
                rollup["sha"] = sha.strip()
                rollup["accepted_at"] = iso_now()
            else:
                if summary is not None:
                    rollup["summary"] = summary
                if sha is not None:
                    rollup["sha"] = sha

            rollup["status"] = status
            state["rollup"] = rollup
            return self._write_unlocked(project_id, review_node_id, state)

    def get_next_pending_sibling(
        self, project_id: str, review_node_id: str
    ) -> dict[str, Any] | None:
        """Get the next unmaterialized sibling."""
        with self._lock_registry.for_project(project_id):
            state = self._read_unlocked(project_id, review_node_id)
            for sib in state.get("pending_siblings", []):
                if sib.get("materialized_node_id") is None:
                    return copy.deepcopy(sib)
            return None

    def mark_sibling_materialized(
        self, project_id: str, review_node_id: str, index: int, node_id: str
    ) -> dict[str, Any]:
        """Mark a pending sibling as materialized with its created node_id."""
        with self._lock_registry.for_project(project_id):
            state = self._read_unlocked(project_id, review_node_id)
            for sib in state.get("pending_siblings", []):
                if sib.get("index") == index:
                    sib["materialized_node_id"] = node_id
                    break
            return self._write_unlocked(project_id, review_node_id, state)

    # ── Internal (caller holds lock) ──────────────────────────────

    def _read_unlocked(self, project_id: str, review_node_id: str) -> dict[str, Any]:
        p = self.path(project_id, review_node_id)
        if not p.exists():
            return copy.deepcopy(_DEFAULT_STATE)
        payload = load_json(p, default=None)
        return self._normalize_state(payload)

    def _write_unlocked(
        self, project_id: str, review_node_id: str, state: dict[str, Any]
    ) -> dict[str, Any]:
        normalized = self._normalize_state(state)
        target = self.path(project_id, review_node_id)
        ensure_dir(target.parent)
        atomic_write_json(target, normalized)
        return copy.deepcopy(normalized)

    # ── Normalization ────────────────────────────────────────────

    def _normalize_state(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return copy.deepcopy(_DEFAULT_STATE)

        raw_checkpoints = payload.get("checkpoints")
        raw_rollup = payload.get("rollup")
        raw_siblings = payload.get("pending_siblings")

        checkpoints: list[dict[str, Any]] = []
        if isinstance(raw_checkpoints, list):
            for cp in raw_checkpoints:
                normalized = self._normalize_checkpoint(cp)
                if normalized is not None:
                    checkpoints.append(normalized)

        siblings: list[dict[str, Any]] = []
        if isinstance(raw_siblings, list):
            for sib in raw_siblings:
                normalized = self._normalize_pending_sibling(sib)
                if normalized is not None:
                    siblings.append(normalized)

        return {
            "checkpoints": checkpoints,
            "rollup": self._normalize_rollup(raw_rollup),
            "pending_siblings": siblings,
        }

    def _normalize_checkpoint(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        label = raw.get("label")
        sha = raw.get("sha")
        if not isinstance(label, str) or not label.strip():
            return None
        if not isinstance(sha, str) or not sha.strip():
            return None

        summary = raw.get("summary")
        source_node_id = raw.get("source_node_id")
        accepted_at = raw.get("accepted_at")

        return {
            "label": label.strip(),
            "sha": sha.strip(),
            "summary": summary.strip() if isinstance(summary, str) and summary.strip() else None,
            "source_node_id": (
                source_node_id.strip()
                if isinstance(source_node_id, str) and source_node_id.strip()
                else None
            ),
            "accepted_at": accepted_at.strip() if isinstance(accepted_at, str) and accepted_at.strip() else iso_now(),
        }

    def _normalize_rollup(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return copy.deepcopy(_DEFAULT_ROLLUP)

        status = raw.get("status")
        summary = raw.get("summary")
        sha = raw.get("sha")
        accepted_at = raw.get("accepted_at")

        return {
            "status": status if isinstance(status, str) and status in _VALID_ROLLUP_STATUSES else "pending",
            "summary": summary.strip() if isinstance(summary, str) and summary.strip() else None,
            "sha": sha.strip() if isinstance(sha, str) and sha.strip() else None,
            "accepted_at": accepted_at.strip() if isinstance(accepted_at, str) and accepted_at.strip() else None,
        }

    def _normalize_pending_sibling(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        index = raw.get("index")
        title = raw.get("title")
        objective = raw.get("objective")
        if not isinstance(index, int) or index < 1:
            return None
        if not isinstance(title, str) or not title.strip():
            return None
        if not isinstance(objective, str) or not objective.strip():
            return None

        materialized_node_id = raw.get("materialized_node_id")

        return {
            "index": index,
            "title": title.strip(),
            "objective": objective.strip(),
            "materialized_node_id": (
                materialized_node_id.strip()
                if isinstance(materialized_node_id, str) and materialized_node_id.strip()
                else None
            ),
        }
