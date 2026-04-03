from __future__ import annotations

from backend.config.app_config import (
    is_audit_uiux_v3_frontend_enabled,
    is_execution_uiux_v3_frontend_enabled,
    is_execution_audit_v2_enabled,
    is_execution_audit_v2_rehearsal_enabled,
    is_execution_audit_uiux_v3_backend_enabled,
    is_execution_audit_uiux_v3_frontend_enabled,
)


def test_execution_audit_v2_enabled_defaults_to_true(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", raising=False)
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)

    assert is_execution_audit_v2_enabled() is True


def test_execution_audit_v2_enabled_respects_explicit_false(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "0")
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)

    assert is_execution_audit_v2_enabled() is False


def test_execution_audit_v2_enabled_yields_to_rehearsal_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", raising=False)
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", "1")

    assert is_execution_audit_v2_rehearsal_enabled() is True
    assert is_execution_audit_v2_enabled() is False


def test_execution_audit_uiux_v3_backend_enabled_defaults_to_false(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_BACKEND", raising=False)

    assert is_execution_audit_uiux_v3_backend_enabled() is False


def test_execution_audit_uiux_v3_frontend_enabled_defaults_to_false(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND", raising=False)

    assert is_execution_audit_uiux_v3_frontend_enabled() is False


def test_execution_audit_uiux_v3_flags_accept_true_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_BACKEND", "true")
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND", "1")

    assert is_execution_audit_uiux_v3_backend_enabled() is True
    assert is_execution_audit_uiux_v3_frontend_enabled() is True


def test_lane_scoped_frontend_flags_fallback_to_shared_flag(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND", "1")
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_UIUX_V3_FRONTEND", raising=False)
    monkeypatch.delenv("PLANNINGTREE_AUDIT_UIUX_V3_FRONTEND", raising=False)

    assert is_execution_uiux_v3_frontend_enabled() is True
    assert is_audit_uiux_v3_frontend_enabled() is True


def test_lane_scoped_frontend_flags_override_shared_flag(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_UIUX_V3_FRONTEND", "0")
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_UIUX_V3_FRONTEND", "1")
    monkeypatch.setenv("PLANNINGTREE_AUDIT_UIUX_V3_FRONTEND", "true")

    assert is_execution_uiux_v3_frontend_enabled() is True
    assert is_audit_uiux_v3_frontend_enabled() is True
