from __future__ import annotations

import pytest

from backend.ai.split_prompt_builder import (
    build_hidden_retry_feedback,
    build_planning_base_instructions,
    build_split_attempt_prompt,
    is_failure_sentinel_payload,
    split_payload_issues,
    split_payload_schema_example,
    validate_split_payload,
)
from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY


def _payload_with_count(count: int) -> dict[str, object]:
    return {
        "subtasks": [
            {
                "id": f"S{index}",
                "title": f"Subtask {index}",
                "objective": f"What step {index} achieves.",
                "why_now": f"Why step {index} belongs here.",
            }
            for index in range(1, count + 1)
        ]
    }


@pytest.mark.parametrize(
    ("mode", "expected_snippet"),
    [
        ("workflow", "Split a parent task into a small set of sequential workflow-based subtasks."),
        ("simplify_workflow", "Identify the smallest core workflow that still proves the task is real"),
        ("phase_breakdown", "Break a parent task into a small set of sequential implementation phases."),
        ("agent_breakdown", "Use agent judgment to choose the most natural decomposition shape for this task."),
    ],
)
def test_build_split_attempt_prompt_uses_canonical_mode_prompt_and_stable_context(
    mode: str,
    expected_snippet: str,
) -> None:
    prompt = build_split_attempt_prompt(
        mode,  # type: ignore[arg-type]
        {
            "root_prompt": "Ship reset flow",
            "current_node_prompt": "Add project reset flow: Reset to root safely",
            "parent_chain_prompts": ["Root goal: Ship reset flow", "Reset workflow"],
            "prior_node_summaries_compact": [
                {
                    "title": "Prepare reset request",
                    "description": "Gather the reset target and current state.",
                }
            ],
            "parent_chain_truncated": True,
        },
    )

    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]  # type: ignore[index]

    assert expected_snippet in prompt
    assert "Runtime context:" in prompt
    assert "- Parent task: Add project reset flow: Reset to root safely" in prompt
    assert "- Root goal: Ship reset flow" in prompt
    assert "- Parent chain:" in prompt
    assert "- Completed sibling context:" in prompt
    assert "Respect AGENTS.md and local repo guidance." in prompt
    assert "Parent chain note: lineage was truncated for prompt compactness." in prompt
    assert "First call emit_render_data(kind='split_result', payload=...)." in prompt
    assert f"should usually contain {spec['min_items']} to {spec['max_items']} items" in prompt
    assert '"id": "S1"' in prompt
    assert '"why_now": "Why this should happen now."' in prompt


def test_build_split_attempt_prompt_retry_feedback_keeps_same_prompt_family() -> None:
    retry_feedback = build_hidden_retry_feedback(
        "workflow",
        ["payload.subtasks[1].why_now is required"],
    )
    prompt = build_split_attempt_prompt(
        "workflow",
        {
            "root_prompt": "Ship reset flow",
            "current_node_prompt": "Add project reset flow: Reset to root safely",
            "parent_chain_prompts": [],
            "prior_node_summaries_compact": [],
        },
        retry_feedback,
    )

    assert prompt.startswith("Retry: your previous workflow split output was invalid.")
    assert "Validation issues:" in prompt
    assert "- payload.subtasks[1].why_now is required" in prompt
    assert "Split a parent task into a small set of sequential workflow-based subtasks." in prompt
    assert "Produce a corrected split using the same task, repository context, and output contract below." in prompt


def test_build_planning_base_instructions_is_generic_for_structured_split_output() -> None:
    instructions = build_planning_base_instructions()

    assert "emit_render_data(kind='split_result', payload=...)." in instructions
    assert "Do not duplicate the structured payload in the summary text." in instructions
    assert "do not invent a generic fallback split".lower() in instructions.lower()
    assert "Support only these canonical split modes" not in instructions


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_validate_split_payload_accepts_any_positive_count_when_shape_is_valid(mode: str) -> None:
    assert validate_split_payload(mode, _payload_with_count(1)) is True  # type: ignore[arg-type]
    assert validate_split_payload(mode, _payload_with_count(8)) is True  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_validate_split_payload_accepts_empty_failure_sentinel(mode: str) -> None:
    payload = {"subtasks": []}

    assert validate_split_payload(mode, payload) is True  # type: ignore[arg-type]
    assert is_failure_sentinel_payload(mode, payload) is True  # type: ignore[arg-type]


def test_split_payload_schema_example_is_shared_one_item_shape() -> None:
    assert split_payload_schema_example("workflow") == {
        "subtasks": [
            {
                "id": "S1",
                "title": "Subtask title",
                "objective": "What this step achieves.",
                "why_now": "Why this should happen now.",
            }
        ]
    }


def test_split_payload_issues_rejects_extra_keys_missing_fields_blank_text_and_nonsequential_ids() -> None:
    issues = split_payload_issues(
        "workflow",
        {
            "subtasks": [
                {
                    "id": "S2",
                    "title": "  ",
                    "objective": "Build setup.",
                    "why_now": "Needed first.",
                    "extra": "legacy",
                },
                {
                    "id": "S2",
                    "title": "Ship",
                    "objective": "",
                },
            ],
            "epics": [],
        },
    )

    assert "payload.epics is not allowed" in issues
    assert "payload.subtasks[0].extra is not allowed" in issues
    assert "payload.subtasks[0].title must be a non-empty string" in issues
    assert "payload.subtasks[0].id must be 'S1'" in issues
    assert "payload.subtasks[1].why_now is required" in issues
    assert "payload.subtasks[1].objective must be a non-empty string" in issues


def test_is_failure_sentinel_payload_requires_exact_valid_shape() -> None:
    assert is_failure_sentinel_payload("workflow", {"subtasks": []}) is True
    assert is_failure_sentinel_payload("workflow", {"subtasks": [], "extra": True}) is False
    assert is_failure_sentinel_payload("workflow", _payload_with_count(2)) is False
