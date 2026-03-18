from __future__ import annotations

import pytest

from backend.ai.split_prompt_builder import validate_split_payload
from backend.services.canonical_split_fallback import build_canonical_split_fallback
from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY


def _task_context() -> dict[str, object]:
    return {
        "root_prompt": "Ship the approved split refactor",
        "current_node_prompt": "Implement split fallback orchestration",
    }


@pytest.mark.parametrize(
    ("mode", "expected_first_title"),
    [
        ("workflow", "Define the working flow"),
        ("simplify_workflow", "Ship the minimum valid path"),
        ("phase_breakdown", "Phase 1: Lowest-risk scaffold"),
        ("agent_breakdown", "Stabilize dependencies and inputs"),
    ],
)
def test_build_canonical_split_fallback_returns_valid_flat_payload(
    mode: str,
    expected_first_title: str,
) -> None:
    payload = build_canonical_split_fallback(mode, _task_context())  # type: ignore[arg-type]
    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]  # type: ignore[index]

    assert validate_split_payload(mode, payload) is True  # type: ignore[arg-type]
    assert len(payload["subtasks"]) == spec["min_items"]
    assert payload["subtasks"][0]["title"] == expected_first_title
    assert [item["id"] for item in payload["subtasks"]] == [
        f"S{index}" for index in range(1, len(payload["subtasks"]) + 1)
    ]
    assert all(set(item.keys()) == {"id", "title", "objective", "why_now"} for item in payload["subtasks"])


def test_build_canonical_split_fallback_uses_root_prompt_when_current_node_prompt_is_missing() -> None:
    payload = build_canonical_split_fallback(
        "workflow",
        {
            "root_prompt": "Ship the canonical split contract",
            "current_node_prompt": "",
        },
    )

    assert "Ship the canonical split contract" in payload["subtasks"][0]["objective"]
