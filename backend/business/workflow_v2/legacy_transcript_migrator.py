from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.business.workflow_v2.models import ThreadBinding
from backend.business.workflow_v2.repository import WorkflowStateRepositoryV2
from backend.conversation.domain.types import ThreadRole as LegacyThreadRole
from backend.conversation.domain.types_v3 import ThreadRoleV3
from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.conversation.storage.thread_snapshot_store_v3 import ThreadSnapshotStoreV3
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2
from backend.session_core_v2.thread_store import ThreadRolloutRecorder, build_turns_from_rollout_items
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)

_LEGACY_SNAPSHOT_ROLE_MAP: dict[str, LegacyThreadRole] = {
    "ask_planning": "ask_planning",
    "execution": "execution",
    "audit": "audit",
}
_LEGACY_SNAPSHOT_ROLE_MAP_V3: dict[str, ThreadRoleV3] = {
    "ask_planning": "ask_planning",
    "execution": "execution",
    "audit": "audit",
}
_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "interrupted"})


@dataclass(slots=True)
class LegacyThreadCandidate:
    project_id: str
    node_id: str
    role: str
    binding: ThreadBinding


@dataclass(slots=True)
class _LegacySource:
    kind: str
    snapshot: dict[str, Any]


class LegacyTranscriptMigratorV2:
    """One-shot migrator from legacy thread history stores -> native rollout JSONL."""

    def __init__(
        self,
        *,
        storage: Storage,
        workflow_repository: WorkflowStateRepositoryV2,
        thread_rollout_recorder: ThreadRolloutRecorder,
        snapshot_store_v2: ThreadSnapshotStoreV2 | None = None,
        snapshot_store_v3: ThreadSnapshotStoreV3 | None = None,
        snapshot_store: ThreadSnapshotStoreV2 | None = None,
        runtime_store: RuntimeStoreV2 | None = None,
        dry_run: bool = False,
        force: bool = False,
        project_id_filter: str | None = None,
        thread_id_filter: str | None = None,
        limit: int | None = None,
    ) -> None:
        self._storage = storage
        self._workflow_repository = workflow_repository
        self._snapshot_store_v2 = snapshot_store_v2 or snapshot_store
        self._snapshot_store_v3 = snapshot_store_v3
        self._runtime_store = runtime_store
        self._thread_rollout_recorder = thread_rollout_recorder
        self._dry_run = bool(dry_run)
        self._force = bool(force)
        self._project_id_filter = self._normalize_optional_filter(project_id_filter)
        self._thread_id_filter = self._normalize_optional_filter(thread_id_filter)
        self._limit = max(0, int(limit)) if limit is not None else None

    def migrate_all(self) -> dict[str, Any]:
        candidates = self._collect_candidates()
        successes = 0
        failures: list[dict[str, Any]] = []
        skipped = 0
        rollouts_created = 0
        turns_converted = 0
        items_converted = 0
        for candidate in candidates:
            thread_id = str(candidate.binding.thread_id or "").strip()
            if not thread_id:
                skipped += 1
                continue
            try:
                result = self._migrate_candidate(candidate)
                if result["migrated"]:
                    successes += 1
                    rollouts_created += int(result.get("rolloutsCreated") or 0)
                    turns_converted += int(result.get("turnsConverted") or 0)
                    items_converted += int(result.get("itemsConverted") or 0)
                else:
                    skipped += 1
            except Exception as exc:
                failures.append(
                    {
                        "projectId": candidate.project_id,
                        "nodeId": candidate.node_id,
                        "role": candidate.role,
                        "threadId": thread_id,
                        "error": str(exc),
                    }
                )
                logger.exception(
                    "workflow_v2 legacy transcript migration failed",
                    extra={
                        "projectId": candidate.project_id,
                        "nodeId": candidate.node_id,
                        "role": candidate.role,
                        "threadId": thread_id,
                    },
                )
        return {
            "candidates": len(candidates),
            "migrated": successes,
            "skipped": skipped,
            "failed": len(failures),
            "failures": failures,
            "rolloutsCreated": rollouts_created,
            "turnsConverted": turns_converted,
            "itemsConverted": items_converted,
            "dryRun": self._dry_run,
            "force": self._force,
        }

    def find_unmigrated_candidates(self) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for candidate in self._collect_candidates():
            thread_id = str(candidate.binding.thread_id or "").strip()
            if not thread_id:
                continue
            if self._has_migration_marker(thread_id=thread_id):
                continue
            if self._has_valid_native_rollout(thread_id=thread_id):
                continue
            missing.append(
                {
                    "projectId": candidate.project_id,
                    "nodeId": candidate.node_id,
                    "role": candidate.role,
                    "threadId": thread_id,
                }
            )
        return missing

    def _collect_candidates(self) -> list[LegacyThreadCandidate]:
        candidates: list[LegacyThreadCandidate] = []
        seen_thread_ids: set[str] = set()
        for entry in self._storage.workspace_store.list_entries():
            project_id = str(entry.get("project_id") or "").strip()
            folder_path = str(entry.get("folder_path") or "").strip()
            if not project_id or not folder_path:
                continue
            if self._project_id_filter and project_id != self._project_id_filter:
                continue
            workflow_dir = Path(folder_path).expanduser().resolve() / ".planningtree" / "workflow_core_v2"
            if not workflow_dir.exists():
                continue
            for path in workflow_dir.glob("*.json"):
                node_id = path.stem.strip()
                if not node_id:
                    continue
                state = self._workflow_repository.read_state(project_id, node_id)
                for role, binding in state.thread_bindings.items():
                    self._append_candidate(
                        candidates=candidates,
                        seen_thread_ids=seen_thread_ids,
                        project_id=project_id,
                        node_id=node_id,
                        role=role,
                        thread_id=str(binding.thread_id or "").strip(),
                        binding=binding,
                    )
                    if self._limit is not None and len(candidates) >= self._limit:
                        return candidates
                legacy_state_thread_ids = {
                    "ask_planning": state.ask_thread_id,
                    "execution": state.execution_thread_id,
                    "audit": state.audit_thread_id,
                    "package_review": state.package_review_thread_id,
                }
                for role, thread_id in legacy_state_thread_ids.items():
                    self._append_candidate(
                        candidates=candidates,
                        seen_thread_ids=seen_thread_ids,
                        project_id=project_id,
                        node_id=node_id,
                        role=role,
                        thread_id=str(thread_id or "").strip(),
                    )
                    if self._limit is not None and len(candidates) >= self._limit:
                        return candidates
        if self._runtime_store is not None and self._project_id_filter is None:
            for thread_id in self._runtime_store.list_thread_ids_with_history():
                self._append_candidate(
                    candidates=candidates,
                    seen_thread_ids=seen_thread_ids,
                    project_id=None,
                    node_id=None,
                    role="execution",
                    thread_id=thread_id,
                    created_from="runtime_history",
                )
                if self._limit is not None and len(candidates) >= self._limit:
                    return candidates
        return candidates

    def _append_candidate(
        self,
        *,
        candidates: list[LegacyThreadCandidate],
        seen_thread_ids: set[str],
        project_id: str | None,
        node_id: str | None,
        role: str,
        thread_id: str,
        binding: ThreadBinding | None = None,
        created_from: str = "existing_thread",
    ) -> None:
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_thread_id or normalized_thread_id in seen_thread_ids:
            return
        if self._thread_id_filter and normalized_thread_id != self._thread_id_filter:
            return
        normalized_project_id = str(project_id or "").strip()
        normalized_node_id = str(node_id or "").strip()
        normalized_role = role if role in {"ask_planning", "execution", "audit", "package_review"} else "execution"
        seen_thread_ids.add(normalized_thread_id)
        candidates.append(
            LegacyThreadCandidate(
                project_id=normalized_project_id,
                node_id=normalized_node_id,
                role=normalized_role,
                binding=binding
                or ThreadBinding(
                    projectId=normalized_project_id,
                    nodeId=normalized_node_id,
                    role=normalized_role,
                    threadId=normalized_thread_id,
                    createdFrom=created_from,
                ),
            )
        )

    def _migrate_candidate(self, candidate: LegacyThreadCandidate) -> dict[str, Any]:
        thread_id = str(candidate.binding.thread_id or "").strip()
        if not thread_id:
            return {"migrated": False}
        if not self._force:
            if self._has_migration_marker(thread_id=thread_id):
                return {"migrated": False, "reason": "already_marked"}
            if self._has_valid_native_rollout(thread_id=thread_id):
                self._mark_migrated(
                    candidate=candidate,
                    source_kind="native_rollout",
                    source_snapshot_version=None,
                    source_item_count=0,
                    source_pending_request_count=0,
                    source_hash="already_native_rollout",
                )
                return {"migrated": False, "reason": "already_native_rollout"}

        source = self._read_legacy_source(candidate)
        rollout_items = self._build_rollout_items(candidate=candidate, source=source)
        turns = build_turns_from_rollout_items(rollout_items)
        source_items = source.snapshot.get("items") if isinstance(source.snapshot.get("items"), list) else []
        pending_requests = (
            source.snapshot.get("pendingRequests") if isinstance(source.snapshot.get("pendingRequests"), list) else []
        )
        if not rollout_items:
            return {"migrated": False, "reason": "empty_rollout"}
        if not turns and source_items:
            raise ValueError(f"legacy source {source.kind} produced no native turns for thread {thread_id}")

        if self._dry_run:
            return {
                "migrated": True,
                "rolloutsCreated": 0,
                "turnsConverted": len(turns),
                "itemsConverted": len(source_items),
                "source": source.kind,
            }

        self._thread_rollout_recorder.ensure_thread(
            thread_id=thread_id,
            project_id=candidate.project_id,
            title=f"{candidate.role} thread",
            status=self._metadata_status_from_turns(turns),
        )
        appended = self._thread_rollout_recorder.append_items(thread_id, rollout_items)
        loaded_items = self._thread_rollout_recorder.load_items(thread_id)
        build_turns_from_rollout_items(loaded_items)

        source_hash = self._source_hash(source.snapshot)
        self._mark_migrated(
            candidate=candidate,
            source_kind=source.kind,
            source_snapshot_version=self._snapshot_version(source.snapshot),
            source_item_count=len(source_items),
            source_pending_request_count=len(pending_requests),
            source_hash=f"sha256:{source_hash}",
        )
        logger.info(
            "workflow_v2 legacy transcript migration success",
            extra={
                "projectId": candidate.project_id,
                "nodeId": candidate.node_id,
                "role": candidate.role,
                "threadId": thread_id,
                "source": source.kind,
                "migratedItemCount": len(source_items),
                "migratedTurnCount": len(turns),
                "rolloutAppendCount": len(appended),
            },
        )
        return {
            "migrated": True,
            "rolloutsCreated": 1,
            "turnsConverted": len(turns),
            "itemsConverted": len(source_items),
            "source": source.kind,
        }

    def _read_legacy_source(self, candidate: LegacyThreadCandidate) -> _LegacySource:
        runtime_source = self._read_runtime_journal_source(candidate)
        if runtime_source is not None:
            return runtime_source
        snapshot_v3 = self._read_snapshot_v3(candidate)
        if snapshot_v3 is not None:
            return _LegacySource(kind="thread_snapshot_store_v3", snapshot=snapshot_v3)
        snapshot_v2 = self._read_snapshot_v2(candidate)
        if snapshot_v2 is not None:
            return _LegacySource(kind="thread_snapshot_store_v2", snapshot=snapshot_v2)
        chat_source = self._read_chat_session_source(candidate)
        if chat_source is not None:
            return chat_source
        return _LegacySource(
            kind="empty",
            snapshot={
                "threadId": candidate.binding.thread_id,
                "snapshotVersion": 0,
                "activeTurnId": None,
                "processingState": "idle",
                "items": [],
                "pendingRequests": [],
            },
        )

    def _read_snapshot_v3(self, candidate: LegacyThreadCandidate) -> dict[str, Any] | None:
        if self._snapshot_store_v3 is None:
            return None
        snapshot_role = _LEGACY_SNAPSHOT_ROLE_MAP_V3.get(candidate.role)
        if snapshot_role is None:
            return None
        if not self._snapshot_store_v3.exists(candidate.project_id, candidate.node_id, snapshot_role):
            return None
        return dict(self._snapshot_store_v3.read_snapshot(candidate.project_id, candidate.node_id, snapshot_role))

    def _read_snapshot_v2(self, candidate: LegacyThreadCandidate) -> dict[str, Any] | None:
        if self._snapshot_store_v2 is None:
            return None
        snapshot_role = _LEGACY_SNAPSHOT_ROLE_MAP.get(candidate.role)
        if snapshot_role is None:
            return None
        if not self._snapshot_store_v2.exists(candidate.project_id, candidate.node_id, snapshot_role):
            return None
        return dict(self._snapshot_store_v2.read_snapshot(candidate.project_id, candidate.node_id, snapshot_role))

    def _read_chat_session_source(self, candidate: LegacyThreadCandidate) -> _LegacySource | None:
        chat_store = getattr(self._storage, "chat_state_store", None)
        if chat_store is None:
            return None
        session = chat_store.read_session(candidate.project_id, candidate.node_id, thread_role=candidate.role)
        if not isinstance(session, dict):
            return None
        messages = session.get("messages") if isinstance(session.get("messages"), list) else []
        thread_id = str(session.get("thread_id") or candidate.binding.thread_id or "").strip()
        if not messages and thread_id != str(candidate.binding.thread_id or "").strip():
            return None
        active_turn_id = str(session.get("active_turn_id") or "").strip()
        fallback_turn_id = active_turn_id or f"legacy-{candidate.role}-turn"
        items: list[dict[str, Any]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "assistant").strip()
            items.append(
                {
                    "id": str(message.get("message_id") or f"legacy-message-{index + 1}"),
                    "kind": "message",
                    "role": role,
                    "text": str(message.get("content") or ""),
                    "turnId": str(message.get("turn_id") or "").strip() or fallback_turn_id,
                    "status": "failed" if str(message.get("status") or "") == "error" else "completed",
                    "sequence": index + 1,
                    "createdAt": message.get("created_at"),
                    "updatedAt": message.get("updated_at"),
                    "metadata": {"legacyChatMessage": True},
                }
            )
        return _LegacySource(
            kind="chat_state_store",
            snapshot={
                "threadId": thread_id or candidate.binding.thread_id,
                "snapshotVersion": 0,
                "activeTurnId": active_turn_id or fallback_turn_id,
                "processingState": "idle",
                "items": items,
                "pendingRequests": [],
            },
        )

    def _read_runtime_journal_source(self, candidate: LegacyThreadCandidate) -> _LegacySource | None:
        if self._runtime_store is None:
            return None
        thread_id = str(candidate.binding.thread_id or "").strip()
        journal = self._runtime_store.read_thread_journal(thread_id)
        if not journal:
            return None
        return _LegacySource(
            kind="session_v2_journal",
            snapshot={
                "threadId": thread_id,
                "snapshotVersion": 0,
                "activeTurnId": None,
                "processingState": "idle",
                "items": [],
                "pendingRequests": [],
                "journal": journal,
            },
        )

    def _build_rollout_items(self, *, candidate: LegacyThreadCandidate, source: _LegacySource) -> list[dict[str, Any]]:
        if source.kind == "session_v2_journal":
            return self._build_rollout_items_from_runtime_journal(candidate=candidate, source=source)

        thread_id = str(candidate.binding.thread_id or source.snapshot.get("threadId") or "").strip()
        if not thread_id:
            return []
        items = source.snapshot.get("items") if isinstance(source.snapshot.get("items"), list) else []
        grouped_turn_items = self._group_items_by_turn(candidate.role, source.snapshot, items)
        rollout_items: list[dict[str, Any]] = [
            {
                "type": "session_meta",
                "eventId": f"legacy:{thread_id}:session_meta:{source.kind}",
                "threadId": thread_id,
                "projectId": candidate.project_id,
                "nodeId": candidate.node_id,
                "role": candidate.role,
                "source": source.kind,
                "snapshotVersion": self._snapshot_version(source.snapshot),
            }
        ]
        for turn_id, turn_items in grouped_turn_items:
            turn_status = self._resolve_turn_status(source.snapshot, turn_id)
            turn_payload = self._to_api_turn_payload({"id": turn_id, "status": turn_status, "items": []})
            rollout_items.append(
                self._event_msg(
                    event_id=f"legacy:{thread_id}:{turn_id}:turn_started:{source.kind}",
                    method="turn/started",
                    thread_id=thread_id,
                    turn_id=turn_id,
                    params={"threadId": thread_id, "turnId": turn_id, "turn": turn_payload},
                )
            )
            converted_items: list[dict[str, Any]] = []
            for item_index, raw_item in enumerate(turn_items):
                item_payload = self._to_native_item_payload(
                    raw_item=raw_item,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    role=candidate.role,
                    index=item_index,
                )
                converted_items.append(item_payload)
                method = "item/started" if item_payload.get("status") == "inProgress" else "item/completed"
                rollout_items.append(
                    self._event_msg(
                        event_id=f"legacy:{thread_id}:{turn_id}:item:{item_payload['id']}:{method}:{source.kind}",
                        method=method,
                        thread_id=thread_id,
                        turn_id=turn_id,
                        params={"threadId": thread_id, "turnId": turn_id, "item": item_payload},
                    )
                )
            if turn_status in _TERMINAL_STATUSES:
                turn_payload = self._to_api_turn_payload(
                    {"id": turn_id, "status": turn_status, "items": converted_items}
                )
                rollout_items.append(
                    self._event_msg(
                        event_id=f"legacy:{thread_id}:{turn_id}:turn_completed:{source.kind}",
                        method="turn/completed",
                        thread_id=thread_id,
                        turn_id=turn_id,
                        params={"threadId": thread_id, "turnId": turn_id, "turn": turn_payload},
                    )
                )
        return rollout_items

    def _build_rollout_items_from_runtime_journal(
        self,
        *,
        candidate: LegacyThreadCandidate,
        source: _LegacySource,
    ) -> list[dict[str, Any]]:
        thread_id = str(candidate.binding.thread_id or source.snapshot.get("threadId") or "").strip()
        journal = source.snapshot.get("journal") if isinstance(source.snapshot.get("journal"), list) else []
        if not thread_id:
            return []
        rollout_items: list[dict[str, Any]] = [
            {
                "type": "session_meta",
                "eventId": f"legacy:{thread_id}:session_meta:{source.kind}",
                "threadId": thread_id,
                "projectId": candidate.project_id,
                "nodeId": candidate.node_id,
                "role": candidate.role,
                "source": source.kind,
            }
        ]
        for index, event in enumerate(journal):
            if not isinstance(event, dict):
                continue
            method = str(event.get("method") or "").strip()
            if not method:
                continue
            params = event.get("params") if isinstance(event.get("params"), dict) else {}
            turn_id = str(event.get("turnId") or params.get("turnId") or "").strip() or None
            event_id = str(event.get("eventId") or "").strip() or f"legacy:{thread_id}:runtime:{index + 1}:{method}"
            rollout_items.append(
                self._event_msg(
                    event_id=event_id,
                    method=method,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    params={**params, "threadId": thread_id, **({"turnId": turn_id} if turn_id else {})},
                )
            )
        return rollout_items

    @staticmethod
    def _group_items_by_turn(role: str, snapshot: dict[str, Any], items: list[Any]) -> list[tuple[str, list[dict[str, Any]]]]:
        normalized_items = [item for item in items if isinstance(item, dict)]
        normalized_items.sort(
            key=lambda item: (
                int(item.get("sequence") or 0),
                str(item.get("createdAt") or item.get("created_at") or ""),
                str(item.get("id") or item.get("message_id") or ""),
            )
        )
        active_turn_id = str(snapshot.get("activeTurnId") or snapshot.get("active_turn_id") or "").strip()
        fallback_turn_id = active_turn_id or f"legacy-{role}-turn"
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in normalized_items:
            turn_id = str(item.get("turnId") or item.get("turn_id") or "").strip() or fallback_turn_id
            grouped.setdefault(turn_id, []).append(item)
        return list(grouped.items())

    @staticmethod
    def _resolve_turn_status(snapshot: dict[str, Any], turn_id: str) -> str:
        active_turn_id = str(snapshot.get("activeTurnId") or snapshot.get("active_turn_id") or "").strip()
        processing_state = str(snapshot.get("processingState") or snapshot.get("processing_state") or "").strip()
        if turn_id != active_turn_id:
            return "completed"
        if processing_state == "running":
            return "inProgress"
        if processing_state == "waiting_user_input":
            return "waitingUserInput"
        if processing_state == "failed":
            return "failed"
        return "completed"

    @staticmethod
    def _map_item_status(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"pending", "in_progress", "requested", "answer_submitted", "streaming"}:
            return "inProgress"
        if raw in {"failed", "cancelled", "stale", "error"}:
            return "failed"
        return "completed"

    @staticmethod
    def _map_item_kind(raw_item: dict[str, Any]) -> str:
        raw_kind = str(raw_item.get("kind") or raw_item.get("item_type") or "").strip()
        if raw_kind == "message":
            role = str(raw_item.get("role") or "").strip().lower()
            return "userMessage" if role == "user" else "agentMessage"
        if raw_kind == "reasoning":
            return "reasoning"
        if raw_kind == "plan":
            return "plan"
        if raw_kind == "tool":
            tool_type = str(raw_item.get("toolType") or raw_item.get("tool_type") or "").strip()
            if tool_type == "fileChange":
                return "fileChange"
            return "commandExecution"
        if raw_kind == "userInput":
            return "userInput"
        if raw_kind == "error":
            return "error"
        return "agentMessage"

    @staticmethod
    def _to_api_turn_payload(turn: dict[str, Any]) -> dict[str, Any]:
        status = str(turn.get("status") or "inProgress")
        if status == "waitingUserInput":
            status = "inProgress"
        if status == "idle":
            status = "inProgress"
        if status not in {"inProgress", "completed", "failed", "interrupted"}:
            status = "failed"
        payload = {
            "id": str(turn.get("id") or ""),
            "status": status,
            "items": list(turn.get("items") or []),
            "startedAtMs": turn.get("startedAtMs"),
            "completedAtMs": turn.get("completedAtMs"),
            "lastCodexStatus": turn.get("lastCodexStatus"),
        }
        error = turn.get("error")
        if isinstance(error, dict):
            payload["error"] = error
        return payload

    def _to_native_item_payload(
        self,
        *,
        raw_item: dict[str, Any],
        thread_id: str,
        turn_id: str,
        role: str,
        index: int,
    ) -> dict[str, Any]:
        mapped_kind = self._map_item_kind(raw_item)
        item_id = str(raw_item.get("id") or raw_item.get("message_id") or "").strip() or f"legacy-{turn_id}-item-{index + 1}"
        status = self._map_item_status(raw_item.get("status"))
        metadata = raw_item.get("metadata")
        normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        normalized_metadata["legacyMigrated"] = True
        normalized_metadata["legacyRole"] = role
        payload: dict[str, Any] = {
            "id": item_id,
            "threadId": thread_id,
            "turnId": turn_id,
            "kind": mapped_kind,
            "type": mapped_kind,
            "status": status,
            "metadata": normalized_metadata,
            "legacyRawKind": raw_item.get("kind"),
            "createdAt": raw_item.get("createdAt") or raw_item.get("created_at"),
            "updatedAt": raw_item.get("updatedAt") or raw_item.get("updated_at"),
        }
        if mapped_kind == "userMessage":
            text = str(raw_item.get("text") or raw_item.get("content") or "").strip()
            payload["text"] = text
            payload["content"] = [{"type": "text", "text": text}]
        elif mapped_kind == "agentMessage":
            text = str(raw_item.get("text") or raw_item.get("content") or raw_item.get("label") or "").strip()
            payload["text"] = text
        elif mapped_kind == "reasoning":
            summary = str(raw_item.get("summaryText") or "").strip()
            detail = str(raw_item.get("detailText") or "").strip()
            payload["summary"] = [summary] if summary else []
            payload["content"] = [detail] if detail else []
            payload["text"] = "\n".join([part for part in [summary, detail] if part])
        elif mapped_kind == "plan":
            payload["text"] = str(raw_item.get("text") or "").strip()
            payload["title"] = raw_item.get("title")
            payload["steps"] = raw_item.get("steps") if isinstance(raw_item.get("steps"), list) else []
        elif mapped_kind == "commandExecution":
            payload["command"] = raw_item.get("argumentsText")
            payload["output"] = raw_item.get("outputText")
            payload["aggregatedOutput"] = raw_item.get("outputText")
            payload["toolName"] = raw_item.get("toolName")
        elif mapped_kind == "fileChange":
            payload["output"] = raw_item.get("outputText")
            payload["changes"] = raw_item.get("changes") if isinstance(raw_item.get("changes"), list) else []
            if isinstance(raw_item.get("outputFiles"), list):
                payload["files"] = raw_item.get("outputFiles")
        elif mapped_kind == "userInput":
            payload["requestId"] = raw_item.get("requestId")
            payload["questions"] = raw_item.get("questions") if isinstance(raw_item.get("questions"), list) else []
            payload["answers"] = raw_item.get("answers") if isinstance(raw_item.get("answers"), list) else []
            payload["title"] = raw_item.get("title")
        elif mapped_kind == "error":
            payload["code"] = raw_item.get("code")
            payload["message"] = raw_item.get("message")
            payload["title"] = raw_item.get("title")
        return payload

    def _has_valid_native_rollout(self, *, thread_id: str) -> bool:
        try:
            items = self._thread_rollout_recorder.load_items(thread_id)
        except (FileNotFoundError, json.JSONDecodeError):
            return False
        if not items:
            return False
        return bool(build_turns_from_rollout_items(items))

    def _has_migration_marker(self, *, thread_id: str) -> bool:
        return bool(
            self._runtime_store is not None
            and self._runtime_store.has_legacy_migration_marker(thread_id=thread_id)
        )

    def _mark_migrated(
        self,
        *,
        candidate: LegacyThreadCandidate,
        source_kind: str,
        source_snapshot_version: int | None,
        source_item_count: int,
        source_pending_request_count: int,
        source_hash: str,
    ) -> None:
        if self._dry_run or self._runtime_store is None:
            return
        self._runtime_store.mark_legacy_thread_migrated(
            thread_id=str(candidate.binding.thread_id or ""),
            source_project_id=candidate.project_id,
            source_node_id=candidate.node_id,
            source_role=candidate.role,
            source_snapshot_version=source_snapshot_version,
            source_item_count=source_item_count,
            source_pending_request_count=source_pending_request_count,
            source_hash=f"{source_kind}:{source_hash}",
        )

    @staticmethod
    def _event_msg(
        *,
        event_id: str,
        method: str,
        thread_id: str,
        turn_id: str | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": "event_msg",
            "event": {
                "eventId": event_id,
                "method": method,
                "threadId": thread_id,
                "turnId": turn_id,
                "params": params,
            },
        }

    @staticmethod
    def _metadata_status_from_turns(turns: list[dict[str, Any]]) -> str:
        if any(str(turn.get("status") or "") == "failed" for turn in turns):
            return "failed"
        if any(str(turn.get("status") or "") == "inProgress" for turn in turns):
            return "running"
        return "closed"

    @staticmethod
    def _source_hash(snapshot: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _snapshot_version(snapshot: dict[str, Any]) -> int | None:
        value = snapshot.get("snapshotVersion")
        if value is None:
            value = snapshot.get("snapshot_version")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_optional_filter(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None
