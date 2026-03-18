from __future__ import annotations

from pathlib import Path

from backend.main import create_app
from backend.services.codex_session_manager import (
    CodexSessionManager,
    RuntimeThreadState,
    SessionWorkspaceRootMismatchError,
)


class FakeCodexClient:
    def __init__(
        self,
        workspace_root: str,
        *,
        client_alive: bool = False,
        status_error: Exception | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.client_alive = client_alive
        self.status_error = status_error
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def status(self) -> dict[str, object]:
        if self.status_error is not None:
            raise self.status_error
        return {
            "workspace_root": self.workspace_root,
            "client_started": self.client_alive,
            "client_alive": self.client_alive,
        }


def populate_session_runtime_state(session, *, suffix: str) -> None:
    with session.lock:
        session.active_streams[f"conversation-{suffix}"] = f"stream-{suffix}"
        session.active_turns[f"conversation-{suffix}"] = f"turn-{suffix}"
        session.runtime_request_registry[f"request-{suffix}"] = {"status": "pending"}
        session.loaded_runtime_threads[f"thread-{suffix}"] = RuntimeThreadState(
            thread_id=f"thread-{suffix}",
            last_used_at="2026-03-14T00:00:00Z",
            active_turn_id=f"turn-{suffix}",
            status="active",
        )
        session.health.last_error = f"error-{suffix}"


def test_same_project_reuses_same_session_and_client() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)

    first = manager.get_or_create_session("project-a", "C:/workspace-a")
    second = manager.get_or_create_session("project-a", "C:/workspace-a")

    assert first is second
    assert first.client is second.client
    assert first.workspace_root == "C:/workspace-a"


def test_different_projects_create_isolated_sessions() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)

    first = manager.get_or_create_session("project-a", "C:/workspace-a")
    second = manager.get_or_create_session("project-b", "C:/workspace-b")

    assert first is not second
    assert first.client is not second.client
    assert first.project_id == "project-a"
    assert second.project_id == "project-b"


def test_same_project_conflicting_workspace_root_raises_session_workspace_root_mismatch_error() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)
    manager.get_or_create_session("project-a", "C:/workspace-a")

    try:
        manager.get_or_create_session("project-a", "D:/workspace-b")
    except SessionWorkspaceRootMismatchError as exc:
        assert exc.project_id == "project-a"
        assert exc.existing_workspace_root == "C:/workspace-a"
        assert exc.requested_workspace_root == "D:/workspace-b"
    else:
        raise AssertionError("Expected conflicting workspace_root to be rejected")


def test_reset_session_only_affects_target_project() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)
    first = manager.get_or_create_session("project-a", "C:/workspace-a")
    second = manager.get_or_create_session("project-b", "C:/workspace-b")
    populate_session_runtime_state(first, suffix="a")
    populate_session_runtime_state(second, suffix="b")

    removed = manager.reset_session("project-a")

    assert removed is True
    assert manager.get_session("project-a") is None
    assert manager.get_session("project-b") is second
    assert first.client.stop_calls == 1
    assert second.client.stop_calls == 0
    assert first.active_streams == {}
    assert first.active_turns == {}
    assert first.runtime_request_registry == {}
    assert first.loaded_runtime_threads["thread-a"].active_turn_id is None
    assert first.loaded_runtime_threads["thread-a"].status == "stopped"
    assert first.health.status == "stopped"
    assert first.health.last_error is None
    assert second.active_streams == {"conversation-b": "stream-b"}
    assert second.active_turns == {"conversation-b": "turn-b"}
    assert second.runtime_request_registry == {"request-b": {"status": "pending"}}
    assert second.loaded_runtime_threads["thread-b"].active_turn_id == "turn-b"
    assert second.loaded_runtime_threads["thread-b"].status == "active"


def test_missing_session_status_is_safe() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)

    status = manager.get_status("missing-project")

    assert status["project_id"] == "missing-project"
    assert status["exists"] is False
    assert status["health"]["status"] == "missing"
    assert status["runtime_request_count"] == 0


def test_existing_session_status_reports_idle_when_client_not_alive() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)
    manager.get_or_create_session("project-a", "C:/workspace-a")

    status = manager.get_status("project-a")

    assert status["exists"] is True
    assert status["health"]["status"] == "idle"
    assert status["health"]["last_error"] is None
    assert status["client_status"]["client_alive"] is False


def test_existing_session_status_reports_ready_when_client_alive() -> None:
    manager = CodexSessionManager(
        client_factory=lambda workspace_root: FakeCodexClient(workspace_root, client_alive=True)
    )
    manager.get_or_create_session("project-a", "C:/workspace-a")

    status = manager.get_status("project-a")

    assert status["exists"] is True
    assert status["health"]["status"] == "ready"
    assert status["health"]["last_error"] is None
    assert status["client_status"]["client_alive"] is True


def test_existing_session_status_reports_error_when_client_status_fails() -> None:
    manager = CodexSessionManager(
        client_factory=lambda workspace_root: FakeCodexClient(
            workspace_root,
            status_error=RuntimeError("status failed"),
        )
    )
    manager.get_or_create_session("project-a", "C:/workspace-a")

    status = manager.get_status("project-a")

    assert status["exists"] is True
    assert status["health"]["status"] == "error"
    assert status["health"]["last_error"] == "status failed"
    assert status["client_status"] == {}


def test_shutdown_stops_all_sessions_and_clears_registry() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)
    first = manager.get_or_create_session("project-a", "C:/workspace-a")
    second = manager.get_or_create_session("project-b", "C:/workspace-b")
    populate_session_runtime_state(first, suffix="a")
    populate_session_runtime_state(second, suffix="b")

    manager.shutdown()

    assert first.client.stop_calls == 1
    assert second.client.stop_calls == 1
    assert first.active_streams == {}
    assert first.active_turns == {}
    assert first.runtime_request_registry == {}
    assert second.active_streams == {}
    assert second.active_turns == {}
    assert second.runtime_request_registry == {}
    assert first.loaded_runtime_threads["thread-a"].active_turn_id is None
    assert first.loaded_runtime_threads["thread-a"].status == "stopped"
    assert second.loaded_runtime_threads["thread-b"].active_turn_id is None
    assert second.loaded_runtime_threads["thread-b"].status == "stopped"
    assert first.health.status == "stopped"
    assert second.health.status == "stopped"
    assert first.health.last_error is None
    assert second.health.last_error is None
    assert manager.list_statuses() == []


def test_create_app_wires_session_manager_without_replacing_legacy_client(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path / "appdata")

    assert hasattr(app.state, "codex_session_manager")
    assert app.state.codex_session_manager is not None
    assert hasattr(app.state, "codex_client")
    assert app.state.codex_client is not None
