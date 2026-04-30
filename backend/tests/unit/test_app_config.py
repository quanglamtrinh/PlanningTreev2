from __future__ import annotations

from backend.config.app_config import (
    get_session_core_v2_protocol_gate_timeout_sec,
    get_thread_raw_event_coalesce_ms,
    get_thread_stream_cadence_profile,
    is_ask_followup_queue_enabled,
    is_session_core_v2_protocol_gate_enabled,
)


def test_ask_followup_queue_gate_defaults_to_false(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_ASK_FOLLOWUP_QUEUE_ENABLED", raising=False)
    assert is_ask_followup_queue_enabled() is False


def test_ask_followup_queue_gate_accepts_true_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_ASK_FOLLOWUP_QUEUE_ENABLED", "true")
    assert is_ask_followup_queue_enabled() is True


def test_thread_stream_cadence_profile_defaults_to_high(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", raising=False)
    assert get_thread_stream_cadence_profile() == "high"


def test_thread_stream_cadence_profile_accepts_valid_values(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "HIGH")
    assert get_thread_stream_cadence_profile() == "high"


def test_thread_raw_event_coalesce_uses_explicit_ms_override(monkeypatch) -> None:
    monkeypatch.setenv("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "low")
    monkeypatch.setenv("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS", "18")
    assert get_thread_raw_event_coalesce_ms() == 18


def test_thread_raw_event_coalesce_uses_profile_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PLANNINGTREE_THREAD_RAW_EVENT_COALESCE_MS", raising=False)

    monkeypatch.setenv("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "low")
    assert get_thread_raw_event_coalesce_ms() == 60

    monkeypatch.setenv("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "standard")
    assert get_thread_raw_event_coalesce_ms() == 25

    monkeypatch.setenv("PLANNINGTREE_THREAD_STREAM_CADENCE_PROFILE", "high")
    assert get_thread_raw_event_coalesce_ms() == 20


def test_session_core_v2_protocol_gate_defaults_enabled(monkeypatch) -> None:
    monkeypatch.delenv("SESSION_CORE_V2_PROTOCOL_GATE_ENABLED", raising=False)
    assert is_session_core_v2_protocol_gate_enabled() is True


def test_session_core_v2_protocol_gate_accepts_false(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_CORE_V2_PROTOCOL_GATE_ENABLED", "false")
    assert is_session_core_v2_protocol_gate_enabled() is False


def test_session_core_v2_protocol_gate_timeout_defaults_and_bounds(monkeypatch) -> None:
    monkeypatch.delenv("SESSION_CORE_V2_PROTOCOL_GATE_TIMEOUT_SEC", raising=False)
    assert get_session_core_v2_protocol_gate_timeout_sec() == 12

    monkeypatch.setenv("SESSION_CORE_V2_PROTOCOL_GATE_TIMEOUT_SEC", "1")
    assert get_session_core_v2_protocol_gate_timeout_sec() == 3

    monkeypatch.setenv("SESSION_CORE_V2_PROTOCOL_GATE_TIMEOUT_SEC", "200")
    assert get_session_core_v2_protocol_gate_timeout_sec() == 60


