from __future__ import annotations

import copy
import logging
import threading
from typing import Any, cast

from backend.conversation.domain.events import build_thread_envelope
from backend.conversation.domain.types_v3 import ThreadRoleV3, ThreadSnapshotV3, copy_snapshot_v3
from backend.conversation.projector.thread_event_projector_v3 import project_v2_envelope_to_v3, project_v2_snapshot_to_v3
from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.conversation.storage.thread_snapshot_store_v3 import ThreadSnapshotStoreV3
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)

_SUPPORTED_THREAD_ROLES = {"ask_planning", "execution", "audit"}


def _normalize_thread_role(value: Any) -> ThreadRoleV3 | None:
    normalized = str(value or "").strip()
    if normalized in _SUPPORTED_THREAD_ROLES:
        return cast(ThreadRoleV3, normalized)
    return None


class RelayingConversationEventBrokerV2(ChatEventBroker):
    """Publishes legacy V2 envelopes and mirrors mapped V3 envelopes to the V3 broker."""

    def __init__(
        self,
        *,
        conversation_event_broker_v3: ChatEventBroker,
        snapshot_store_v2: ThreadSnapshotStoreV2,
        snapshot_store_v3: ThreadSnapshotStoreV3,
    ) -> None:
        super().__init__()
        self._conversation_event_broker_v3 = conversation_event_broker_v3
        self._snapshot_store_v2 = snapshot_store_v2
        self._snapshot_store_v3 = snapshot_store_v3
        self._snapshot_cache: dict[tuple[str, str, ThreadRoleV3], ThreadSnapshotV3] = {}
        self._snapshot_cache_lock = threading.Lock()

    def publish(self, project_id: str, node_id: str, event: dict[str, Any], thread_role: str = "") -> None:
        super().publish(project_id, node_id, event, thread_role=thread_role)
        self._relay_event(project_id, node_id, event, thread_role=thread_role)

    def _relay_event(self, project_id: str, node_id: str, event: dict[str, Any], *, thread_role: str = "") -> None:
        event_payload = event if isinstance(event, dict) else {}
        role = _normalize_thread_role(thread_role) or _normalize_thread_role(event_payload.get("threadRole"))
        if role is None:
            return

        key = (project_id, node_id, role)
        with self._snapshot_cache_lock:
            current_snapshot = self._snapshot_cache.get(key)
            if current_snapshot is None:
                snapshot_v2 = self._snapshot_store_v2.read_snapshot(project_id, node_id, role)
                current_snapshot = project_v2_snapshot_to_v3(snapshot_v2)
            updated_snapshot, mapped_events = project_v2_envelope_to_v3(current_snapshot, event_payload)
            self._snapshot_cache[key] = copy_snapshot_v3(updated_snapshot)

        try:
            self._snapshot_store_v3.write_snapshot(project_id, node_id, role, copy.deepcopy(updated_snapshot))
        except Exception:
            logger.debug(
                "Failed to mirror V2 envelope snapshot to V3 store for %s/%s/%s",
                project_id,
                node_id,
                role,
                exc_info=True,
            )

        event_snapshot_version = int(event_payload.get("snapshotVersion") or 0)
        mapped_snapshot_version = event_snapshot_version or int(updated_snapshot.get("snapshotVersion") or 0)
        for mapped in mapped_events:
            mapped_payload = mapped.get("payload")
            envelope_payload = mapped_payload if isinstance(mapped_payload, dict) else {}
            envelope = build_thread_envelope(
                project_id=project_id,
                node_id=node_id,
                thread_role=role,
                snapshot_version=mapped_snapshot_version,
                event_type=str(mapped.get("type") or ""),
                payload=envelope_payload,
            )
            self._conversation_event_broker_v3.publish(project_id, node_id, envelope, thread_role=role)
