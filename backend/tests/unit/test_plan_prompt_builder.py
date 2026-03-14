from __future__ import annotations

from backend.ai.plan_prompt_builder import (
    build_plan_turn_prompt,
    parse_plan_turn_response,
    plan_turn_issues,
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
    assert "requires_spec_update" in prompt


def test_parse_plan_turn_response_accepts_plan_ready_branch() -> None:
    payload = parse_plan_turn_response(
        "```json\n"
        '{'
        '"kind":"plan_ready",'
        '"assistant_summary":"The plan is ready."'
        "}\n```"
    )

    assert payload is not None
    assert plan_turn_issues(payload) == []
    assert payload["kind"] == "plan_ready"
    assert payload["assistant_summary"] == "The plan is ready."
