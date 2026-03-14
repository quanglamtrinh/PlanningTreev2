from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from backend.storage.file_utils import iso_now
from backend.streaming.sse_broker import AgentEventBroker

logger = logging.getLogger(__name__)


AgentOperationKind = str


def clear_last_agent_failure(state: dict[str, Any]) -> None:
    state["last_agent_failure"] = None


def set_last_agent_failure(state: dict[str, Any], *, operation: AgentOperationKind, message: str) -> None:
    state["last_agent_failure"] = {
        "operation": str(operation or "").strip(),
        "message": str(message or "").strip(),
        "occurred_at": iso_now(),
    }


@dataclass
class AgentOperationHandle:
    project_id: str
    node_id: str
    operation: AgentOperationKind
    accepted_at: str
    started_at: str
    first_delta_at: str | None = None


class AgentOperationService:
    def __init__(self, event_broker: AgentEventBroker) -> None:
        self._event_broker = event_broker
        self._lock = threading.Lock()
        self._active_nodes: set[tuple[str, str]] = set()
        self._event_seq: dict[tuple[str, str], int] = defaultdict(int)

    def start_operation(self, project_id: str, node_id: str, operation: AgentOperationKind) -> AgentOperationHandle:
        key = (project_id, node_id)
        with self._lock:
            if key in self._active_nodes:
                raise RuntimeError("Another agent operation is already active for this node.")
            self._active_nodes.add(key)
        now = iso_now()
        handle = AgentOperationHandle(
            project_id=project_id,
            node_id=node_id,
            operation=operation,
            accepted_at=now,
            started_at=now,
        )
        logger.info(
            "agent_operation_started operation=%s project_id=%s node_id=%s accepted_at=%s started_at=%s",
            operation,
            project_id,
            node_id,
            handle.accepted_at,
            handle.started_at,
        )
        return handle

    def finish_operation(self, handle: AgentOperationHandle) -> None:
        with self._lock:
            self._active_nodes.discard((handle.project_id, handle.node_id))

    def is_active(self, project_id: str, node_id: str) -> bool:
        with self._lock:
            return (project_id, node_id) in self._active_nodes

    def publish_started(
        self,
        handle: AgentOperationHandle,
        *,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._publish(
            handle,
            event_type="operation_started",
            stage=stage,
            message=message,
            extra=extra,
        )

    def publish_progress(
        self,
        handle: AgentOperationHandle,
        *,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._publish(
            handle,
            event_type="operation_progress",
            stage=stage,
            message=message,
            extra=extra,
        )

    def mark_first_delta(self, handle: AgentOperationHandle) -> None:
        with self._lock:
            if handle.first_delta_at is not None:
                return
            handle.first_delta_at = iso_now()
        logger.info(
            "agent_operation_first_delta operation=%s project_id=%s node_id=%s first_delta_at=%s",
            handle.operation,
            handle.project_id,
            handle.node_id,
            handle.first_delta_at,
        )

    def publish_completed(
        self,
        handle: AgentOperationHandle,
        *,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        completed_at = iso_now()
        logger.info(
            "agent_operation_completed operation=%s project_id=%s node_id=%s accepted_at=%s started_at=%s first_delta_at=%s completed_at=%s",
            handle.operation,
            handle.project_id,
            handle.node_id,
            handle.accepted_at,
            handle.started_at,
            handle.first_delta_at,
            completed_at,
        )
        self._publish(
            handle,
            event_type="operation_completed",
            stage=stage,
            message=message,
            extra={"completed_at": completed_at, **(extra or {})},
        )

    def publish_failed(
        self,
        handle: AgentOperationHandle,
        *,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        failed_at = iso_now()
        logger.warning(
            "agent_operation_failed operation=%s project_id=%s node_id=%s accepted_at=%s started_at=%s first_delta_at=%s failed_at=%s message=%s",
            handle.operation,
            handle.project_id,
            handle.node_id,
            handle.accepted_at,
            handle.started_at,
            handle.first_delta_at,
            failed_at,
            message,
        )
        self._publish(
            handle,
            event_type="operation_failed",
            stage=stage,
            message=message,
            extra={"failed_at": failed_at, **(extra or {})},
        )

    def _publish(
        self,
        handle: AgentOperationHandle,
        *,
        event_type: str,
        stage: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        key = (handle.project_id, handle.node_id)
        with self._lock:
            self._event_seq[key] += 1
            event_seq = self._event_seq[key]
        payload: dict[str, Any] = {
            "event_seq": event_seq,
            "type": event_type,
            "node_id": handle.node_id,
            "operation": handle.operation,
            "stage": stage,
            "message": message,
            "timestamp": iso_now(),
        }
        if extra:
            payload.update(extra)
        self._event_broker.publish(handle.project_id, handle.node_id, payload)
