from __future__ import annotations

import copy
from typing import Any, Dict

from backend.config.app_config import AppPaths
from backend.storage.file_utils import atomic_write_json, load_json
from backend.storage.project_ids import normalize_project_id
from backend.storage.project_locks import ProjectLockRegistry


def _default_planning_state() -> dict[str, Any]:
    return {
        "thread_id": None,
        "forked_from_node": None,
        "status": None,
        "active_turn_id": None,
        "turns": [],
        "event_seq": 0,
    }


def _default_execution_state() -> dict[str, Any]:
    return {
        "thread_id": None,
        "forked_from_planning": None,
        "status": None,
        "active_turn_id": None,
        "active_assistant_message_id": None,
        "messages": [],
        "event_seq": 0,
        "config": None,
        "runtime_thread_status": None,
        "runtime_request_registry": [],
        "pending_input_request": None,
    }


def _default_ask_state() -> dict[str, Any]:
    return {
        "thread_id": None,
        "forked_from_planning_thread_id": None,
        "status": None,
        "active_turn_id": None,
        "messages": [],
        "event_seq": 0,
        "delta_context_packets": [],
        "created_at": None,
    }


_ASK_FIELD_UNSET = object()


def _bump_event_seq(bucket: dict[str, Any]) -> None:
    bucket["event_seq"] = int(bucket.get("event_seq", 0) or 0) + 1


