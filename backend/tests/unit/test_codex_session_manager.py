from __future__ import annotations

from pathlib import Path

from backend.main import create_app
from backend.services.codex_session_manager import CodexSessionManager


class FakeCodexClient:
    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = workspace_root
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def status(self) -> dict[str, object]:
        return {
            "workspace_root": self.workspace_root,
            "client_started": False,
            "client_alive": False,
        }


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


def test_reset_session_only_affects_target_project() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)
    first = manager.get_or_create_session("project-a", "C:/workspace-a")
    second = manager.get_or_create_session("project-b", "C:/workspace-b")

    removed = manager.reset_session("project-a")

    assert removed is True
    assert manager.get_session("project-a") is None
    assert manager.get_session("project-b") is second
    assert first.client.stop_calls == 1
    assert second.client.stop_calls == 0


def test_missing_session_status_is_safe() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)

    status = manager.get_status("missing-project")

    assert status["project_id"] == "missing-project"
    assert status["exists"] is False
    assert status["health"]["status"] == "missing"
    assert status["runtime_request_count"] == 0


def test_shutdown_stops_all_sessions_and_clears_registry() -> None:
    manager = CodexSessionManager(client_factory=FakeCodexClient)
    first = manager.get_or_create_session("project-a", "C:/workspace-a")
    second = manager.get_or_create_session("project-b", "C:/workspace-b")

    manager.shutdown()

    assert first.client.stop_calls == 1
    assert second.client.stop_calls == 1
    assert manager.list_statuses() == []


def test_create_app_wires_session_manager_without_replacing_legacy_client(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path / "appdata")

    assert hasattr(app.state, "codex_session_manager")
    assert app.state.codex_session_manager is not None
    assert hasattr(app.state, "codex_client")
    assert app.state.codex_client is not None
