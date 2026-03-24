from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.errors.app_errors import ProjectNotFound
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now, load_json
from backend.storage.project_locks import ProjectLockRegistry
from backend.storage.workspace_store import WorkspaceStore

_VALID_THREAD_ROLES = {"audit", "ask_planning", "execution", "integration"}
_DEFAULT_THREAD_ROLE = "ask_planning"


def _default_session(thread_role: str = _DEFAULT_THREAD_ROLE) -> dict[str, Any]:
    now = iso_now()
    return {
        "thread_id": None,
        "thread_role": thread_role,
        "active_turn_id": None,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }


class ChatStateStore:
    def __init__(
        self,
        paths: AppPaths,
        workspace_store: WorkspaceStore,
        lock_registry: ProjectLockRegistry,
    ) -> None:
        self._paths = paths
        self._workspace_store = workspace_store
        self._lock_registry = lock_registry

    def _project_dir(self, project_id: str) -> Path:
        folder_path = self._workspace_store.get_folder_path(project_id)
        return Path(folder_path).expanduser().resolve() / ".planningtree"

    def _chat_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "chat"

    def _flat_path(self, project_id: str, node_id: str) -> Path:
        """Legacy flat file path: chat/{node_id}.json"""
        return self._chat_dir(project_id) / f"{node_id}.json"

    def _role_dir(self, project_id: str, node_id: str) -> Path:
        """Directory for per-role sessions: chat/{node_id}/"""
        return self._chat_dir(project_id) / node_id

    def _role_path(self, project_id: str, node_id: str, thread_role: str) -> Path:
        """Per-role session path: chat/{node_id}/{role}.json"""
        return self._role_dir(project_id, node_id) / f"{thread_role}.json"

    def path(self, project_id: str, node_id: str, thread_role: str = _DEFAULT_THREAD_ROLE) -> Path:
        """Public path accessor. Returns the role-based path."""
        return self._role_path(project_id, node_id, thread_role)

    def _maybe_migrate(self, project_id: str, node_id: str) -> None:
        """Lazy migration: move flat chat/{node_id}.json to chat/{node_id}/ask_planning.json.

        Migration triggers when the flat file exists AND ask_planning.json does not.
        The directory may already exist (e.g. an audit session was created first);
        we still migrate the flat file into it.  The flat file is only removed after
        ask_planning.json is successfully written.  If both exist, the directory
        version wins and the flat file is kept as-is (no silent deletion).
        """
        flat = self._flat_path(project_id, node_id)
        if not flat.exists():
            return

        target = self._role_path(project_id, node_id, _DEFAULT_THREAD_ROLE)
        if target.exists():
            # Already migrated (or written directly). Keep flat file intact.
            return

        payload = load_json(flat, default=None)
        if payload is None:
            flat.unlink(missing_ok=True)
            return

        if isinstance(payload, dict):
            payload["thread_role"] = _DEFAULT_THREAD_ROLE

        ensure_dir(target.parent)
        atomic_write_json(target, payload)
        flat.unlink(missing_ok=True)

    def read_session(
        self, project_id: str, node_id: str, thread_role: str = _DEFAULT_THREAD_ROLE
    ) -> dict[str, Any]:
        role = thread_role if thread_role in _VALID_THREAD_ROLES else _DEFAULT_THREAD_ROLE
        with self._lock_registry.for_project(project_id):
            self._maybe_migrate(project_id, node_id)
            payload = load_json(self._role_path(project_id, node_id, role), default=None)
            return self._normalize_session(payload, role)

    def write_session(
        self, project_id: str, node_id: str, session: dict[str, Any],
        thread_role: str = _DEFAULT_THREAD_ROLE,
    ) -> dict[str, Any]:
        role = thread_role if thread_role in _VALID_THREAD_ROLES else _DEFAULT_THREAD_ROLE
        with self._lock_registry.for_project(project_id):
            project_dir = self._project_dir(project_id)
            if not project_dir.exists():
                raise ProjectNotFound(project_id)
            self._maybe_migrate(project_id, node_id)
            normalized = self._normalize_session(session, role)
            normalized["updated_at"] = iso_now()
            target = self._role_path(project_id, node_id, role)
            ensure_dir(target.parent)
            atomic_write_json(target, normalized)
            return copy.deepcopy(normalized)

    def clear_session(
        self, project_id: str, node_id: str, thread_role: str = _DEFAULT_THREAD_ROLE
    ) -> dict[str, Any]:
        role = thread_role if thread_role in _VALID_THREAD_ROLES else _DEFAULT_THREAD_ROLE
        return self.write_session(project_id, node_id, _default_session(role), thread_role=role)

    def clear_all_sessions(self, project_id: str) -> None:
        chat_dir = self._chat_dir(project_id)
        if chat_dir.exists():
            shutil.rmtree(chat_dir, ignore_errors=True)

    def _normalize_session(self, payload: Any, thread_role: str = _DEFAULT_THREAD_ROLE) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return _default_session(thread_role)

        thread_id = payload.get("thread_id")
        active_turn_id = payload.get("active_turn_id")
        raw_messages = payload.get("messages")
        created_at = payload.get("created_at")
        updated_at = payload.get("updated_at")
        raw_role = payload.get("thread_role")

        role = raw_role if isinstance(raw_role, str) and raw_role in _VALID_THREAD_ROLES else thread_role

        messages: list[dict[str, Any]] = []
        if isinstance(raw_messages, list):
            for raw in raw_messages:
                msg = self._normalize_message(raw)
                if msg is not None:
                    messages.append(msg)

        return {
            "thread_id": thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None,
            "thread_role": role,
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
