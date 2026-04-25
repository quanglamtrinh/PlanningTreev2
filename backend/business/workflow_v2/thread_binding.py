from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import uuid
from typing import Any

from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.context_packets import PlanningTreeContextPacket
from backend.business.workflow_v2.errors import (
    WorkflowIdempotencyConflictError,
    WorkflowThreadBindingFailedError,
)
from backend.business.workflow_v2.models import (
    NodeWorkflowStateV2,
    SourceVersions,
    ThreadBinding,
    ThreadRole,
    utc_now_iso,
    workflow_state_to_response,
)
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.state_machine import derive_allowed_actions
from backend.business.workflow_v2.events import WorkflowEventPublisherV2

_ROLE_THREAD_ATTR: dict[str, str] = {
    "ask_planning": "ask_thread_id",
    "execution": "execution_thread_id",
    "audit": "audit_thread_id",
    "package_review": "package_review_thread_id",
}

_IDEMPOTENCY_ACTION = "ensure_thread"
logger = logging.getLogger(__name__)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _thread_id_looks_like_native_session_uuid(thread_id: str) -> bool:
    t = str(thread_id or "").strip()
    if not t or not _UUID_RE.match(t):
        return False
    try:
        uuid.UUID(t)
    except ValueError:
        return False
    return True


class ThreadBindingServiceV2:
    def __init__(
        self,
        repository: WorkflowStateRepositoryV2,
        context_builder: WorkflowContextBuilderV2,
        session_manager: Any,
        event_publisher: WorkflowEventPublisherV2 | None = None,
    ) -> None:
        self._repository = repository
        self._context_builder = context_builder
        self._session_manager = session_manager
        self._event_publisher = event_publisher

    def reconcile_stale_native_thread_refs(self, project_id: str, node_id: str) -> NodeWorkflowStateV2:
        """
        Drop workflow thread ids that have no row in the native session rollout store
        (e.g. after DB wipe / dev reset). Safe to call on read paths.
        """
        state = self._repository.read_state(project_id, node_id)
        for role in ("ask_planning", "execution", "audit", "package_review"):
            state = self._persist_if_cleared_stale_thread_refs(project_id, node_id, state, role)
        return state

    def _native_rollout_metadata_exists(self, thread_id: str) -> bool:
        tid = str(thread_id or "").strip()
        if not tid:
            return False
        check = getattr(self._session_manager, "native_rollout_metadata_exists", None)
        if callable(check):
            return bool(check(tid))
        return True

    def _idempotency_cached_response_stale(self, cached_response: dict[str, Any]) -> bool:
        """True if the idempotency cache references a thread id with no native rollout row."""
        binding = cached_response.get("binding")
        if not isinstance(binding, dict):
            return False
        tid = _optional_str(binding.get("threadId"))
        if not tid or not _thread_id_looks_like_native_session_uuid(tid):
            return False
        return not self._native_rollout_metadata_exists(tid)

    def _persist_if_cleared_stale_thread_refs(
        self,
        project_id: str,
        node_id: str,
        state: NodeWorkflowStateV2,
        role: ThreadRole,
    ) -> NodeWorkflowStateV2:
        thread_attr = _ROLE_THREAD_ATTR[str(role)]
        binding = state.thread_bindings.get(role)
        legacy = _optional_str(getattr(state, thread_attr, None))
        stale_binding = binding is not None and not self._native_rollout_metadata_exists(binding.thread_id)
        # Only auto-clear *legacy* column ids that look like native session UUIDs (v2 rollout store).
        # v3 string ids like "review-thread-1" are kept so GET workflow-state can still return them.
        stale_legacy = (
            legacy is not None
            and not self._native_rollout_metadata_exists(legacy)
            and _thread_id_looks_like_native_session_uuid(legacy)
        )
        if not stale_binding and not stale_legacy:
            return state

        if stale_binding and binding is not None:
            logger.warning(
                "workflow_v2: clearing %s role binding; native session rollout is missing for thread %s",
                str(role),
                binding.thread_id,
            )
        if stale_legacy and legacy is not None:
            logger.warning(
                "workflow_v2: clearing %s; native session rollout is missing for thread %s",
                thread_attr,
                legacy,
            )
        if stale_binding:
            new_bindings: dict[str, ThreadBinding] = {k: v for k, v in state.thread_bindings.items() if k != role}
        else:
            new_bindings = dict(state.thread_bindings)
        return self._repository.write_state(
            project_id,
            node_id,
            state.model_copy(
                deep=True,
                update={"thread_bindings": new_bindings, thread_attr: None},
            ),
        )

    def ensure_thread(
        self,
        *,
        project_id: str,
        node_id: str,
        role: ThreadRole,
        idempotency_key: str,
        model: str | None = None,
        model_provider: str | None = None,
    ) -> dict[str, Any]:
        key = idempotency_key.strip()
        if not key:
            raise WorkflowThreadBindingFailedError(
                "idempotencyKey is required.",
                details={"projectId": project_id, "nodeId": node_id, "role": role},
            )

        state = self._repository.read_state(project_id, node_id)
        state = self._persist_if_cleared_stale_thread_refs(project_id, node_id, state, role)
        packet = self._context_builder.build_context_packet(
            project_id=project_id,
            node_id=node_id,
            role=role,
            workflow_state=state,
        )
        packet_hash = packet.packet_hash()
        payload_hash = _payload_hash(
            {
                "action": _IDEMPOTENCY_ACTION,
                "projectId": project_id,
                "nodeId": node_id,
                "role": role,
                "model": model,
                "modelProvider": model_provider,
                "contextPacketHash": packet_hash,
            }
        )
        record_key = _record_key(key)
        existing_record = state.idempotency_records.get(record_key)
        if existing_record is not None:
            if existing_record.get("payloadHash") != payload_hash:
                raise WorkflowIdempotencyConflictError(key)
            cached_response = existing_record.get("response")
            if isinstance(cached_response, dict):
                if not self._idempotency_cached_response_stale(cached_response):
                    return copy.deepcopy(cached_response)
                new_records = {k: v for k, v in state.idempotency_records.items() if k != record_key}
                state = self._repository.write_state(
                    project_id,
                    node_id,
                    state.model_copy(deep=True, update={"idempotency_records": new_records}),
                )
            else:
                replay_state = self._repository.read_state(project_id, node_id)
                replay_binding = replay_state.thread_bindings.get(role)
                if replay_binding is None:
                    raise WorkflowThreadBindingFailedError(
                        "Idempotency record exists but thread binding is missing.",
                        details={"projectId": project_id, "nodeId": node_id, "role": role},
                    )
                return _response(replay_state, replay_binding)

        binding = state.thread_bindings.get(role)
        thread_attr = _ROLE_THREAD_ATTR[str(role)]
        legacy_thread_id = _optional_str(getattr(state, thread_attr, None))
        source_versions = SourceVersions.model_validate(packet.source_versions)

        if binding is not None and _binding_matches(binding, packet_hash, source_versions):
            persisted = self._persist_binding(
                state,
                role=role,
                binding=binding,
                thread_attr=thread_attr,
                payload_hash=payload_hash,
                record_key=record_key,
            )
            self._publish_state_changed(
                persisted,
                details={"reason": "binding_reused", "role": role},
            )
            logger.info(
                "workflow_v2 thread binding reused",
                extra={
                    "idempotencyKey": key,
                    "projectId": project_id,
                    "nodeId": node_id,
                    "role": role,
                    "threadId": binding.thread_id,
                    "contextPacketHash": packet_hash,
                },
            )
            persisted_binding = persisted.thread_bindings[role]
            return _response(persisted, persisted_binding)

        if binding is not None:
            update_packet = self._context_builder.build_context_update_packet(
                project_id=project_id,
                node_id=node_id,
                role=role,
                previous_context_packet_hash=binding.context_packet_hash,
                next_packet=packet,
            )
            self._inject_context(
                thread_id=binding.thread_id,
                role=role,
                packet=update_packet,
                idempotency_key=key,
                context_packet_hash=packet_hash,
            )
            next_binding = _updated_binding(
                binding,
                source_versions=source_versions,
                context_packet_hash=packet_hash,
            )
            next_state = self._persist_binding(
                state,
                role=role,
                binding=next_binding,
                thread_attr=thread_attr,
                payload_hash=payload_hash,
                record_key=record_key,
            )
            self._publish_state_changed(
                next_state,
                details={"reason": "context_updated", "role": role},
            )
            logger.info(
                "workflow_v2 thread context updated",
                extra={
                    "idempotencyKey": key,
                    "projectId": project_id,
                    "nodeId": node_id,
                    "role": role,
                    "threadId": binding.thread_id,
                    "contextPacketHash": packet_hash,
                },
            )
            return _response(next_state, next_binding)

        if legacy_thread_id:
            self._inject_context(
                thread_id=legacy_thread_id,
                role=role,
                packet=packet,
                idempotency_key=key,
            )
            next_binding = _new_binding(
                project_id=project_id,
                node_id=node_id,
                role=role,
                thread_id=legacy_thread_id,
                created_from="legacy_adopted",
                source_versions=source_versions,
                context_packet_hash=packet_hash,
            )
            next_state = self._persist_binding(
                state,
                role=role,
                binding=next_binding,
                thread_attr=thread_attr,
                payload_hash=payload_hash,
                record_key=record_key,
            )
            self._publish_state_changed(
                next_state,
                details={"reason": "legacy_adopted", "role": role},
            )
            logger.info(
                "workflow_v2 thread binding adopted legacy thread",
                extra={
                    "idempotencyKey": key,
                    "projectId": project_id,
                    "nodeId": node_id,
                    "role": role,
                    "threadId": legacy_thread_id,
                    "contextPacketHash": packet_hash,
                },
            )
            return _response(next_state, next_binding)

        thread_id = self._start_thread(
            cwd=_optional_str(packet.payload.get("workspaceRoot")),
            model=model,
            model_provider=model_provider,
        )
        self._inject_context(
            thread_id=thread_id,
            role=role,
            packet=packet,
            idempotency_key=key,
        )
        next_binding = _new_binding(
            project_id=project_id,
            node_id=node_id,
            role=role,
            thread_id=thread_id,
            created_from="new_thread",
            source_versions=source_versions,
            context_packet_hash=packet_hash,
        )
        next_state = self._persist_binding(
            state,
            role=role,
            binding=next_binding,
            thread_attr=thread_attr,
            payload_hash=payload_hash,
            record_key=record_key,
        )
        self._publish_state_changed(
            next_state,
            details={"reason": "new_thread", "role": role},
        )
        logger.info(
            "workflow_v2 thread binding created new thread",
            extra={
                "idempotencyKey": key,
                "projectId": project_id,
                "nodeId": node_id,
                "role": role,
                "threadId": thread_id,
                "contextPacketHash": packet_hash,
            },
        )
        return _response(next_state, next_binding)

    def _publish_state_changed(
        self,
        state: NodeWorkflowStateV2,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._event_publisher is not None:
            self._event_publisher.publish_state_changed(state, details=details)

    def _start_thread(
        self,
        *,
        cwd: str | None,
        model: str | None,
        model_provider: str | None,
    ) -> str:
        payload: dict[str, Any] = {}
        if cwd:
            payload["cwd"] = cwd
        if model:
            payload["model"] = model
        if model_provider:
            payload["modelProvider"] = model_provider
        response = self._session_manager.thread_start(payload)
        thread_id = _thread_id_from_response(response)
        if not thread_id:
            raise WorkflowThreadBindingFailedError(
                "Session Core did not return a thread id.",
                details={"response": copy.deepcopy(response)},
            )
        return thread_id

    def _inject_context(
        self,
        *,
        thread_id: str,
        role: ThreadRole,
        packet: PlanningTreeContextPacket,
        idempotency_key: str,
        context_packet_hash: str | None = None,
    ) -> None:
        injected_packet_hash = packet.packet_hash()
        action_context_hash = context_packet_hash or injected_packet_hash
        client_action_id = f"{idempotency_key}:inject:{role}:{action_context_hash}"
        metadata = {
            "workflowContext": True,
            "role": role,
            "packetKind": packet.kind,
            "contextPacketHash": action_context_hash,
            "contextPayload": packet.ui_context_payload(),
            "sourceVersions": copy.deepcopy(packet.source_versions),
        }
        if injected_packet_hash != action_context_hash:
            metadata["injectedPacketHash"] = injected_packet_hash
        self._session_manager.thread_inject_items(
            thread_id=thread_id,
            payload={
                "clientActionId": client_action_id,
                "items": [
                    {
                        "id": f"workflow-context-{role}-{_hash_suffix(action_context_hash)}",
                        "type": "systemMessage",
                        "text": packet.render_model_visible_message(),
                        "metadata": metadata,
                        "workflowContext": copy.deepcopy(metadata),
                    }
                ],
            },
        )

    def _persist_binding(
        self,
        state: NodeWorkflowStateV2,
        *,
        role: ThreadRole,
        binding: ThreadBinding,
        thread_attr: str,
        payload_hash: str,
        record_key: str,
    ) -> NodeWorkflowStateV2:
        bindings = dict(state.thread_bindings)
        bindings[role] = binding
        base_state = state.model_copy(
            deep=True,
            update={
                thread_attr: binding.thread_id,
                "thread_bindings": bindings,
                "frame_version": binding.source_versions.frame_version,
                "spec_version": binding.source_versions.spec_version,
                "split_manifest_version": binding.source_versions.split_manifest_version,
            },
        )
        projected_state = base_state.model_copy(
            deep=True,
            update={"state_version": state.state_version + 1},
        )
        idempotency_records = copy.deepcopy(state.idempotency_records)
        idempotency_records[record_key] = {
            "action": _IDEMPOTENCY_ACTION,
            "payloadHash": payload_hash,
            "role": role,
            "threadId": binding.thread_id,
            "contextPacketHash": binding.context_packet_hash,
            "response": _response(projected_state, binding),
        }
        next_state = base_state.model_copy(
            deep=True,
            update={"idempotency_records": idempotency_records},
        )
        return self._repository.write_state(state.project_id, state.node_id, next_state)


def _new_binding(
    *,
    project_id: str,
    node_id: str,
    role: ThreadRole,
    thread_id: str,
    created_from: str,
    source_versions: SourceVersions,
    context_packet_hash: str,
) -> ThreadBinding:
    now = utc_now_iso()
    return ThreadBinding(
        projectId=project_id,
        nodeId=node_id,
        role=role,
        threadId=thread_id,
        createdFrom=created_from,
        sourceVersions=source_versions,
        contextPacketHash=context_packet_hash,
        createdAt=now,
        updatedAt=now,
    )


def _updated_binding(
    binding: ThreadBinding,
    *,
    source_versions: SourceVersions,
    context_packet_hash: str,
) -> ThreadBinding:
    return binding.model_copy(
        deep=True,
        update={
            "source_versions": source_versions,
            "context_packet_hash": context_packet_hash,
            "updated_at": utc_now_iso(),
        },
    )


def _binding_matches(
    binding: ThreadBinding,
    context_packet_hash: str,
    source_versions: SourceVersions,
) -> bool:
    return (
        binding.context_packet_hash == context_packet_hash
        and binding.source_versions.model_dump(mode="json") == source_versions.model_dump(mode="json")
    )


def _response(state: NodeWorkflowStateV2, binding: ThreadBinding) -> dict[str, Any]:
    return {
        "binding": binding.model_dump(by_alias=True, mode="json", exclude_none=False),
        "workflowState": workflow_state_to_response(
            state,
            allowed_actions=derive_allowed_actions(state),
        ).to_public_dict(),
    }


def _record_key(idempotency_key: str) -> str:
    return f"{_IDEMPOTENCY_ACTION}:{idempotency_key}"


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _thread_id_from_response(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    thread = response.get("thread")
    if isinstance(thread, dict):
        thread_id = _optional_str(thread.get("id") or thread.get("threadId"))
        if thread_id:
            return thread_id
    return _optional_str(response.get("threadId") or response.get("id"))


def _hash_suffix(packet_hash: str) -> str:
    return packet_hash.rsplit(":", 1)[-1][:16]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