class ThreadStore:
    def __init__(self, paths: AppPaths, lock_registry: ProjectLockRegistry) -> None:
        self._paths = paths
        self._lock_registry = lock_registry

    def _thread_state_path(self, project_id: str):
        normalized = normalize_project_id(project_id)
        return self._paths.projects_root / normalized / "thread_state.json"

    def project_lock(self, project_id: str):
        return self._lock_registry.for_project(project_id)

    def read_thread_state(self, project_id: str) -> Dict[str, Any]:
        with self.project_lock(project_id):
            return self._read_thread_state_unlocked(project_id)

    def write_thread_state(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.project_lock(project_id):
            self._write_thread_state_unlocked(project_id, payload)
            return payload

    def get_node_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(node_state)

    def peek_node_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            raw_node_state = state.get(node_id)
            if isinstance(raw_node_state, dict):
                node_state = copy.deepcopy(raw_node_state)
                node_state.setdefault("planning", _default_planning_state())
                node_state.setdefault("execution", _default_execution_state())
                node_state.setdefault("ask", _default_ask_state())
                return node_state
            return self._default_node_state()

    def upsert_node_state(
        self,
        project_id: str,
        node_id: str,
        *,
        planning: dict[str, Any] | None = None,
        execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            if planning is not None:
                node_state["planning"] = copy.deepcopy(planning)
            if execution is not None:
                node_state["execution"] = copy.deepcopy(execution)
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(node_state)

    def append_planning_turn(
        self,
        project_id: str,
        node_id: str,
        turn: dict[str, Any],
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            planning = node_state["planning"]
            planning["turns"].append(copy.deepcopy(turn))
            planning["event_seq"] = int(planning.get("event_seq", 0) or 0) + 1
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(planning)

    def replace_planning_turns(
        self,
        project_id: str,
        node_id: str,
        turns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            planning = self._ensure_node_state_unlocked(state, node_id)["planning"]
            planning["turns"] = copy.deepcopy(turns)
            try:
                current_event_seq = int(planning.get("event_seq", 0) or 0)
            except (TypeError, ValueError):
                current_event_seq = 0
            planning["event_seq"] = max(current_event_seq, len(turns))
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(planning)

    def set_planning_status(
        self,
        project_id: str,
        node_id: str,
        *,
        thread_id: str | None = None,
        forked_from_node: str | None = None,
        status: str | None = None,
        active_turn_id: str | None = None,
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            planning = self._ensure_node_state_unlocked(state, node_id)["planning"]
            if thread_id is not None:
                planning["thread_id"] = thread_id
            if forked_from_node is not None:
                planning["forked_from_node"] = forked_from_node
            planning["status"] = status
            planning["active_turn_id"] = active_turn_id
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(planning)

    def get_planning_turns(self, project_id: str, node_id: str) -> list[dict[str, Any]]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            return copy.deepcopy(node_state["planning"].get("turns", []))

    def get_execution_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            return copy.deepcopy(node_state["execution"])

    def write_execution_session(
        self,
        project_id: str,
        node_id: str,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            node_state["execution"] = copy.deepcopy(session)
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(node_state["execution"])

    def get_ask_state(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            return copy.deepcopy(node_state["ask"])

    def write_ask_session(
        self,
        project_id: str,
        node_id: str,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            node_state["ask"] = copy.deepcopy(session)
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(node_state["ask"])

    def write_ask_session_and_append_planning_turn(
        self,
        project_id: str,
        node_id: str,
        *,
        ask_session: dict[str, Any],
        planning_turn: dict[str, Any],
        planning_status: str | None,
        planning_active_turn_id: str | None,
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            node_state = self._ensure_node_state_unlocked(state, node_id)
            node_state["ask"] = copy.deepcopy(ask_session)

            planning = node_state["planning"]
            planning["turns"].append(copy.deepcopy(planning_turn))
            planning["event_seq"] = int(planning.get("event_seq", 0) or 0) + 1
            planning["status"] = planning_status
            planning["active_turn_id"] = planning_active_turn_id

            self._write_thread_state_unlocked(project_id, state)
            return {
                "ask": copy.deepcopy(node_state["ask"]),
                "planning": copy.deepcopy(planning),
            }

    def set_ask_status(
        self,
        project_id: str,
        node_id: str,
        *,
        thread_id: Any = _ASK_FIELD_UNSET,
        forked_from_planning_thread_id: Any = _ASK_FIELD_UNSET,
        status: Any = _ASK_FIELD_UNSET,
        active_turn_id: Any = _ASK_FIELD_UNSET,
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            ask = self._ensure_node_state_unlocked(state, node_id)["ask"]
            changed = False

            if thread_id is not _ASK_FIELD_UNSET and ask.get("thread_id") != thread_id:
                ask["thread_id"] = thread_id
                changed = True
            if (
                forked_from_planning_thread_id is not _ASK_FIELD_UNSET
                and ask.get("forked_from_planning_thread_id") != forked_from_planning_thread_id
            ):
                ask["forked_from_planning_thread_id"] = forked_from_planning_thread_id
                changed = True
            if status is not _ASK_FIELD_UNSET and ask.get("status") != status:
                ask["status"] = status
                changed = True
            if active_turn_id is not _ASK_FIELD_UNSET and ask.get("active_turn_id") != active_turn_id:
                ask["active_turn_id"] = active_turn_id
                changed = True

            if changed:
                _bump_event_seq(ask)
                self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(ask)

    def append_ask_message(
        self,
        project_id: str,
        node_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            ask = self._ensure_node_state_unlocked(state, node_id)["ask"]
            ask["messages"].append(copy.deepcopy(message))
            _bump_event_seq(ask)
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(ask)

    def upsert_delta_context_packet(
        self,
        project_id: str,
        node_id: str,
        packet: dict[str, Any],
    ) -> dict[str, Any]:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            ask = self._ensure_node_state_unlocked(state, node_id)["ask"]
            packets = ask["delta_context_packets"]
            packet_id = packet.get("packet_id")

            for index, existing in enumerate(packets):
                if isinstance(existing, dict) and existing.get("packet_id") == packet_id:
                    if existing != packet:
                        packets[index] = copy.deepcopy(packet)
                        _bump_event_seq(ask)
                        self._write_thread_state_unlocked(project_id, state)
                    return copy.deepcopy(packets[index])

            packets.append(copy.deepcopy(packet))
            _bump_event_seq(ask)
            self._write_thread_state_unlocked(project_id, state)
            return copy.deepcopy(packets[-1])

    def block_mergeable_ask_packets(
        self,
        project_id: str,
        node_id: str,
        *,
        reason: str,
    ) -> int:
        with self.project_lock(project_id):
            state = self._read_thread_state_unlocked(project_id)
            ask = self._ensure_node_state_unlocked(state, node_id)["ask"]
            blocked_count = 0

            for packet in ask.get("delta_context_packets", []):
                if not isinstance(packet, dict):
                    continue
                if packet.get("status") not in ("pending", "approved"):
                    continue
                packet["status"] = "blocked"
                packet["status_reason"] = reason
                blocked_count += 1

            if blocked_count:
                _bump_event_seq(ask)
                self._write_thread_state_unlocked(project_id, state)
            return blocked_count

    def _read_thread_state_unlocked(self, project_id: str) -> Dict[str, Any]:
        return load_json(self._thread_state_path(project_id), default={}) or {}

    def _write_thread_state_unlocked(self, project_id: str, payload: Dict[str, Any]) -> None:
        atomic_write_json(self._thread_state_path(project_id), payload)

    def _ensure_node_state_unlocked(self, state: dict[str, Any], node_id: str) -> dict[str, Any]:
        node_state = state.setdefault(node_id, {})
        node_state.setdefault("planning", _default_planning_state())
        node_state.setdefault("execution", _default_execution_state())
        node_state.setdefault("ask", _default_ask_state())
        return node_state

    def _default_node_state(self) -> dict[str, Any]:
        return {
            "planning": _default_planning_state(),
            "execution": _default_execution_state(),
            "ask": _default_ask_state(),
        }
