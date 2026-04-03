from __future__ import annotations

from backend.config.app_config import is_execution_audit_v2_rehearsal_enabled


def test_execution_audit_v2_rehearsal_defaults_to_false(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)
    assert is_execution_audit_v2_rehearsal_enabled() is False


def test_execution_audit_v2_rehearsal_accepts_true_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", "true")
    assert is_execution_audit_v2_rehearsal_enabled() is True
