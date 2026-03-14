from __future__ import annotations

from backend.ai.spec_prompt_builder import (
    build_spec_generation_prompt,
    build_spec_retry_feedback,
    normalize_spec_generation_payload,
    parse_spec_generation_response,
    spec_generation_issues,
    spec_generation_schema_example,
    validate_spec_generation_payload,
)


def test_build_spec_generation_prompt_includes_context_and_required_shape() -> None:
    prompt = build_spec_generation_prompt(
        {
            "project_root_goal": "Ship phase 5",
            "task": {"title": "Implement API", "purpose": "Serve spec drafts", "responsibility": ""},
            "brief": {"runtime_state": {"status": "ready"}},
        }
    )

    assert "Return exactly one JSON object." in prompt
    assert "mission, scope, constraints, autonomy, verification, execution_controls, assumptions" in prompt
    assert "Do not run tools. Do not inspect files." in prompt
    assert '"project_root_goal": "Ship phase 5"' in prompt


def test_parse_spec_generation_response_extracts_wrapped_json() -> None:
    payload = parse_spec_generation_response(
        "Here you go:\n```json\n"
        '{"mission":{"goal":"A","success_outcome":"B","implementation_level":"working"},'
        '"scope":{"must_do":["C"],"must_not_do":[],"deferred_work":[]},'
        '"constraints":{"hard_constraints":[],"change_budget":"small","touch_boundaries":[],"external_dependencies":[]},'
        '"autonomy":{"allowed_decisions":[],"requires_confirmation":[],"default_policy_when_unclear":"ask_user"},'
        '"verification":{"acceptance_checks":["D"],"definition_of_done":"done","evidence_expected":[]},'
        '"execution_controls":{"quality_profile":"standard","tooling_limits":[],"output_expectation":"concise","conflict_policy":"reopen_spec","missing_decision_policy":"reopen_spec"},'
        '"assumptions":{"assumptions_in_force":["E"]}}'
        "\n```"
    )

    assert payload is not None
    assert payload["mission"]["goal"] == "A"
    assert payload["scope"]["must_do"] == ["C"]
    assert validate_spec_generation_payload(payload) is True


def test_spec_generation_issues_describe_missing_and_invalid_fields() -> None:
    issues = spec_generation_issues(
        {
            "mission": {"goal": "ok", "success_outcome": 3},
            "scope": {"must_do": "bad"},
        }
    )

    assert "mission.success_outcome must be a string." in issues
    assert "scope.must_do must be a list of strings." in issues
    assert "constraints is required." in issues


def test_build_spec_retry_feedback_includes_issues_and_schema() -> None:
    feedback = build_spec_retry_feedback(["mission.goal must be a string."])

    assert "Validation issues:" in feedback
    assert "- mission.goal must be a string." in feedback
    assert '"mission"' in feedback


def test_normalize_spec_generation_payload_normalizes_nested_scalars_and_lists() -> None:
    normalized = normalize_spec_generation_payload(
        {
            "mission": {
                "goal": "  Ship feature  ",
                "success_outcome": "  Delivered  ",
                "implementation_level": " working ",
            },
            "scope": {
                "must_do": ["  Implement API  ", " "],
                "must_not_do": [],
                "deferred_work": [" Later "],
            },
            "constraints": {
                "hard_constraints": ["  Keep schema stable "],
                "change_budget": "  small  ",
                "touch_boundaries": [" backend/services "],
                "external_dependencies": [],
            },
            "autonomy": {
                "allowed_decisions": [" Local choice "],
                "requires_confirmation": [],
                "default_policy_when_unclear": " ask_user ",
            },
            "verification": {
                "acceptance_checks": ["  Test passes "],
                "definition_of_done": " shipped ",
                "evidence_expected": [" screenshot "],
            },
            "execution_controls": {
                "quality_profile": " standard ",
                "tooling_limits": [" workspace only "],
                "output_expectation": " concise ",
                "conflict_policy": " reopen_spec ",
                "missing_decision_policy": " reopen_spec ",
            },
            "assumptions": {
                "assumptions_in_force": [" seeded data ok "],
            },
        }
    )

    assert normalized["mission"]["goal"] == "Ship feature"
    assert normalized["scope"]["must_do"] == ["Implement API"]
    assert normalized["execution_controls"]["tooling_limits"] == ["workspace only"]
    assert spec_generation_schema_example()["assumptions"]["assumptions_in_force"][0].startswith("Assumption")
