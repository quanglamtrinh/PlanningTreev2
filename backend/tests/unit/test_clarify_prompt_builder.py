from __future__ import annotations

from backend.ai.clarify_prompt_builder import (
    build_clarify_base_instructions,
    build_clarify_generation_prompt,
    clarify_render_tool,
    extract_clarify_questions,
    extract_clarify_questions_from_text,
)


def test_clarify_render_tool_shape() -> None:
    tool = clarify_render_tool()
    assert tool["name"] == "emit_clarify_questions"
    assert "questions" in tool["inputSchema"]["properties"]
    assert tool["inputSchema"]["required"] == ["questions"]
    items = tool["inputSchema"]["properties"]["questions"]["items"]
    assert "field_name" in items["properties"]
    assert "question" in items["properties"]


def test_base_instructions_mentions_clarify() -> None:
    instructions = build_clarify_base_instructions()
    assert "clarif" in instructions.lower()
    assert "emit_clarify_questions" in instructions


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
    assert "emit_clarify_questions" in prompt


def test_build_prompt_truncates_long_frame() -> None:
    long_frame = "x" * 10000
    prompt = build_clarify_generation_prompt(
        frame_content=long_frame,
        task_context={"current_node_prompt": "Test"},
    )
    assert "..." in prompt
    assert len(prompt) < 10000


def test_extract_clarify_questions_from_tool_calls() -> None:
    tool_calls = [
        {
            "tool_name": "emit_clarify_questions",
            "arguments": {
                "questions": [
                    {"field_name": "auth_provider", "question": "Which auth provider should we use?"},
                    {"field_name": "storage_backend", "question": "What storage backend?"},
                ]
            },
        }
    ]
    result = extract_clarify_questions(tool_calls)
    assert result is not None
    assert len(result) == 2
    assert result[0]["field_name"] == "auth_provider"
    assert result[0]["question"] == "Which auth provider should we use?"
    assert result[0]["answer"] == ""
    assert result[0]["resolution_status"] == "open"


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
                    {"field_name": "auth", "question": "First?"},
                    {"field_name": "auth", "question": "Duplicate?"},
                    {"field_name": "storage", "question": "Which storage?"},
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


def test_extract_clarify_questions_from_text_json_array() -> None:
    stdout = '[{"field_name": "auth", "question": "Which auth?"}]'
    result = extract_clarify_questions_from_text(stdout)
    assert result is not None
    assert len(result) == 1
    assert result[0]["field_name"] == "auth"


def test_extract_clarify_questions_from_text_empty() -> None:
    assert extract_clarify_questions_from_text("") is None
    assert extract_clarify_questions_from_text("no json here") is None
