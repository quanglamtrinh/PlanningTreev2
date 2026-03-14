from __future__ import annotations

import pytest

from backend.ai.split_prompt_builder import (
    STRICTNESS_LEVELS,
    build_hidden_retry_feedback,
    build_generation_prompt,
    parse_generation_response,
    split_payload_issues,
    split_payload_schema_example,
    validate_split_payload,
)


@pytest.mark.parametrize("mode", ["walking_skeleton", "slice"])
@pytest.mark.parametrize("strictness", STRICTNESS_LEVELS)
def test_build_generation_prompt_includes_context_and_schema(mode: str, strictness: str) -> None:
    prompt = build_generation_prompt(
        mode,
        {
            "root_prompt": "Ship phase 5",
            "current_node_prompt": "Split the node",
            "parent_chain_prompts": ["Root goal"],
        },
        strictness,
        {"failed_criteria": ["parse"], "reasons": ["bad shape"]} if strictness != "standard" else None,
    )

    assert f"Planning mode: {mode}." in prompt
    assert "Return exactly one JSON object." in prompt
    assert '"current_node_prompt": "Split the node"' in prompt


def test_parse_walking_skeleton_response_normalizes_phase_dicts() -> None:
    payload = parse_generation_response(
        "walking_skeleton",
        """```json
        {
          "epics": [
            {
              "title": " Core ",
              "prompt": " Build backend ",
              "phases": {
                "B": {"prompt": " Hook integration ", "definition_of_done": " Connected "},
                "A": {"prompt": " Scaffold api ", "definition_of_done": " Ready "}
              }
            }
          ]
        }
        ```""",
    )

    assert payload == {
        "epics": [
            {
                "title": "Core",
                "prompt": "Build backend",
                "phases": [
                    {
                        "phase_key": "A",
                        "prompt": "Scaffold api",
                        "definition_of_done": "Ready",
                    },
                    {
                        "phase_key": "B",
                        "prompt": "Hook integration",
                        "definition_of_done": "Connected",
                    },
                ],
            }
        ]
    }
    assert validate_split_payload("walking_skeleton", payload) is True


def test_parse_slice_response_reorders_valid_orders() -> None:
    payload = parse_generation_response(
        "slice",
        """
        {
          "subtasks": [
            {"order": 2, "prompt": "Second", "risk_reason": "r2", "what_unblocks": "u2"},
            {"order": 1, "prompt": "First", "risk_reason": "r1", "what_unblocks": "u1"}
          ]
        }
        """,
    )

    assert payload == {
        "subtasks": [
            {"order": 1, "prompt": "First", "risk_reason": "r1", "what_unblocks": "u1"},
            {"order": 2, "prompt": "Second", "risk_reason": "r2", "what_unblocks": "u2"},
        ]
    }
    assert validate_split_payload("slice", payload) is True


def test_parse_generation_response_returns_none_for_invalid_text() -> None:
    assert parse_generation_response("slice", "not json") is None


def test_validate_split_payload_enforces_counts() -> None:
    assert (
        validate_split_payload(
            "walking_skeleton",
            {
                "epics": [
                    {
                        "title": "Epic",
                        "prompt": "Build it",
                        "phases": [{"phase_key": "A", "prompt": "Only one", "definition_of_done": ""}],
                    }
                ]
            },
        )
        is False
    )
    assert (
        validate_split_payload(
            "slice",
            {"subtasks": [{"order": 1, "prompt": "Only one", "risk_reason": "", "what_unblocks": ""}]},
        )
        is False
    )


def test_split_payload_issues_describes_missing_fields() -> None:
    issues = split_payload_issues(
        "walking_skeleton",
        {
            "epics": [
                {
                    "title": "",
                    "prompt": "Build it",
                    "phases": [{"prompt": ""}, {"prompt": "Phase two"}],
                }
            ]
        },
    )

    assert "payload.epics[0].title is required" in issues
    assert "payload.epics[0].phases[0].prompt is required" in issues


def test_build_hidden_retry_feedback_includes_schema_and_issues() -> None:
    feedback = build_hidden_retry_feedback(
        "slice",
        ["payload.subtasks must contain 2 to 10 items"],
    )

    assert "Validation issues:" in feedback
    assert "- payload.subtasks must contain 2 to 10 items" in feedback
    assert '"subtasks"' in feedback
    assert split_payload_schema_example("slice")["subtasks"][0]["prompt"] == "Subtask prompt"
