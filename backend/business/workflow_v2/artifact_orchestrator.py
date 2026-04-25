from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.business.workflow_v2.errors import (
    WorkflowIdempotencyConflictError,
    WorkflowThreadBindingFailedError,
)
from backend.business.workflow_v2.models import NodeWorkflowStateV2, SourceVersions, workflow_state_to_response
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.state_machine import derive_allowed_actions
from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2
from backend.business.workflow_v2.events import WorkflowEventPublisherV2
from backend.services import planningtree_workspace
from backend.services.node_detail_service import (
    _load_clarify_from_node_dir,
    _load_frame_meta_from_node_dir,
    _load_spec_meta_from_node_dir,
)
from backend.storage.storage import Storage


class ArtifactOrchestratorV2:
    def __init__(
        self,
        *,
        repository: WorkflowStateRepositoryV2,
        thread_binding_service: ThreadBindingServiceV2,
        event_publisher: WorkflowEventPublisherV2 | None,
        storage: Storage,
        node_detail_service: Any,
        frame_generation_service: Any,
        clarify_generation_service: Any,
        spec_generation_service: Any,
        split_service: Any,
    ) -> None:
        self._repository = repository
        self._thread_binding_service = thread_binding_service
        self._event_publisher = event_publisher
        self._storage = storage
        self._node_detail_service = node_detail_service
        self._frame_generation_service = frame_generation_service
        self._clarify_generation_service = clarify_generation_service
        self._spec_generation_service = spec_generation_service
        self._split_service = split_service

    def get_artifact_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        return self._artifact_state(project_id, node_id)

    def start_frame_generation(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._run_idempotent_mutation(
            project_id,
            node_id,
            action="artifact.frame.generate",
            idempotency_key=idempotency_key,
            payload={"projectId": project_id, "nodeId": node_id},
            execute=lambda: self._start_generation(
                project_id,
                node_id,
                kind="frame",
                service_method=self._frame_generation_service.generate_frame,
            ),
        )

    def get_frame_generation_status(self, project_id: str, node_id: str) -> dict[str, Any]:
        status = self._frame_generation_service.get_generation_status(project_id, node_id)
        return self._status_response(project_id, node_id, "frame", status)

    def confirm_frame(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._run_idempotent_mutation(
            project_id,
            node_id,
            action="artifact.frame.confirm",
            idempotency_key=idempotency_key,
            payload={"projectId": project_id, "nodeId": node_id},
            execute=lambda: self._confirm_artifact(
                project_id,
                node_id,
                kind="frame",
                confirm=lambda: self._node_detail_service.confirm_frame(project_id, node_id),
                reason="frame_confirmed",
            ),
        )

    def start_clarify_generation(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._run_idempotent_mutation(
            project_id,
            node_id,
            action="artifact.clarify.generate",
            idempotency_key=idempotency_key,
            payload={"projectId": project_id, "nodeId": node_id},
            execute=lambda: self._start_generation(
                project_id,
                node_id,
                kind="clarify",
                service_method=self._clarify_generation_service.generate_clarify,
            ),
        )

    def get_clarify(self, project_id: str, node_id: str) -> dict[str, Any]:
        return self._node_detail_service.get_clarify(project_id, node_id)

    def update_clarify(
        self,
        project_id: str,
        node_id: str,
        *,
        answers: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            return self._run_idempotent_mutation(
                project_id,
                node_id,
                action="artifact.clarify.update",
                idempotency_key=idempotency_key,
                payload={"projectId": project_id, "nodeId": node_id, "answers": answers},
                execute=lambda: self._clarify_update_response(project_id, node_id, answers),
            )
        return self._clarify_update_response(project_id, node_id, answers)

    def get_clarify_generation_status(self, project_id: str, node_id: str) -> dict[str, Any]:
        status = self._clarify_generation_service.get_generation_status(project_id, node_id)
        return self._status_response(project_id, node_id, "clarify", status)

    def confirm_clarify(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._run_idempotent_mutation(
            project_id,
            node_id,
            action="artifact.clarify.confirm",
            idempotency_key=idempotency_key,
            payload={"projectId": project_id, "nodeId": node_id},
            execute=lambda: self._confirm_artifact(
                project_id,
                node_id,
                kind="clarify",
                confirm=lambda: self._node_detail_service.apply_clarify_to_frame(project_id, node_id),
                reason="clarify_confirmed",
            ),
        )

    def start_spec_generation(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._run_idempotent_mutation(
            project_id,
            node_id,
            action="artifact.spec.generate",
            idempotency_key=idempotency_key,
            payload={"projectId": project_id, "nodeId": node_id},
            execute=lambda: self._start_generation(
                project_id,
                node_id,
                kind="spec",
                service_method=self._spec_generation_service.generate_spec,
                sync_reason="spec_generation_started",
            ),
        )

    def get_spec_generation_status(self, project_id: str, node_id: str) -> dict[str, Any]:
        status = self._spec_generation_service.get_generation_status(project_id, node_id)
        return self._status_response(project_id, node_id, "spec", status)

    def confirm_spec(
        self,
        project_id: str,
        node_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._run_idempotent_mutation(
            project_id,
            node_id,
            action="artifact.spec.confirm",
            idempotency_key=idempotency_key,
            payload={"projectId": project_id, "nodeId": node_id},
            execute=lambda: self._confirm_artifact(
                project_id,
                node_id,
                kind="spec",
                confirm=lambda: self._node_detail_service.confirm_spec(project_id, node_id),
                reason="spec_confirmed",
            ),
        )

    def start_split(
        self,
        project_id: str,
        node_id: str,
        *,
        mode: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._run_idempotent_mutation(
            project_id,
            node_id,
            action="artifact.split.start",
            idempotency_key=idempotency_key,
            payload={"projectId": project_id, "nodeId": node_id, "mode": mode},
            execute=lambda: self._start_split(project_id, node_id, mode),
        )

    def get_split_status(self, project_id: str) -> dict[str, Any]:
        status = self._split_service.get_split_status(project_id)
        node_id = str(status.get("node_id") or "").strip()
        if not node_id:
            return {**status, "artifactState": None, "workflowState": None}
        return self._status_response(project_id, node_id, "split", status)

    def sync_artifact_source_versions(
        self,
        project_id: str,
        node_id: str,
        *,
        reason: str,
    ) -> NodeWorkflowStateV2:
        state = self._repository.read_state(project_id, node_id)
        versions = self._current_source_versions(project_id, node_id)
        updates: dict[str, Any] = {}
        if state.frame_version != versions.frame_version:
            updates["frame_version"] = versions.frame_version
        if state.spec_version != versions.spec_version:
            updates["spec_version"] = versions.spec_version
        if state.split_manifest_version != versions.split_manifest_version:
            updates["split_manifest_version"] = versions.split_manifest_version

        persisted = state
        if updates:
            persisted = self._repository.write_state(
                project_id,
                node_id,
                state.model_copy(deep=True, update=updates),
            )
            if self._event_publisher is not None:
                self._event_publisher.publish_state_changed(
                    persisted,
                    details={
                        "reason": reason,
                        "sourceVersions": versions.model_dump(by_alias=True, mode="json"),
                    },
                )
        return persisted

    def _start_generation(
        self,
        project_id: str,
        node_id: str,
        *,
        kind: str,
        service_method: Any,
        sync_reason: str | None = None,
    ) -> dict[str, Any]:
        accepted = service_method(project_id, node_id)
        if sync_reason:
            workflow_state = self.sync_artifact_source_versions(project_id, node_id, reason=sync_reason)
        else:
            workflow_state = self._repository.read_state(project_id, node_id)
        response = {
            **accepted,
            "accepted": True,
            "job": _job_from_accepted(kind, accepted),
            "artifactState": self._artifact_state(project_id, node_id),
            "workflowState": _workflow_response(workflow_state),
        }
        self._publish_artifact_event(
            workflow_state,
            "workflow/artifact_job_started",
            details={"artifact": kind, "job": copy.deepcopy(response["job"])},
        )
        return response

    def _start_split(self, project_id: str, node_id: str, mode: str) -> dict[str, Any]:
        accepted = self._split_service.split_node(project_id, node_id, mode)
        workflow_state = self.sync_artifact_source_versions(project_id, node_id, reason="split_started")
        response = {
            **accepted,
            "accepted": True,
            "job": _job_from_accepted("split", accepted),
            "artifactState": self._artifact_state(project_id, node_id),
            "workflowState": _workflow_response(workflow_state),
        }
        self._publish_artifact_event(
            workflow_state,
            "workflow/artifact_job_started",
            details={"artifact": "split", "job": copy.deepcopy(response["job"])},
        )
        return response

    def _confirm_artifact(
        self,
        project_id: str,
        node_id: str,
        *,
        kind: str,
        confirm: Any,
        reason: str,
    ) -> dict[str, Any]:
        detail_state = confirm()
        workflow_state = self.sync_artifact_source_versions(project_id, node_id, reason=reason)
        artifact = self._artifact_summary(project_id, node_id, kind)
        response = {
            "confirmed": True,
            "artifact": artifact,
            "artifactState": self._artifact_state(project_id, node_id),
            "detailState": detail_state,
            "workflowState": _workflow_response(workflow_state),
        }
        self._publish_artifact_event(
            workflow_state,
            "workflow/artifact_confirmed",
            details={"artifact": kind, "reason": reason, **artifact},
        )
        self._publish_artifact_event(
            workflow_state,
            "workflow/artifact_state_changed",
            details={"artifact": kind, "reason": reason},
        )
        return response

    def _clarify_update_response(self, project_id: str, node_id: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
        clarify = self._node_detail_service.update_clarify_answers(project_id, node_id, answers)
        state = self._repository.read_state(project_id, node_id)
        self._publish_artifact_event(
            state,
            "workflow/artifact_state_changed",
            details={"artifact": "clarify", "reason": "clarify_updated"},
        )
        return {
            "clarify": clarify,
            "artifactState": self._artifact_state(project_id, node_id),
            "workflowState": _workflow_response(state),
        }

    def _status_response(self, project_id: str, node_id: str, kind: str, status: dict[str, Any]) -> dict[str, Any]:
        state = self._repository.read_state(project_id, node_id)
        status_value = str(status.get("status") or "")
        event_type = None
        if status_value == "failed":
            event_type = "workflow/artifact_job_failed"
        elif status_value == "idle" and status.get("completed_at"):
            event_type = "workflow/artifact_job_completed"
        if event_type is not None:
            self._publish_artifact_status_once(state, kind, status, event_type)
        return {
            **status,
            "artifactState": self._artifact_state(project_id, node_id),
            "workflowState": _workflow_response(state),
        }

    def _run_idempotent_mutation(
        self,
        project_id: str,
        node_id: str,
        *,
        action: str,
        idempotency_key: str,
        payload: dict[str, Any],
        execute: Any,
    ) -> dict[str, Any]:
        key = idempotency_key.strip()
        if not key:
            raise WorkflowThreadBindingFailedError(
                "idempotencyKey is required.",
                details={"projectId": project_id, "nodeId": node_id, "action": action},
            )
        record_key = f"{action}:{key}"
        payload_hash = _payload_hash({"action": action, **payload})
        state = self._repository.read_state(project_id, node_id)
        existing = state.idempotency_records.get(record_key)
        if existing is not None:
            if existing.get("payloadHash") != payload_hash:
                raise WorkflowIdempotencyConflictError(key)
            response = existing.get("response")
            if isinstance(response, dict):
                return copy.deepcopy(response)

        response = execute()
        latest_state = self._repository.read_state(project_id, node_id)
        projected_state = latest_state.model_copy(
            deep=True,
            update={"state_version": latest_state.state_version + 1},
        )
        cached_response = _replace_workflow_state(response, projected_state)
        records = copy.deepcopy(latest_state.idempotency_records)
        records[record_key] = {
            "action": action,
            "payloadHash": payload_hash,
            "response": copy.deepcopy(cached_response),
        }
        persisted = self._repository.write_state(
            project_id,
            node_id,
            latest_state.model_copy(deep=True, update={"idempotency_records": records}),
        )
        return _replace_workflow_state(response, persisted)

    def _artifact_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        detail_state = self._node_detail_service.get_detail_state(project_id, node_id)
        versions = self._current_source_versions(project_id, node_id)
        clarify = self._safe_get_clarify(project_id, node_id)
        frame_status = self._safe_status(self._frame_generation_service, project_id, node_id)
        clarify_status = self._safe_status(self._clarify_generation_service, project_id, node_id)
        spec_status = self._safe_status(self._spec_generation_service, project_id, node_id)
        split_status = self._safe_split_status(project_id)
        return {
            "schemaVersion": 1,
            "projectId": project_id,
            "nodeId": node_id,
            "versions": {
                "frameVersion": detail_state.get("frame_revision"),
                "confirmedFrameVersion": detail_state.get("frame_confirmed_revision"),
                "specVersion": versions.spec_version,
                "splitManifestVersion": versions.split_manifest_version,
            },
            "artifacts": {
                "frame": {
                    "confirmed": bool(detail_state.get("frame_confirmed")),
                    "confirmedAt": self._artifact_summary(project_id, node_id, "frame").get("confirmedAt"),
                    "needsReconfirm": bool(detail_state.get("frame_needs_reconfirm")),
                },
                "clarify": {
                    "confirmed": bool(detail_state.get("clarify_confirmed")),
                    "sourceFrameVersion": clarify.get("source_frame_revision") if isinstance(clarify, dict) else None,
                    "openQuestions": _open_clarify_questions(clarify),
                },
                "spec": {
                    "confirmed": bool(detail_state.get("spec_confirmed")),
                    "sourceFrameVersion": versions.spec_version,
                    "stale": bool(detail_state.get("spec_stale")),
                },
                "split": {
                    "status": split_status.get("status"),
                    "mode": split_status.get("mode"),
                    "jobId": split_status.get("job_id"),
                },
            },
            "jobs": {
                "frame": _job_status(frame_status),
                "clarify": _job_status(clarify_status),
                "spec": _job_status(spec_status),
                "split": _job_status(split_status),
            },
            "detailState": detail_state,
        }

    def _current_source_versions(self, project_id: str, node_id: str) -> SourceVersions:
        node_dir = self._node_dir(project_id, node_id)
        frame_meta = _load_frame_meta_from_node_dir(node_dir)
        spec_meta = _load_spec_meta_from_node_dir(node_dir)
        frame_version = _optional_int(frame_meta.get("confirmed_revision"))
        if frame_version is not None and frame_version < 1:
            frame_version = None
        spec_version = None
        if spec_meta.get("confirmed_at"):
            spec_version = _optional_int(spec_meta.get("source_frame_revision"))
        return SourceVersions(
            frameVersion=frame_version,
            specVersion=spec_version,
            splitManifestVersion=None,
        )

    def _artifact_summary(self, project_id: str, node_id: str, kind: str) -> dict[str, Any]:
        node_dir = self._node_dir(project_id, node_id)
        if kind == "frame":
            meta = _load_frame_meta_from_node_dir(node_dir)
            return {
                "kind": "frame",
                "frameVersion": _optional_int(meta.get("confirmed_revision")),
                "confirmedAt": meta.get("confirmed_at"),
            }
        if kind == "spec":
            meta = _load_spec_meta_from_node_dir(node_dir)
            return {
                "kind": "spec",
                "specVersion": _optional_int(meta.get("source_frame_revision")) if meta.get("confirmed_at") else None,
                "confirmedAt": meta.get("confirmed_at"),
            }
        if kind == "clarify":
            clarify = _load_clarify_from_node_dir(node_dir) or {}
            return {
                "kind": "clarify",
                "clarifyVersion": _optional_int(clarify.get("confirmed_revision")),
                "confirmedAt": clarify.get("confirmed_at"),
            }
        return {"kind": kind}

    def _node_dir(self, project_id: str, node_id: str) -> Path:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            project = snapshot.get("project") if isinstance(snapshot.get("project"), dict) else {}
            workspace_root = str(project.get("project_path") or "").strip()
            if not workspace_root:
                raise WorkflowThreadBindingFailedError(
                    "Project snapshot is missing project_path.",
                    details={"projectId": project_id, "nodeId": node_id},
                )
            node_dir = planningtree_workspace.resolve_node_dir(Path(workspace_root), snapshot, node_id)
            if node_dir is None:
                raise WorkflowThreadBindingFailedError(
                    "Node directory was not found.",
                    details={"projectId": project_id, "nodeId": node_id},
                )
            return node_dir

    def _safe_get_clarify(self, project_id: str, node_id: str) -> dict[str, Any] | None:
        try:
            return self._node_detail_service.get_clarify(project_id, node_id)
        except Exception:
            return None

    @staticmethod
    def _safe_status(service: Any, project_id: str, node_id: str) -> dict[str, Any]:
        try:
            return service.get_generation_status(project_id, node_id)
        except Exception:
            return {"status": "idle", "job_id": None, "started_at": None, "completed_at": None, "error": None}

    def _safe_split_status(self, project_id: str) -> dict[str, Any]:
        try:
            return self._split_service.get_split_status(project_id)
        except Exception:
            return {
                "status": "idle",
                "job_id": None,
                "node_id": None,
                "mode": None,
                "started_at": None,
                "completed_at": None,
                "error": None,
            }

    def _publish_artifact_event(
        self,
        state: NodeWorkflowStateV2,
        event_type: str,
        *,
        details: dict[str, Any],
    ) -> None:
        if self._event_publisher is not None:
            self._event_publisher.publish_artifact_event(state, event_type=event_type, details=details)

    def _publish_artifact_status_once(
        self,
        state: NodeWorkflowStateV2,
        kind: str,
        status: dict[str, Any],
        event_type: str,
    ) -> None:
        job_id = status.get("job_id") or "unknown"
        completed_at = status.get("completed_at") or status.get("error") or "unknown"
        record_key = f"artifact.status_event:{kind}:{event_type}:{job_id}:{completed_at}"
        if record_key in state.idempotency_records:
            return
        records = copy.deepcopy(state.idempotency_records)
        records[record_key] = {
            "action": "artifact.status_event",
            "payloadHash": _payload_hash({"kind": kind, "status": status, "eventType": event_type}),
        }
        persisted = self._repository.write_state(
            state.project_id,
            state.node_id,
            state.model_copy(deep=True, update={"idempotency_records": records}),
        )
        self._publish_artifact_event(
            persisted,
            event_type,
            details={"artifact": kind, "job": _job_status(status)},
        )
        self._publish_artifact_event(
            persisted,
            "workflow/artifact_state_changed",
            details={"artifact": kind, "reason": status.get("status")},
        )


def _workflow_response(state: NodeWorkflowStateV2) -> dict[str, Any]:
    return workflow_state_to_response(
        state,
        allowed_actions=derive_allowed_actions(state),
    ).to_public_dict()


def _replace_workflow_state(response: dict[str, Any], state: NodeWorkflowStateV2) -> dict[str, Any]:
    updated = copy.deepcopy(response)
    if "workflowState" in updated:
        updated["workflowState"] = _workflow_response(state)
    return updated


def _job_from_accepted(kind: str, accepted: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobId": accepted.get("job_id"),
        "kind": kind,
        "status": "running",
        "nodeId": accepted.get("node_id"),
        "mode": accepted.get("mode"),
    }


def _job_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status.get("status"),
        "jobId": status.get("job_id"),
        "nodeId": status.get("node_id"),
        "mode": status.get("mode"),
        "startedAt": status.get("started_at"),
        "completedAt": status.get("completed_at"),
        "lastError": status.get("error"),
    }


def _open_clarify_questions(clarify: dict[str, Any] | None) -> int:
    if not isinstance(clarify, dict):
        return 0
    questions = clarify.get("questions")
    if not isinstance(questions, list):
        return 0
    count = 0
    for question in questions:
        if not isinstance(question, dict):
            continue
        if question.get("selected_option_id") is None and not str(question.get("custom_answer") or "").strip():
            count += 1
    return count


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
