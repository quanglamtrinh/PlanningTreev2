from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, iso_now, load_json
from backend.storage.project_ids import normalize_project_id
from backend.storage.project_locks import ProjectLockRegistry


def _default_session() -> dict[str, Any]:
    now = iso_now()
    return {
        "thread_id": None,
        "active_turn_id": None,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }


class ChatStateStore:
    def __init__(self, paths: AppPaths, lock_registry: ProjectLockRegistry) -> None:
        self._paths = paths
        self._lock_registry = lock_registry

    def _chat_dir(self, project_id: str) -> Path:
        normalized = normalize_project_id(project_id)
        return self._paths.projects_root / normalized / "chat"

    def path(self, project_id: str, node_id: str) -> Path:
        return self._chat_dir(project_id) / f"{node_id}.json"

    def read_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            payload = load_json(self.path(project_id, node_id), default=None)
            return self._normalize_session(payload)

    def write_session(self, project_id: str, node_id: str, session: dict[str, Any]) -> dict[str, Any]:
        with self._lock_registry.for_project(project_id):
            project_dir = self._chat_dir(project_id).parent
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            normalized = self._normalize_session(session)
            normalized["updated_at"] = iso_now()
            atomic_write_json(self.path(project_id, node_id), normalized)
            return copy.deepcopy(normalized)

    def clear_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        return self.write_session(project_id, node_id, _default_session())

    def clear_all_sessions(self, project_id: str) -> None:
        chat_dir = self._chat_dir(project_id)
        if chat_dir.exists():
            shutil.rmtree(chat_dir, ignore_errors=True)

    def _normalize_session(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return _default_session()

        thread_id = payload.get("thread_id")
        active_turn_id = payload.get("active_turn_id")
        raw_messages = payload.get("messages")
        created_at = payload.get("created_at")
        updated_at = payload.get("updated_at")

        messages: list[dict[str, Any]] = []
        if isinstance(raw_messages, list):
            for raw in raw_messages:
                msg = self._normalize_message(raw)
                if msg is not None:
                    messages.append(msg)

        return {
            "thread_id": thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None,
            "active_turn_id": (
                active_turn_id.strip()
                if isinstance(active_turn_id, str) and active_turn_id.strip()
                else None
            ),
            "messages": messages,
            "created_at": created_at if isinstance(created_at, str) and created_at.strip() else iso_now(),
            "updated_at": updated_at if isinstance(updated_at, str) and updated_at.strip() else iso_now(),
        }

    def _normalize_message(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        message_id = raw.get("message_id")
        role = raw.get("role")
        if not isinstance(message_id, str) or not message_id.strip():
            return None
        if role not in ("user", "assistant"):
            return None

        content = raw.get("content")
        status = raw.get("status")
        error = raw.get("error")
        turn_id = raw.get("turn_id")
        created_at = raw.get("created_at")
        updated_at = raw.get("updated_at")

        parts = raw.get("parts")
        normalized_parts: list[dict[str, Any]] | None = None
        if isinstance(parts, list):
            normalized_parts = [p for p in parts if isinstance(p, dict) and isinstance(p.get("type"), str)]

        result: dict[str, Any] = {
            "message_id": message_id.strip(),
            "role": role,
            "content": str(content) if content is not None else "",
            "status": status if isinstance(status, str) and status in ("pending", "streaming", "completed", "error") else "pending",
            "error": str(error) if isinstance(error, str) and error.strip() else None,
            "turn_id": turn_id.strip() if isinstance(turn_id, str) and turn_id.strip() else None,
            "created_at": created_at if isinstance(created_at, str) and created_at.strip() else iso_now(),
            "updated_at": updated_at if isinstance(updated_at, str) and updated_at.strip() else iso_now(),
        }
        if normalized_parts is not None:
            result["parts"] = normalized_parts
        return result
