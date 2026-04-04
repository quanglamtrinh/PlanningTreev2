from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.projector.thread_event_projector_v3 import (
    project_v2_envelope_to_v3,
    project_v2_snapshot_to_v3,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "thread-rework"
    / "fileschanged"
    / "artifacts"
    / "execution-fileschanged-parity-fixtures.json"
)


def _load_scenarios() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return list(payload.get("scenarios") or [])


def _seed_execution_snapshot_v2() -> dict[str, Any]:
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "exec-thread-1"
    snapshot["activeTurnId"] = "turn-1"
    snapshot["processingState"] = "running"
    return snapshot


def _diff_items_by_id(snapshot_v3: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = snapshot_v3.get("items") if isinstance(snapshot_v3.get("items"), list) else []
    output: dict[str, dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("kind") or "") != "diff":
            continue
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            continue
        output[item_id] = raw
    return output


def test_execution_fileschanged_parity_fixtures_project_to_expected_diff_payloads() -> None:
    scenarios = _load_scenarios()
    assert scenarios, "Expected at least one fileschanged parity fixture scenario."

    for scenario in scenarios:
        snapshot_v3 = project_v2_snapshot_to_v3(_seed_execution_snapshot_v2())
        for envelope in scenario.get("events_v2") or []:
            snapshot_v3, _ = project_v2_envelope_to_v3(snapshot_v3, copy.deepcopy(envelope))

        diff_items = _diff_items_by_id(snapshot_v3)
        expected_diff_items = (
            scenario.get("expected", {}).get("diffItems")
            if isinstance(scenario.get("expected"), dict)
            else None
        )
        assert isinstance(expected_diff_items, dict), scenario.get("id")
        assert set(diff_items.keys()) == set(expected_diff_items.keys()), scenario.get("id")

        for item_id, expected_payload in expected_diff_items.items():
            assert isinstance(expected_payload, dict), scenario.get("id")
            current = diff_items[item_id]
            assert current.get("metadata", {}).get("semanticKind") == "fileChange", scenario.get("id")
            assert current.get("changes") == expected_payload.get("changes"), scenario.get("id")
            assert current.get("files") == expected_payload.get("files"), scenario.get("id")
            assert current.get("summaryText") == expected_payload.get("summaryText"), scenario.get("id")
