from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from backend.business.workflow_v2.context_builder import WorkflowContextBuilderV2
from backend.business.workflow_v2.context_packets import PlanningTreeContextPacket
from backend.business.workflow_v2.errors import (
    WorkflowActionNotAllowedError,
    WorkflowContextNotStaleError,
    WorkflowContextStaleError,
    WorkflowIdempotencyConflictError,
    WorkflowThreadBindingFailedError,
    WorkflowVersionConflictError,
)
from backend.business.workflow_v2.models import (
    ContextStaleBindingV2,
    NodeWorkflowStateV2,
    SourceVersions,
    ThreadBinding,
    ThreadRole,
    utc_now_iso,
    workflow_state_to_response,
)
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.business.workflow_v2.state_machine import derive_allowed_actions, rebase_context as transition_rebase_context
from backend.business.workflow_v2.events import WorkflowEventPublisherV2

_ROLE_THREAD_ATTR: dict[str, str] = {
    "ask_planning": "ask_thread_id",
    "execution": "execution_thread_id",
    "audit": "audit_thread_id",
    "package_review": "package_review_thread_id",
}

_IDEMPOTENCY_ACTION = "ensure_thread"


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

    def ensure_thread(
        self,
        *,
        project_id: str,
        node_id: str,
        role: ThreadRole,
        idempotency_key: str,
        model: str | None = None,
        model_provider: str | None = None,
        force_rebase: bool = False,
    ) -> dict[str, Any]:
        key = idempotency_key.strip()
        if not key:
            raise WorkflowThreadBindingFailedError(
                "idempotencyKey is required.",
                details={"projectId": project_id, "nodeId": node_id, "role": role},
            )

        state = self._repository.read_state(project_id, node_id)
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
                "forceRebase": bool(force_rebase),
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
                return copy.deepcopy(cached_response)
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
            persisted_binding = persisted.thread_bindings[role]
            return _response(persisted, persisted_binding)

        if binding is not None:
            if not force_rebase:
                persisted_stale_state = self._refresh_context_freshness_state(
                    state,
                    publish=True,
                    fallback_reason=f"{role} context packet changed.",
                )
                raise WorkflowContextStaleError(
                    project_id,
                    node_id,
                    reason=persisted_stale_state.context_stale_reason or f"{role} context packet changed.",
                )
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
                details={"reason": "context_rebased", "role": role},
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
        return _response(next_state, next_binding)

    def refresh_context_freshness(self, project_id: str, node_id: str) -> NodeWorkflowStateV2:
        state = self._repository.read_state(project_id, node_id)
        return self._refresh_context_freshness_state(state, publish=True)

    def rebase_context(
        self,
        *,
        project_id: str,
        node_id: str,
        idempotency_key: str,
        expected_workflow_version: int | None = None,
        roles: list[ThreadRole] | None = None,
    ) -> dict[str, Any]:
        key = idempotency_key.strip()
        if not key:
            raise WorkflowThreadBindingFailedError(
                "idempotencyKey is required.",
                details={"projectId": project_id, "nodeId": node_id},
            )
        normalized_roles = _normalize_role_subset(roles)
        payload_hash = _payload_hash(
            {
                "action": "rebase_context",
                "projectId": project_id,
                "nodeId": node_id,
                "expectedWorkflowVersion": expected_workflow_version,
                "roles": normalized_roles,
            }
        )

        state = self._refresh_context_freshness_state(
            self._repository.read_state(project_id, node_id),
            publish=True,
        )
        record_key = _rebase_record_key(key)
        existing_record = state.idempotency_records.get(record_key)
        if existing_record is not None:
            if existing_record.get("payloadHash") != payload_hash:
                raise WorkflowIdempotencyConflictError(key)
            cached_response = existing_record.get("response")
            if isinstance(cached_response, dict):
                return copy.deepcopy(cached_response)

        if expected_workflow_version is not None and state.state_version != expected_workflow_version:
            raise WorkflowVersionConflictError(
                expected_version=expected_workflow_version,
                actual_version=state.state_version,
            )

        if "rebase_context" not in derive_allowed_actions(state):
            if not state.context_stale:
                raise WorkflowContextNotStaleError(project_id, node_id)
            raise WorkflowActionNotAllowedError(
                "rebase_context",
                state.phase,
                allowed_actions=derive_allowed_actions(state),
            )

        stale_details = list(state.context_stale_details)
        if not stale_details:
            stale_details = self._compute_stale_bindings(state)
        if not stale_details:
            raise WorkflowContextNotStaleError(project_id, node_id)

        stale_roles = {detail.role for detail in stale_details}
        target_roles = normalized_roles or sorted(stale_roles)
        invalid_roles = [role for role in target_roles if role not in stale_roles]
        if invalid_roles:
            raise WorkflowActionNotAllowedError(
                "rebase_context",
                state.phase,
                allowed_actions=derive_allowed_actions(state),
                message="Requested rebase roles are not stale.",
            )

        bindings = dict(state.thread_bindings)
        updated_bindings: list[dict[str, Any]] = []
        latest_versions = SourceVersions()

        for role in target_roles:
            binding = bindings.get(role)
            if binding is None:
                raise WorkflowThreadBindingFailedError(
                    "Cannot rebase a missing thread binding.",
                    details={"projectId": project_id, "nodeId": node_id, "role": role},
                )
            next_packet = self._context_builder.build_context_packet(
                project_id=project_id,
                node_id=node_id,
                role=role,
                workflow_state=state,
            )
            next_hash = next_packet.packet_hash()
            latest_versions = SourceVersions.model_validate(next_packet.source_versions)
            update_packet = self._context_builder.build_context_update_packet(
                project_id=project_id,
                node_id=node_id,
                role=role,
                previous_context_packet_hash=binding.context_packet_hash,
                next_packet=next_packet,
            )
            self._inject_context(
                thread_id=binding.thread_id,
                role=role,
                packet=update_packet,
                idempotency_key=key,
                context_packet_hash=next_hash,
            )
            next_binding = _updated_binding(
                binding,
                source_versions=latest_versions,
                context_packet_hash=next_hash,
            )
            bindings[role] = next_binding
            updated_bindings.append(
                {
                    "role": role,
                    "threadId": next_binding.thread_id,
                    "contextPacketHash": next_binding.context_packet_hash,
                }
            )

        if set(target_roles) == stale_roles:
            next_state = transition_rebase_context(
                state.model_copy(deep=True, update={"thread_bindings": bindings}),
                frame_version=latest_versions.frame_version,
                spec_version=latest_versions.spec_version,
                split_manifest_version=latest_versions.split_manifest_version,
            ).model_copy(deep=True, update={"context_stale_details": []})
        else:
            remaining_details = [
                detail for detail in stale_details if detail.role not in set(target_roles)
            ]
            next_state = state.model_copy(
                deep=True,
                update={
                    "thread_bindings": bindings,
                    "context_stale": True,
                    "context_stale_reason": _stale_reason(remaining_details),
                    "context_stale_details": remaining_details,
                },
            )

        projected = next_state.model_copy(deep=True, update={"state_version": next_state.state_version + 1})
        response = _rebase_response(projected, updated_bindings)
        records = copy.deepcopy(next_state.idempotency_records)
        records[record_key] = {
            "action": "rebase_context",
            "payloadHash": payload_hash,
            "response": copy.deepcopy(response),
        }
        persisted = self._repository.write_state(
            project_id,
            node_id,
            next_state.model_copy(deep=True, update={"idempotency_records": records}),
        )
        final_response = _rebase_response(persisted, updated_bindings)
        if self._event_publisher is not None:
            self._event_publisher.publish_action_completed(
                persisted,
                action="rebase_context",
                details={"reason": "context_rebased", "updatedBindings": copy.deepcopy(updated_bindings)},
            )
            self._event_publisher.publish_state_changed(
                persisted,
                details={"reason": "context_rebased", "action": "rebase_context"},
            )
        return final_response

    def _refresh_context_freshness_state(
        self,
        state: NodeWorkflowStateV2,
        *,
        publish: bool,
        fallback_reason: str | None = None,
    ) -> NodeWorkflowStateV2:
        if state.phase in {"done", "blocked"}:
            if state.context_stale or state.context_stale_details:
                cleared = state.model_copy(
                    deep=True,
                    update={
                        "context_stale": False,
                        "context_stale_reason": None,
                        "context_stale_details": [],
                    },
                )
                return self._repository.write_state(state.project_id, state.node_id, cleared)
            return state

        stale_details = self._compute_stale_bindings(state)
        if stale_details:
            reason = _stale_reason(stale_details) or fallback_reason
            if (
                state.context_stale
                and state.context_stale_reason == reason
                and _stale_details_equal(state.context_stale_details, stale_details)
            ):
                return state
            stale_state = state.model_copy(
                deep=True,
                update={
                    "context_stale": True,
                    "context_stale_reason": reason,
                    "context_stale_details": stale_details,
                },
            )
            persisted = self._repository.write_state(state.project_id, state.node_id, stale_state)
            if publish and not state.context_stale:
                details: dict[str, Any] = {
                    "staleBindings": [
                        detail.model_dump(by_alias=True, mode="json") for detail in stale_details
                    ],
                }
                if len(stale_details) == 1:
                    details["role"] = stale_details[0].role
                self._publish_context_stale(persisted, reason=reason, details=details)
            return persisted

        if state.context_stale or state.context_stale_details:
            cleared = state.model_copy(
                deep=True,
                update={
                    "context_stale": False,
                    "context_stale_reason": None,
                    "context_stale_details": [],
                },
            )
            persisted = self._repository.write_state(state.project_id, state.node_id, cleared)
            if publish:
                self._publish_state_changed(persisted, details={"reason": "context_fresh"})
            return persisted

        return state

    def _compute_stale_bindings(self, state: NodeWorkflowStateV2) -> list[ContextStaleBindingV2]:
        stale_details: list[ContextStaleBindingV2] = []
        for role_key in sorted(state.thread_bindings):
            binding = state.thread_bindings[role_key]
            role = binding.role
            if role not in _ROLE_THREAD_ATTR:
                continue
            packet = self._context_builder.build_context_packet(
                project_id=state.project_id,
                node_id=state.node_id,
                role=role,
                workflow_state=state,
            )
            next_hash = packet.packet_hash()
            next_versions = SourceVersions.model_validate(packet.source_versions)
            if _binding_matches(binding, next_hash, next_versions):
                continue
            stale_details.append(
                ContextStaleBindingV2(
                    role=role,
                    threadId=binding.thread_id,
                    currentContextPacketHash=binding.context_packet_hash,
                    nextContextPacketHash=next_hash,
                    currentSourceVersions=copy.deepcopy(binding.source_versions),
                    nextSourceVersions=next_versions,
                )
            )
        return stale_details

    def _publish_state_changed(
        self,
        state: NodeWorkflowStateV2,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._event_publisher is not None:
            self._event_publisher.publish_state_changed(state, details=details)

    def _publish_context_stale(
        self,
        state: NodeWorkflowStateV2,
        *,
        reason: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._event_publisher is not None:
            self._event_publisher.publish_context_stale(state, reason=reason, details=details)

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
                "context_stale": False,
                "context_stale_reason": None,
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


def _rebase_response(state: NodeWorkflowStateV2, updated_bindings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rebased": True,
        "updatedBindings": copy.deepcopy(updated_bindings),
        "workflowState": workflow_state_to_response(
            state,
            allowed_actions=derive_allowed_actions(state),
        ).to_public_dict(),
    }


def _normalize_role_subset(roles: list[ThreadRole] | None) -> list[ThreadRole]:
    if not roles:
        return []
    normalized: list[ThreadRole] = []
    for role in roles:
        if role not in _ROLE_THREAD_ATTR:
            raise WorkflowThreadBindingFailedError(
                "Unsupported workflow thread role.",
                details={"role": role},
            )
        if role not in normalized:
            normalized.append(role)
    return sorted(normalized)


def _stale_reason(details: list[ContextStaleBindingV2]) -> str | None:
    if not details:
        return None
    if len(details) == 1:
        return f"{details[0].role} context packet changed."
    return "Multiple workflow context packets changed."


def _stale_details_equal(left: list[ContextStaleBindingV2], right: list[ContextStaleBindingV2]) -> bool:
    return [
        item.model_dump(by_alias=True, mode="json") for item in left
    ] == [
        item.model_dump(by_alias=True, mode="json") for item in right
    ]


def _record_key(idempotency_key: str) -> str:
    return f"{_IDEMPOTENCY_ACTION}:{idempotency_key}"


def _rebase_record_key(idempotency_key: str) -> str:
    return f"rebase_context:{idempotency_key}"


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
