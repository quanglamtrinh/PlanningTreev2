from __future__ import annotations

from backend.config.app_config import (
    get_conversation_v3_bridge_allowlist,
    get_conversation_v3_bridge_mode,
    get_v3_lane_compat_mode,
    is_ask_v3_backend_enabled,
    is_ask_v3_frontend_enabled,
    is_conversation_v3_bridge_allowed_for_project,
    is_execution_audit_v2_enabled,
    is_execution_audit_v2_rehearsal_enabled,
    is_v3_lane_compat_enabled,
)


def test_execution_audit_v2_rehearsal_defaults_to_false(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)
    assert is_execution_audit_v2_rehearsal_enabled() is False


def test_execution_audit_v2_rehearsal_accepts_true_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", "true")
    assert is_execution_audit_v2_rehearsal_enabled() is True


def test_execution_audit_v2_enabled_defaults_to_true(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", raising=False)
    assert is_execution_audit_v2_enabled() is True


def test_execution_audit_v2_enabled_accepts_false_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "0")
    assert is_execution_audit_v2_enabled() is False


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


def test_conversation_v3_bridge_mode_defaults_to_enabled(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", raising=False)
    assert get_conversation_v3_bridge_mode() == "enabled"


def test_conversation_v3_bridge_mode_invalid_falls_back_to_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "weird")
    assert get_conversation_v3_bridge_mode() == "enabled"


def test_conversation_v3_bridge_allowlist_parses_csv(monkeypatch) -> None:
    monkeypatch.setenv(
        "PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST",
        " project-a , ,project-b,project-c  ",
    )
    assert get_conversation_v3_bridge_allowlist() == {"project-a", "project-b", "project-c"}


def test_conversation_v3_bridge_project_gate(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE", "allowlist")
    monkeypatch.setenv("PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST", "project-a,project-b")
    assert is_conversation_v3_bridge_allowed_for_project("project-a") is True
    assert is_conversation_v3_bridge_allowed_for_project("project-z") is False


def test_v3_lane_compat_mode_defaults_to_enabled(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_V3_LANE_COMPAT_MODE", raising=False)
    assert get_v3_lane_compat_mode() == "enabled"
    assert is_v3_lane_compat_enabled() is True


def test_v3_lane_compat_mode_invalid_falls_back_to_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_V3_LANE_COMPAT_MODE", "strange")
    assert get_v3_lane_compat_mode() == "enabled"
    assert is_v3_lane_compat_enabled() is True


def test_v3_lane_compat_mode_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_V3_LANE_COMPAT_MODE", "disabled")
    assert get_v3_lane_compat_mode() == "disabled"
    assert is_v3_lane_compat_enabled() is False
