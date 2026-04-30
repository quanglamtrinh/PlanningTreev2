from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.business.workflow_v2.models import (
    NodeWorkflowStateV2,
    WORKFLOW_SCHEMA_VERSION,
    default_workflow_state,
    utc_now_iso,
)
from backend.storage.file_utils import atomic_write_json, ensure_dir, load_json
from backend.storage.storage import Storage


class WorkflowStateRepositoryV2:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def canonical_path(self, project_id: str, node_id: str) -> Path:
        return self._project_dir(project_id) / "workflow_core_v2" / f"{node_id}.json"

    def read_state(self, project_id: str, node_id: str) -> NodeWorkflowStateV2:
        with self._storage.project_lock(project_id):
            canonical_path = self.canonical_path(project_id, node_id)
            if canonical_path.exists():
                return self._normalize_canonical_state(
                    load_json(canonical_path, default={}),
                    project_id=project_id,
                    node_id=node_id,
                )
            return default_workflow_state(project_id, node_id)

    def write_state(
        self,
        project_id: str,
        node_id: str,
        state: NodeWorkflowStateV2,
    ) -> NodeWorkflowStateV2:
        with self._storage.project_lock(project_id):
            target = self.canonical_path(project_id, node_id)
            previous = None
            if target.exists():
                previous = self._normalize_canonical_state(
                    load_json(target, default={}),
                    project_id=project_id,
                    node_id=node_id,
                )
            now = utc_now_iso()
            next_state = state.model_copy(
                deep=True,
                update={
                    "schema_version": WORKFLOW_SCHEMA_VERSION,
                    "project_id": project_id,
                    "node_id": node_id,
                    "state_version": (previous.state_version + 1 if previous else state.state_version + 1),
                    "created_at": previous.created_at if previous else (state.created_at or now),
                    "updated_at": now,
                },
            )
            ensure_dir(target.parent)
            payload = next_state.model_dump(mode="json", exclude_none=False)
            if "execution_projection" in payload:
                payload["executionProjection"] = payload.pop("execution_projection")
            if "review_package" in payload:
                payload["reviewPackage"] = payload.pop("review_package")
            payload["thread_bindings"] = {
                role: binding.model_dump(by_alias=True, mode="json", exclude_none=False)
                for role, binding in next_state.thread_bindings.items()
            }
            atomic_write_json(target, payload)
            return next_state.model_copy(deep=True)

    def _project_dir(self, project_id: str) -> Path:
        folder_path = self._storage.workspace_store.get_folder_path(project_id)
        return Path(folder_path).expanduser().resolve() / ".planningtree"

    def _normalize_canonical_state(
        self,
        payload: Any,
        *,
        project_id: str,
        node_id: str,
    ) -> NodeWorkflowStateV2:
        source = payload if isinstance(payload, dict) else {}
        if source.get("schema_version") != WORKFLOW_SCHEMA_VERSION:
            source = {**source, "schema_version": WORKFLOW_SCHEMA_VERSION}
        if "executionProjection" in source and "execution_projection" not in source:
            source = {**source, "execution_projection": source.get("executionProjection")}
        if "reviewPackage" in source and "review_package" not in source:
            source = {**source, "review_package": source.get("reviewPackage")}
        return NodeWorkflowStateV2.model_validate(
            {
                **source,
                "project_id": project_id,
                "node_id": node_id,
            }
        )
