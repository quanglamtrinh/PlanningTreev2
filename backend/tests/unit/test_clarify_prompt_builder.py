from __future__ import annotations

import json

from backend.ai.clarify_prompt_builder import (
    _normalize_options,
    _to_snake_case,
    build_clarify_generation_prompt,
    build_clarify_generation_role_prefix,
    build_clarify_output_schema,
    extract_clarify_questions,
    extract_clarify_questions_from_structured_output,
    extract_clarify_questions_from_text,
)


# ── Role prefix ──────────────────────────────────────────────────


def test_role_prefix_contains_clarify_context() -> None:
    prefix = build_clarify_generation_role_prefix()
    assert "clarif" in prefix.lower()
    assert "options" in prefix.lower()
    assert "recommended" in prefix.lower()
    assert "snake_case" in prefix


def test_role_prefix_has_no_emit_references() -> None:
    prefix = build_clarify_generation_role_prefix()
    assert "emit_" not in prefix


def test_role_prefix_empty_list_instruction() -> None:
    """Rule 5 should reference JSON output, not tool call."""
    prefix = build_clarify_generation_role_prefix()
    assert '{"questions": []}' in prefix


# ── Output schema ────────────────────────────────────────────────


def test_output_schema_shape() -> None:
    schema = build_clarify_output_schema()
    assert schema["type"] == "object"
    assert "questions" in schema["properties"]
    assert schema["required"] == ["questions"]
    items = schema["properties"]["questions"]["items"]
    assert "field_name" in items["properties"]
    assert "question" in items["properties"]
    assert "options" in items["properties"]
    option_items = items["properties"]["options"]["items"]
    assert "id" in option_items["properties"]
    assert "label" in option_items["properties"]
    assert "value" in option_items["properties"]
    assert "rationale" in option_items["properties"]
    assert "recommended" in option_items["properties"]


# ── Generation prompt ────────────────────────────────────────────


def test_build_prompt_includes_frame_content() -> None:
    frame = "# Task Title\nBuild a login page\n\n# Task-Shaping Fields\n- auth_provider:"
    context = {
        "current_node_prompt": "Build a login page",
        "root_prompt": "Create a web app",
    }
    prompt = build_clarify_generation_prompt(frame_content=frame, task_context=context)
    assert "Build a login page" in prompt
    assert "auth_provider" in prompt
    assert "Create a web app" in prompt


def test_build_prompt_includes_task_context() -> None:
    context = {
        "current_node_prompt": "Build a login page",
        "root_prompt": "Create a web app",
        "parent_chain_prompts": ["Phase 1: Auth"],
    }
    prompt = build_clarify_generation_prompt(frame_content="# Frame", task_context=context)
    assert "Build a login page" in prompt
    assert "Phase 1: Auth" in prompt


def test_build_prompt_empty_frame() -> None:
    prompt = build_clarify_generation_prompt(
        frame_content="",
        task_context={"current_node_prompt": "Test"},
    )
    assert "(empty)" in prompt
    assert "structured JSON output" in prompt


def test_build_prompt_truncates_long_frame() -> None:
    long_frame = "x" * 10000
    prompt = build_clarify_generation_prompt(
        frame_content=long_frame,
        task_context={"current_node_prompt": "Test"},
    )
    assert "..." in prompt
    assert len(prompt) < 10000


def test_build_prompt_with_role_prefix() -> None:
    prefix = "You are a clarify assistant."
    prompt = build_clarify_generation_prompt(
        frame_content="# Frame",
        task_context={"current_node_prompt": "Test"},
        role_prefix=prefix,
    )
    assert prompt.startswith(prefix)


# ── Extract from tool_calls (tier 2 fallback) ───────────────────


def test_extract_clarify_questions_from_tool_calls() -> None:
    tool_calls = [
        {
            "tool_name": "emit_clarify_questions",
            "arguments": {
                "questions": [
                    {
                        "field_name": "auth_provider",
                        "question": "Which auth provider should we use?",
                        "why_it_matters": "Affects security model",
                        "current_value": "",
                        "options": [
                            {"id": "oauth2", "label": "OAuth2", "value": "OAuth2", "rationale": "Standard", "recommended": True},
                            {"id": "api_key", "label": "API Key", "value": "API Key", "rationale": "Simple", "recommended": False},
                        ],
                    },
                ]
            },
        }
    ]
    result = extract_clarify_questions(tool_calls)
    assert result is not None
    assert len(result) == 1
    assert result[0]["field_name"] == "auth_provider"
    assert result[0]["question"] == "Which auth provider should we use?"
    assert result[0]["selected_option_id"] is None
    assert result[0]["custom_answer"] == ""
    assert result[0]["allow_custom"] is True
    assert result[0]["why_it_matters"] == "Affects security model"
    assert len(result[0]["options"]) == 2


def test_extract_clarify_questions_ignores_other_tools() -> None:
    tool_calls = [
        {"tool_name": "other_tool", "arguments": {"questions": [{"field_name": "x", "question": "y"}]}},
    ]
    result = extract_clarify_questions(tool_calls)
    assert result is None


def test_extract_clarify_questions_returns_none_for_empty() -> None:
    assert extract_clarify_questions([]) is None
    assert extract_clarify_questions(None) is None
    assert extract_clarify_questions("not a list") is None


def test_extract_clarify_questions_deduplicates() -> None:
    tool_calls = [
        {
            "tool_name": "emit_clarify_questions",
            "arguments": {
                "questions": [
                    {"field_name": "auth", "question": "First?", "options": []},
                    {"field_name": "auth", "question": "Duplicate?", "options": []},
                    {"field_name": "storage", "question": "Which storage?", "options": []},
                ]
            },
        }
    ]
    result = extract_clarify_questions(tool_calls)
    assert result is not None
    assert len(result) == 2
    assert result[0]["field_name"] == "auth"
    assert result[1]["field_name"] == "storage"


