from __future__ import annotations

from backend.main import create_app


def test_execution_audit_v2_enabled_defaults_true_in_app_state(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", raising=False)
    app = create_app(data_root=tmp_path / "appdata-default")
    assert bool(getattr(app.state, "execution_audit_v2_enabled", False)) is True


def test_execution_audit_v2_enabled_false_respected_in_app_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "false")
    app = create_app(data_root=tmp_path / "appdata-disabled")
    assert bool(getattr(app.state, "execution_audit_v2_enabled", True)) is False
