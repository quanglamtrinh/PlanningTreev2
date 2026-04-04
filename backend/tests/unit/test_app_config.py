from __future__ import annotations

from backend.config.app_config import (
    is_ask_v3_backend_enabled,
    is_ask_v3_frontend_enabled,
    is_execution_audit_v2_rehearsal_enabled,
)


def test_execution_audit_v2_rehearsal_defaults_to_false(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)
    assert is_execution_audit_v2_rehearsal_enabled() is False


def test_execution_audit_v2_rehearsal_accepts_true_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", "true")
    assert is_execution_audit_v2_rehearsal_enabled() is True


def test_ask_v3_gates_default_to_true(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_ASK_V3_BACKEND_ENABLED", raising=False)
    monkeypatch.delenv("PLANNINGTREE_ASK_V3_FRONTEND_ENABLED", raising=False)
    assert is_ask_v3_backend_enabled() is True
    assert is_ask_v3_frontend_enabled() is True


def test_ask_v3_gates_accept_false_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_ASK_V3_BACKEND_ENABLED", "false")
    monkeypatch.setenv("PLANNINGTREE_ASK_V3_FRONTEND_ENABLED", "0")
    assert is_ask_v3_backend_enabled() is False
    assert is_ask_v3_frontend_enabled() is False
