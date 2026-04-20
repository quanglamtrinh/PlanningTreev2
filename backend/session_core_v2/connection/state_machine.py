from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.session_core_v2.errors import SessionCoreError

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "disconnected": {"connecting"},
    "connecting": {"initialized", "error"},
    "initialized": {"disconnected", "error"},
    "error": {"connecting"},
}


@dataclass(slots=True)
class ConnectionStateMachine:
    _phase: str = "disconnected"
    _client_name: str | None = None
    _server_version: str | None = None
    _error: dict[str, Any] | None = None
    _transition_history: list[tuple[str, str]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "phase": self._phase,
            "clientName": self._client_name,
            "serverVersion": self._server_version,
        }
        if self._error is not None:
            snapshot["error"] = self._error
        return snapshot

    @property
    def phase(self) -> str:
        return self._phase

    def transition(self, next_phase: str) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(self._phase, set())
        if next_phase not in allowed:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Illegal connection transition: {self._phase} -> {next_phase}",
                status_code=500,
                details={"from": self._phase, "to": next_phase},
            )
        self._transition_history.append((self._phase, next_phase))
        self._phase = next_phase

    def set_connecting(self) -> None:
        if self._phase == "error":
            self.transition("connecting")
        elif self._phase == "disconnected":
            self.transition("connecting")
        else:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Cannot enter connecting from {self._phase}",
                status_code=500,
                details={"phase": self._phase},
            )
        self._error = None

    def set_initialized(self, *, client_name: str | None, server_version: str | None) -> None:
        self.transition("initialized")
        self._client_name = client_name
        self._server_version = server_version
        self._error = None

    def set_error(self, *, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        if self._phase not in {"connecting", "initialized"}:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Cannot enter error from {self._phase}",
                status_code=500,
                details={"phase": self._phase},
            )
        self.transition("error")
        self._error = {
            "code": code,
            "message": message,
            "details": details or {},
        }

    def set_disconnected(self) -> None:
        if self._phase != "initialized":
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message=f"Cannot disconnect from {self._phase}",
                status_code=500,
                details={"phase": self._phase},
            )
        self.transition("disconnected")
