from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config.app_config import build_app_paths
from backend.main import create_app
from backend.services.node_service import NodeService
from backend.services.project_service import ProjectService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage


def init_git_repo(workspace: Path) -> None:
    """Initialize a git repo in *workspace* with an initial commit.

    This is needed by tests that exercise finish-task, since git guardrails
    require a clean git repo.
    """
    subprocess.run(["git", "init", "-b", "main"], cwd=str(workspace), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(workspace), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(workspace), check=True, capture_output=True)
    (workspace / ".gitignore").write_text(".planningtree/\n")
    subprocess.run(["git", "add", "-A"], cwd=str(workspace), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(workspace), check=True, capture_output=True)


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "appdata"


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    return path


@pytest.fixture
def storage(data_root: Path) -> Storage:
    return Storage(build_app_paths(data_root))


@pytest.fixture
def tree_service() -> TreeService:
    return TreeService()


@pytest.fixture
def project_service(storage: Storage) -> ProjectService:
    return ProjectService(storage)


@pytest.fixture
def node_service(storage: Storage, tree_service: TreeService) -> NodeService:
    return NodeService(storage, tree_service)


@pytest.fixture
def client(data_root: Path) -> TestClient:
    app = create_app(data_root=data_root)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def disable_session_core_v2_protocol_gate_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_CORE_V2_PROTOCOL_GATE_ENABLED", "false")