def test_extract_clarify_questions_skips_invalid_items() -> None:
    tool_calls = [
        {
            "tool_name": "emit_clarify_questions",
            "arguments": {
                "questions": [
                    {"field_name": "", "question": "No field name"},
                    {"field_name": "valid", "question": ""},
                    "not a dict",
                    {"field_name": "good", "question": "A real question?"},
                ]
            },
        }
    ]
    result = extract_clarify_questions(tool_calls)
    assert result is not None
    assert len(result) == 1
    assert result[0]["field_name"] == "good"


def test_extract_clarify_questions_empty_list_from_tool_call() -> None:
    """Zero questions from tool call returns empty list, not None."""
    tool_calls = [
        {
            "tool_name": "emit_clarify_questions",
            "arguments": {"questions": []},
        }
    ]
    result = extract_clarify_questions(tool_calls)
    assert result is not None
    assert result == []


# ── Extract from structured output (tier 1) ─────────────────────


def test_extract_structured_output_valid() -> None:
    stdout = json.dumps({
        "questions": [
            {"field_name": "auth", "question": "Which auth?", "options": []},
        ]
    })
    result = extract_clarify_questions_from_structured_output(stdout)
    assert result is not None
    assert len(result) == 1
    assert result[0]["field_name"] == "auth"


def test_extract_structured_output_empty_questions() -> None:
    """Empty questions list is valid success (all fields resolved)."""
    stdout = json.dumps({"questions": []})
    result = extract_clarify_questions_from_structured_output(stdout)
    assert result is not None
    assert result == []


def test_extract_structured_output_with_fence() -> None:
    inner = json.dumps({"questions": [{"field_name": "x", "question": "y", "options": []}]})
    stdout = f"```json\n{inner}\n```"
    result = extract_clarify_questions_from_structured_output(stdout)
    assert result is not None
    assert len(result) == 1


def test_extract_structured_output_invalid_json() -> None:
    assert extract_clarify_questions_from_structured_output("not json") is None


def test_extract_structured_output_empty() -> None:
    assert extract_clarify_questions_from_structured_output("") is None


def test_extract_structured_output_missing_questions_key() -> None:
    assert extract_clarify_questions_from_structured_output(json.dumps({"other": "val"})) is None


# ── Extract from text (tier 3 fallback) ──────────────────────────


def test_extract_clarify_questions_from_text_empty_json_array() -> None:
    """Zero questions from stdout JSON returns empty list, not None."""
    result = extract_clarify_questions_from_text("[]")
    assert result is not None
    assert result == []


def test_extract_clarify_questions_from_text_json_array() -> None:
    stdout = '[{"field_name": "auth", "question": "Which auth?"}]'
    result = extract_clarify_questions_from_text(stdout)
    assert result is not None
    assert len(result) == 1
    assert result[0]["field_name"] == "auth"
    assert result[0]["selected_option_id"] is None
    assert result[0]["custom_answer"] == ""


def test_extract_clarify_questions_from_text_empty() -> None:
    assert extract_clarify_questions_from_text("") is None
    assert extract_clarify_questions_from_text("no json here") is None


# ── Stable option ID tests ──────────────────────────────────────────


def test_to_snake_case() -> None:
    assert _to_snake_case("Mobile Web") == "mobile_web"
    assert _to_snake_case("OAuth2") == "oauth2"
    assert _to_snake_case("API Key") == "api_key"
    assert _to_snake_case("  cloud storage  ") == "cloud_storage"
    assert _to_snake_case("camelCase") == "camel_case"
    assert _to_snake_case("already_snake") == "already_snake"


def test_normalize_options_derives_id_from_value() -> None:
    """Option id is always snake_case(value), regardless of AI-provided id."""
    raw = [
        {"id": "WRONG_ID", "label": "Web", "value": "Mobile Web", "rationale": "r", "recommended": True},
        {"id": "also_wrong", "label": "Cloud", "value": "Cloud Storage", "rationale": "r", "recommended": False},
    ]
    result = _normalize_options(raw)
    assert len(result) == 2
    assert result[0]["id"] == "mobile_web"
    assert result[1]["id"] == "cloud_storage"


def test_normalize_options_deduplicates_by_id() -> None:
    raw = [
        {"id": "x", "label": "A", "value": "Same Value", "rationale": "r", "recommended": True},
        {"id": "y", "label": "B", "value": "Same Value", "rationale": "r2", "recommended": False},
    ]
    result = _normalize_options(raw)
    assert len(result) == 1


def test_normalize_options_ensures_one_recommended() -> None:
    """If no option is recommended, the first one becomes recommended."""
    raw = [
        {"id": "x", "label": "A", "value": "val a", "rationale": "r", "recommended": False},
        {"id": "y", "label": "B", "value": "val b", "rationale": "r", "recommended": False},
    ]
    result = _normalize_options(raw)
    assert sum(1 for o in result if o["recommended"]) == 1
    assert result[0]["recommended"] is True


def test_normalize_options_caps_recommended_at_one() -> None:
    """If multiple options are recommended, only the first stays recommended."""
    raw = [
        {"id": "x", "label": "A", "value": "val a", "rationale": "r", "recommended": True},
        {"id": "y", "label": "B", "value": "val b", "rationale": "r", "recommended": True},
    ]
    result = _normalize_options(raw)
    assert sum(1 for o in result if o["recommended"]) == 1
