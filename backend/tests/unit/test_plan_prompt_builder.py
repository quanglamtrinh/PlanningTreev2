from __future__ import annotations

from backend.ai.plan_prompt_builder import (
    build_plan_turn_prompt,
    parse_plan_turn_response,
    plan_turn_issues,
    plan_turn_output_schema,
)


def test_build_plan_turn_prompt_includes_high_impact_missing_info_guidance() -> None:
    prompt = build_plan_turn_prompt(
        {
            "project_root_goal": "Create a restaurant website",
            "task": {
                "title": "Create site shell",
                "purpose": "Deliver the first branded shell for the site",
                "responsibility": "",
            },
        },
        user_message="Please create the plan.",
    )

    assert "Use native requestUserInput only when high-impact execution information is missing." in prompt
    assert "ask 1 short question if possible" in prompt
    assert "prefer multiple-choice options before free-form input" in prompt
    assert "Planner answers are plan-scoped, not automatic Spec edits." in prompt
    assert "The final assistant message must contain only the structured branching JSON." in prompt
    assert "plan_markdown" in prompt
    assert "requires_spec_update" in prompt


def test_parse_plan_turn_response_accepts_plan_ready_branch() -> None:
    payload = parse_plan_turn_response(
        "```json\n"
        '{'
        '"kind":"plan_ready",'
        '"plan_markdown":"1. Inspect\\n2. Apply\\n3. Verify",'
        '"assistant_summary":"The plan is ready."'
        "}\n```"
    )

    assert payload is not None
    assert plan_turn_issues(payload) == []
    assert payload["kind"] == "plan_ready"
    assert payload["plan_markdown"] == "1. Inspect\n2. Apply\n3. Verify"
    assert payload["assistant_summary"] == "The plan is ready."


def test_parse_plan_turn_response_discards_null_branch_fields() -> None:
    payload = parse_plan_turn_response(
        '{'
        '"kind":"plan_ready",'
        '"plan_markdown":"1. Inspect\\n2. Apply\\n3. Verify",'
        '"assistant_summary":"The plan is ready.",'
        '"change_summary":null,'
        '"changed_contract_axes":null,'
        '"recommended_next_step":null'
        '}'
    )

    assert payload == {
        "kind": "plan_ready",
        "plan_markdown": "1. Inspect\n2. Apply\n3. Verify",
        "assistant_summary": "The plan is ready.",
    }
    assert plan_turn_issues(payload) == []


def test_plan_turn_output_schema_uses_structured_outputs_safe_subset() -> None:
    schema = plan_turn_output_schema()

    assert schema["type"] == "object"
    assert "oneOf" not in schema
    assert "allOf" not in schema
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "kind",
        "plan_markdown",
        "assistant_summary",
        "change_summary",
        "changed_contract_axes",
        "recommended_next_step",
    }
