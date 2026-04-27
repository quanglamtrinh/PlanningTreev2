from __future__ import annotations

from fastapi.testclient import TestClient

from backend.services.ask_rollout_metrics_service import AskRolloutMetricsService


def test_ask_rollout_metrics_service_computes_rates() -> None:
    service = AskRolloutMetricsService()
    service.record_stream_session()
    service.record_stream_error()
    service.record_shaping_action_started()
    service.record_shaping_action_started()
    service.record_shaping_action_failed()

    payload = service.as_public_payload()
    assert payload["ask_stream_session_total"] == 1
    assert payload["ask_stream_error_total"] == 1
    assert payload["ask_stream_error_rate"] == 1.0
    assert payload["ask_shaping_action_total"] == 2
    assert payload["ask_shaping_action_failed_total"] == 1
    assert payload["ask_shaping_action_failed_rate"] == 0.5


def test_bootstrap_ask_rollout_metrics_event_endpoints(client: TestClient) -> None:
    initial = client.get("/v3/ask-rollout/metrics")
    assert initial.status_code == 200
    initial_payload = initial.json()
    assert initial_payload["ask_stream_reconnect_total"] == 0
    assert initial_payload["ask_stream_error_total"] == 0

    reconnect = client.post("/v3/ask-rollout/metrics/events", json={"event": "stream_reconnect"})
    assert reconnect.status_code == 200
    assert reconnect.json() == {"ok": True}

    stream_error = client.post("/v3/ask-rollout/metrics/events", json={"event": "stream_error"})
    assert stream_error.status_code == 200
    assert stream_error.json() == {"ok": True}

    updated = client.get("/v3/ask-rollout/metrics")
    assert updated.status_code == 200
    updated_payload = updated.json()
    assert updated_payload["ask_stream_reconnect_total"] == 1
    assert updated_payload["ask_stream_error_total"] == 1
