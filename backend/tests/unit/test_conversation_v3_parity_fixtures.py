from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from backend.conversation.projector.thread_event_projector_v3 import (
    project_v2_envelope_to_v3,
    project_v2_snapshot_to_v3,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "thread-rework"
    / "uiux"
    / "artifacts"
    / "parity-fixtures"
    / "execution-audit-v3-parity-fixtures.json"
)


def _load_scenarios() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return list(payload.get("scenarios") or [])


def _normalize_snapshot(snapshot_v3: dict[str, Any]) -> dict[str, Any]:
    items = list(snapshot_v3.get("items") or [])
    pending = list(snapshot_v3.get("uiSignals", {}).get("activeUserInputRequests") or [])
    thread_role = str(snapshot_v3.get("threadRole") or "").strip()
    if not thread_role:
        lane = str(snapshot_v3.get("lane") or "").strip()
        if lane == "ask":
            thread_role = "ask_planning"
        elif lane in {"execution", "audit"}:
            thread_role = lane
    return {
        "thread_role": thread_role,
        "threadId": snapshot_v3.get("threadId"),
        "item_order": [item.get("id") for item in items],
        "item_kinds": [item.get("kind") for item in items],
        "plan_ready": snapshot_v3.get("uiSignals", {}).get("planReady"),
        "pending_request_statuses": [request.get("status") for request in pending],
    }


def test_v3_parity_fixtures_project_to_expected_snapshots() -> None:
    scenarios = _load_scenarios()
    assert scenarios, "Expected at least one parity fixture scenario."

    for scenario in scenarios:
        snapshot_v2 = copy.deepcopy(scenario["snapshot_v2"])
        events_v2 = [copy.deepcopy(event) for event in scenario.get("events_v2") or []]

        projected = project_v2_snapshot_to_v3(snapshot_v2)
        for envelope in events_v2:
            projected, _ = project_v2_envelope_to_v3(projected, envelope)

        expected = dict(scenario["expected"])
        normalized = _normalize_snapshot(projected)

        expected_thread_role = {"ask": "ask_planning"}.get(expected["lane"], expected["lane"])
        assert normalized["thread_role"] == expected_thread_role, scenario["id"]
        assert normalized["item_order"] == expected["item_order"], scenario["id"]
        assert normalized["item_kinds"] == expected["item_kinds"], scenario["id"]
        assert normalized["plan_ready"] == expected["plan_ready"], scenario["id"]
        assert normalized["pending_request_statuses"] == expected["pending_request_statuses"], scenario["id"]

        fixture_snapshot_v3 = dict(scenario["snapshot_v3"])
        assert _normalize_snapshot(fixture_snapshot_v3) == normalized, scenario["id"]
