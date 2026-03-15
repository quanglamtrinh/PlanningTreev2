from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class RuntimeThreadState:
    thread_id: str
    last_used_at: str
    active_turn_id: str | None = None
    status: str = "idle"


@dataclass
class SessionHealthState:
    status: str = "created"
    last_checked_at: str | None = None
    last_error: str | None = None


@dataclass
class ProjectCodexSession:
    project_id: str
    workspace_root: str
    client: Any
    loaded_runtime_threads: dict[str, RuntimeThreadState] = field(default_factory=dict)
    active_streams: dict[str, str] = field(default_factory=dict)
    active_turns: dict[str, str] = field(default_factory=dict)
    runtime_request_registry: dict[str, dict[str, Any]] = field(default_factory=dict)
    health: SessionHealthState = field(default_factory=SessionHealthState)
    lock: Any = field(default_factory=RLock)
    created_at: str = field(default_factory=_iso_now)
    last_accessed_at: str = field(default_factory=_iso_now)

    def status_snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "project_id": self.project_id,
                "workspace_root": self.workspace_root,
                "exists": True,
                "loaded_runtime_threads": {
                    thread_id: asdict(thread_state)
                    for thread_id, thread_state in sorted(self.loaded_runtime_threads.items())
                },
                "active_streams": dict(sorted(self.active_streams.items())),
                "active_turns": dict(sorted(self.active_turns.items())),
                "runtime_request_count": len(self.runtime_request_registry),
                "health": asdict(self.health),
                "created_at": self.created_at,
                "last_accessed_at": self.last_accessed_at,
            }


class CodexSessionManager:
    def __init__(self, client_factory: Callable[[str], Any]) -> None:
        self._client_factory = client_factory
        self._sessions: dict[str, ProjectCodexSession] = {}
        self._lock = RLock()

    def get_or_create_session(self, project_id: str, workspace_root: str) -> ProjectCodexSession:
        project_key = str(project_id).strip()
        if not project_key:
            raise ValueError("project_id is required")
        workspace_value = str(workspace_root).strip()
        if not workspace_value:
            raise ValueError("workspace_root is required")

        with self._lock:
            session = self._sessions.get(project_key)
            if session is None:
                session = ProjectCodexSession(
                    project_id=project_key,
                    workspace_root=workspace_value,
                    client=self._client_factory(workspace_value),
                )
                self._sessions[project_key] = session
        with session.lock:
            session.last_accessed_at = _iso_now()
            if not session.workspace_root:
                session.workspace_root = workspace_value
        return session

    def get_session(self, project_id: str) -> ProjectCodexSession | None:
        with self._lock:
            session = self._sessions.get(str(project_id).strip())
        if session is not None:
            with session.lock:
                session.last_accessed_at = _iso_now()
        return session

    def reset_session(self, project_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(str(project_id).strip(), None)
        if session is None:
            return False
        self._stop_session_client(session)
        return True

    def get_status(self, project_id: str) -> dict[str, Any]:
        session = self.get_session(project_id)
        if session is None:
            return {
                "project_id": str(project_id).strip(),
                "exists": False,
                "workspace_root": None,
                "loaded_runtime_threads": {},
                "active_streams": {},
                "active_turns": {},
                "runtime_request_count": 0,
                "health": {
                    "status": "missing",
                    "last_checked_at": _iso_now(),
                    "last_error": None,
                },
                "created_at": None,
                "last_accessed_at": None,
            }
        with session.lock:
            session.health.last_checked_at = _iso_now()
            try:
                client_status = self._client_status(session.client)
                if client_status.get("client_alive"):
                    session.health.status = "ready"
                    session.health.last_error = None
                else:
                    session.health.status = session.health.status or "created"
            except Exception as exc:
                client_status = {}
                session.health.status = "error"
                session.health.last_error = str(exc)
            snapshot = session.status_snapshot()
            snapshot["client_status"] = client_status
            return snapshot

    def list_statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            project_ids = sorted(self._sessions.keys())
        return [self.get_status(project_id) for project_id in project_ids]

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            self._stop_session_client(session)

    def _client_status(self, client: Any) -> dict[str, Any]:
        if hasattr(client, "status") and callable(client.status):
            status = client.status()
            if isinstance(status, dict):
                return dict(status)
        return {}

    def _stop_session_client(self, session: ProjectCodexSession) -> None:
        with session.lock:
            session.active_streams.clear()
            session.active_turns.clear()
            session.runtime_request_registry.clear()
            for thread_state in session.loaded_runtime_threads.values():
                thread_state.active_turn_id = None
                thread_state.status = "stopped"
                thread_state.last_used_at = _iso_now()
            session.health.status = "stopped"
            session.health.last_checked_at = _iso_now()
        if hasattr(session.client, "stop") and callable(session.client.stop):
            session.client.stop()
