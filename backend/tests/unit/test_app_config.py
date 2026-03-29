from __future__ import annotations

from backend.config.app_config import (
    is_execution_audit_v2_enabled,
    is_execution_audit_v2_rehearsal_enabled,
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
