from __future__ import annotations

from backend.main import create_app


def test_execution_audit_v2_flags_are_not_exposed_in_app_state(tmp_path) -> None:
    app = create_app(data_root=tmp_path / "appdata-default")
    assert hasattr(app.state, "execution_audit_v2_enabled") is False
    assert hasattr(app.state, "execution_audit_v2_rehearsal_enabled") is False
