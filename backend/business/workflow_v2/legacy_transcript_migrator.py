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
from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)

_LEGACY_SNAPSHOT_ROLE_MAP: dict[str, LegacyThreadRole] = {
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


class LegacyTranscriptMigratorV2:
    """One-shot migrator from legacy projected snapshot -> native Session Core V2 journal."""

    def __init__(
        self,
        *,
        storage: Storage,
        workflow_repository: WorkflowStateRepositoryV2,
        snapshot_store: ThreadSnapshotStoreV2,
        runtime_store: RuntimeStoreV2,
    ) -> None:
        self._storage = storage
        self._workflow_repository = workflow_repository
        self._snapshot_store = snapshot_store
        self._runtime_store = runtime_store

    def migrate_all(self) -> dict[str, Any]:
        candidates = self._collect_candidates()
        successes = 0
        failures: list[dict[str, Any]] = []
        skipped = 0
        for candidate in candidates:
            thread_id = str(candidate.binding.thread_id or "").strip()
            if not thread_id:
                skipped += 1
                continue
            if self._runtime_store.has_legacy_migration_marker(thread_id=thread_id):
                skipped += 1
                continue
            try:
                did_import = self._migrate_candidate(candidate)
                if did_import:
                    successes += 1
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
        }

    def find_unmigrated_candidates(self) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for candidate in self._collect_candidates():
            thread_id = str(candidate.binding.thread_id or "").strip()
            if not thread_id:
                continue
            if self._runtime_store.has_legacy_migration_marker(thread_id=thread_id):
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
            workflow_dir = Path(folder_path).expanduser().resolve() / ".planningtree" / "workflow_core_v2"
            if not workflow_dir.exists():
                continue
            for path in workflow_dir.glob("*.json"):
                node_id = path.stem.strip()
                if not node_id:
                    continue
                state = self._workflow_repository.read_state(project_id, node_id)
                for role, binding in state.thread_bindings.items():
                    if binding.created_from != "legacy_adopted":
                        continue
                    thread_id = str(binding.thread_id or "").strip()
                    if not thread_id or thread_id in seen_thread_ids:
                        continue
                    seen_thread_ids.add(thread_id)
                    candidates.append(
                        LegacyThreadCandidate(
                            project_id=project_id,
                            node_id=node_id,
                            role=role,
                            binding=binding,
                        )
                    )
        return candidates

    def _migrate_candidate(self, candidate: LegacyThreadCandidate) -> bool:
        thread_id = str(candidate.binding.thread_id or "").strip()
        if not thread_id:
            return False
        existing_journal = self._runtime_store.read_thread_journal(thread_id)
        existing_turns = self._runtime_store.list_turns(thread_id=thread_id)
        if existing_journal or existing_turns:
            self._runtime_store.mark_legacy_thread_migrated(
                thread_id=thread_id,
                source_project_id=candidate.project_id,
                source_node_id=candidate.node_id,
                source_role=candidate.role,
                source_snapshot_version=None,
                source_item_count=0,
                source_pending_request_count=0,
                source_hash="already_native",
            )
            logger.info(
                "workflow_v2 legacy transcript migration skipped existing native thread",
                extra={
                    "projectId": candidate.project_id,
                    "nodeId": candidate.node_id,
                    "role": candidate.role,
                    "threadId": thread_id,
                },
            )
            return False

        snapshot = self._read_legacy_snapshot(candidate)
        items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
        pending_requests = snapshot.get("pendingRequests") if isinstance(snapshot.get("pendingRequests"), list) else []
        grouped_turn_items = self._group_items_by_turn(candidate.role, snapshot, items)

        for turn_id, turn_items in grouped_turn_items:
            turn_status = self._resolve_turn_status(snapshot, turn_id)
            self._runtime_store.create_turn(thread_id=thread_id, turn_id=turn_id, status=turn_status)
            turn_payload = self._to_api_turn_payload(
                self._runtime_store.get_turn(thread_id=thread_id, turn_id=turn_id)
                or {"id": turn_id, "status": turn_status, "items": []}
            )
            self._runtime_store.append_turn_started_if_absent(
                thread_id=thread_id,
                turn_id=turn_id,
                turn=turn_payload,
            )
            for item_index, raw_item in enumerate(turn_items):
                item_payload = self._to_native_item_payload(
                    raw_item=raw_item,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    role=candidate.role,
                    index=item_index,
                )
                method = "item/started" if item_payload.get("status") == "inProgress" else "item/completed"
                self._runtime_store.append_notification(
                    method=method,
                    params={"item": item_payload},
                    thread_id_override=thread_id,
                )
            if turn_status in _TERMINAL_STATUSES:
                self._runtime_store.append_notification(
                    method="turn/completed",
                    params={"turn": turn_payload},
                    thread_id_override=thread_id,
                )

        source_hash = hashlib.sha256(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self._runtime_store.mark_legacy_thread_migrated(
            thread_id=thread_id,
            source_project_id=candidate.project_id,
            source_node_id=candidate.node_id,
            source_role=candidate.role,
            source_snapshot_version=int(snapshot.get("snapshotVersion") or 0),
            source_item_count=len(items),
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
                "migratedItemCount": len(items),
                "migratedTurnCount": len(grouped_turn_items),
            },
        )
        return True

    def _read_legacy_snapshot(self, candidate: LegacyThreadCandidate) -> dict[str, Any]:
        snapshot_role = _LEGACY_SNAPSHOT_ROLE_MAP.get(candidate.role)
        if snapshot_role is None:
            return {
                "threadId": candidate.binding.thread_id,
                "snapshotVersion": 0,
                "activeTurnId": None,
                "processingState": "idle",
                "items": [],
                "pendingRequests": [],
            }
        if not self._snapshot_store.exists(candidate.project_id, candidate.node_id, snapshot_role):
            return {
                "threadId": candidate.binding.thread_id,
                "snapshotVersion": 0,
                "activeTurnId": None,
                "processingState": "idle",
                "items": [],
                "pendingRequests": [],
            }
        snapshot = self._snapshot_store.read_snapshot(candidate.project_id, candidate.node_id, snapshot_role)
        return dict(snapshot)

    @staticmethod
    def _group_items_by_turn(role: str, snapshot: dict[str, Any], items: list[Any]) -> list[tuple[str, list[dict[str, Any]]]]:
        normalized_items = [item for item in items if isinstance(item, dict)]
        normalized_items.sort(
            key=lambda item: (
                int(item.get("sequence") or 0),
                str(item.get("createdAt") or ""),
                str(item.get("id") or ""),
            )
        )
        active_turn_id = str(snapshot.get("activeTurnId") or "").strip()
        fallback_turn_id = active_turn_id or f"legacy-{role}-turn"
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in normalized_items:
            turn_id = str(item.get("turnId") or "").strip() or fallback_turn_id
            grouped.setdefault(turn_id, []).append(item)
        return list(grouped.items())

    @staticmethod
    def _resolve_turn_status(snapshot: dict[str, Any], turn_id: str) -> str:
        active_turn_id = str(snapshot.get("activeTurnId") or "").strip()
        processing_state = str(snapshot.get("processingState") or "").strip()
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
        if raw in {"pending", "in_progress", "requested", "answer_submitted"}:
            return "inProgress"
        if raw in {"failed", "cancelled", "stale"}:
            return "failed"
        return "completed"

    @staticmethod
    def _map_item_kind(raw_item: dict[str, Any]) -> str:
        raw_kind = str(raw_item.get("kind") or "").strip()
        if raw_kind == "message":
            role = str(raw_item.get("role") or "").strip().lower()
            return "userMessage" if role == "user" else "agentMessage"
        if raw_kind == "reasoning":
            return "reasoning"
        if raw_kind == "plan":
            return "plan"
        if raw_kind == "tool":
            tool_type = str(raw_item.get("toolType") or "").strip()
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
        item_id = str(raw_item.get("id") or "").strip() or f"legacy-{turn_id}-item-{index + 1}"
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
            "createdAt": raw_item.get("createdAt"),
            "updatedAt": raw_item.get("updatedAt"),
        }
        if mapped_kind == "userMessage":
            text = str(raw_item.get("text") or "").strip()
            payload["text"] = text
            payload["content"] = [{"type": "text", "text": text}]
        elif mapped_kind == "agentMessage":
            text = str(raw_item.get("text") or raw_item.get("label") or "").strip()
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
