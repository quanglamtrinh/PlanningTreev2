from __future__ import annotations

import pytest

from backend.ai.split_prompt_builder import (
    STRICTNESS_LEVELS,
    build_generation_prompt,
    build_hidden_retry_feedback,
    build_planning_base_instructions,
    parse_generation_response,
    split_payload_issues,
    split_payload_schema_example,
    validate_split_payload,
)
from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY


def _valid_payload_for_mode(mode: str) -> dict[str, object]:
    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]  # type: ignore[index]
    subtasks = []
    for index in range(1, spec["min_items"] + 1):
        subtasks.append(
            {
                "id": f"S{index}",
                "title": f"Subtask {index}",
                "objective": f"What step {index} achieves",
                "why_now": f"Why step {index} happens now",
            }
        )
    return {"subtasks": subtasks}


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
@pytest.mark.parametrize("strictness", STRICTNESS_LEVELS)
def test_build_generation_prompt_includes_context_count_and_shared_schema(mode: str, strictness: str) -> None:
    prompt = build_generation_prompt(
        mode,  # type: ignore[arg-type]
        {
            "root_prompt": "Ship phase 5",
            "current_node_prompt": "Split the node",
            "parent_chain_prompts": ["Root goal"],
        },
        strictness,
        "Validation issues:\n- bad shape" if strictness != "standard" else None,
    )

    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]  # type: ignore[index]

    assert f"Planning mode: {mode}." in prompt
    assert "Return exactly one JSON object." in prompt
    assert '"current_node_prompt": "Split the node"' in prompt
    assert f"{spec['min_items']} to {spec['max_items']}" in prompt
    assert '"id": "S1"' in prompt
    assert '"objective"' in prompt
    assert '"why_now"' in prompt
    assert '"id": "S2"' not in prompt


def test_build_planning_base_instructions_mentions_only_canonical_modes() -> None:
    instructions = build_planning_base_instructions()

    for mode in CANONICAL_SPLIT_MODE_REGISTRY:
        assert mode in instructions
    assert "walking_skeleton" not in instructions
    assert '"id": "S1"' in instructions
    assert '"why_now"' in instructions


@pytest.mark.parametrize(
    ("mode", "expected_intent"),
    [
        ("workflow", "workflow-first sequential split"),
        ("simplify_workflow", "minimum valid core workflow first, then additive reintroduction"),
        ("phase_breakdown", "phase-based sequential delivery split"),
        ("agent_breakdown", "conservative non-workflow split when the other shapes are a weak fit"),
    ],
)
def test_build_planning_base_instructions_includes_mode_specific_semantics(
    mode: str,
    expected_intent: str,
) -> None:
    instructions = build_planning_base_instructions(mode)  # type: ignore[arg-type]

    assert f"Planning mode: {mode}." in instructions
    assert expected_intent in instructions


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_validate_split_payload_accepts_valid_canonical_payload(mode: str) -> None:
    payload = _valid_payload_for_mode(mode)

    assert validate_split_payload(mode, payload) is True  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_split_payload_schema_example_is_shared_one_item_shape(mode: str) -> None:
    assert split_payload_schema_example(mode) == {
        "subtasks": [
            {
                "id": "S1",
                "title": "Subtask title",
                "objective": "What this step achieves",
                "why_now": "Why this should happen now",
            }
        ]
    }


@pytest.mark.parametrize(
    ("mode", "payload"),
    [
        ("workflow", {"subtasks": [{"id": "S1", "title": "A", "objective": "B", "why_now": "C"}]}),
        ("simplify_workflow", {"subtasks": [{"id": f"S{index}", "title": "A", "objective": "B", "why_now": "C"} for index in range(1, 7)]}),
        ("phase_breakdown", {"subtasks": [{"id": "S1", "title": "A", "objective": "B", "why_now": "C"}]}),
        ("agent_breakdown", {"subtasks": [{"id": "S1", "title": "A", "objective": "B", "why_now": "C"}]}),
    ],
)
def test_validate_split_payload_enforces_mode_specific_counts(mode: str, payload: dict[str, object]) -> None:
    assert validate_split_payload(mode, payload) is False  # type: ignore[arg-type]


def test_split_payload_issues_rejects_extra_top_level_and_item_keys() -> None:
    issues = split_payload_issues(
        "workflow",
        {
            "subtasks": [
                {
                    "id": "S1",
                    "title": "Setup",
                    "objective": "Build setup",
                    "why_now": "Needed first",
                    "prompt": "legacy key",
                }
            ],
            "epics": [],
        },
    )

    assert "payload.epics is not allowed" in issues
    assert "payload.subtasks[0].prompt is not allowed" in issues


def test_split_payload_issues_rejects_missing_blank_and_duplicate_fields() -> None:
    issues = split_payload_issues(
        "workflow",
        {
            "subtasks": [
                {
                    "id": "S1",
                    "title": "  ",
                    "objective": "Build setup",
                    "why_now": "Needed first",
                },
                {
                    "id": "S1",
                    "title": "Ship",
                    "objective": "",
                    "why_now": "Now",
                },
                {
                    "id": "S3",
                    "title": "Final",
                    "why_now": "Last",
                },
            ]
        },
    )

    assert "payload.subtasks[0].title must be a non-empty string" in issues
    assert "payload.subtasks[1].objective must be a non-empty string" in issues
    assert "payload.subtasks[1].id must be unique" in issues
    assert "payload.subtasks[2].objective is required" in issues


def test_parse_generation_response_normalizes_exact_canonical_payload() -> None:
    payload = parse_generation_response(
        "workflow",
        """
        {
          "subtasks": [
            {"id": " S1 ", "title": " Setup ", "objective": " Create workspace ", "why_now": " First step "},
            {"id": " S2 ", "title": " Build ", "objective": " Implement flow ", "why_now": " Depends on setup "},
            {"id": " S3 ", "title": " Verify ", "objective": " Confirm output ", "why_now": " Closes the loop "}
          ]
        }
        """,
    )

    assert payload == {
        "subtasks": [
            {"id": "S1", "title": "Setup", "objective": "Create workspace", "why_now": "First step"},
            {"id": "S2", "title": "Build", "objective": "Implement flow", "why_now": "Depends on setup"},
            {"id": "S3", "title": "Verify", "objective": "Confirm output", "why_now": "Closes the loop"},
        ]
    }


def test_parse_generation_response_rejects_legacy_slice_shape() -> None:
    assert (
        parse_generation_response(
            "workflow",
            """
            {
              "subtasks": [
                {"order": 1, "prompt": "First", "risk_reason": "", "what_unblocks": ""}
              ]
            }
            """,
        )
        is None
    )


def test_parse_generation_response_rejects_extra_keys_and_invalid_text() -> None:
    assert (
        parse_generation_response(
            "workflow",
            """
            {
              "subtasks": [
                {"id": "S1", "title": "A", "objective": "B", "why_now": "C", "extra": "nope"},
                {"id": "S2", "title": "A", "objective": "B", "why_now": "C"},
                {"id": "S3", "title": "A", "objective": "B", "why_now": "C"}
              ]
            }
            """,
        )
        is None
    )
    assert parse_generation_response("workflow", "not json") is None


def test_build_hidden_retry_feedback_includes_schema_issues_and_mode_count() -> None:
    feedback = build_hidden_retry_feedback(
        "workflow",
        ["payload.subtasks must contain 3 to 7 items"],
    )

    assert "Validation issues:" in feedback
    assert "- payload.subtasks must contain 3 to 7 items" in feedback
    assert "Generate 3 to 7 ordered subtasks." in feedback
    assert '"id": "S1"' in feedback
