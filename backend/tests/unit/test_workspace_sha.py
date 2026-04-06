from __future__ import annotations

from pathlib import Path

from backend.services.workspace_sha import compute_workspace_sha


def test_workspace_sha_ignores_dependency_and_git_dirs(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    (workspace_root / "src").mkdir()
    (workspace_root / "src" / "main.txt").write_text("v1\n", encoding="utf-8")
    (workspace_root / "node_modules").mkdir()
    (workspace_root / "node_modules" / "pkg.txt").write_text("dep-v1\n", encoding="utf-8")
    (workspace_root / ".git").mkdir()
    (workspace_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    baseline = compute_workspace_sha(workspace_root)

    (workspace_root / "node_modules" / "pkg.txt").write_text("dep-v2\n", encoding="utf-8")
    (workspace_root / ".git" / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    ignored_change = compute_workspace_sha(workspace_root)
    assert ignored_change == baseline

    (workspace_root / "src" / "main.txt").write_text("v2\n", encoding="utf-8")
    source_change = compute_workspace_sha(workspace_root)
    assert source_change != baseline
    assert source_change.startswith("sha256:")

