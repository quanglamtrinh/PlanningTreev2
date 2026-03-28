from __future__ import annotations

from backend.ai.frame_prompt_builder import (
    build_frame_generation_prompt,
    build_frame_generation_role_prefix,
    build_frame_output_schema,
    extract_frame_content,
    extract_frame_content_from_structured_output,
)


# Role prefix


def test_role_prefix_contains_frame_context() -> None:
    prefix = build_frame_generation_role_prefix()
    assert "task-framing assistant" in prefix.lower()
    assert "frame" in prefix.lower()


def test_role_prefix_has_no_emit_references() -> None:
    prefix = build_frame_generation_role_prefix()
    assert "emit_" not in prefix


def test_role_prefix_supports_inherit_and_specialize_shaping_fields() -> None:
    prefix = build_frame_generation_role_prefix()
    assert "inherit" in prefix.lower()
    assert "specialize" in prefix.lower()
    assert "task-shaping fields" in prefix.lower()


def test_role_prefix_preserves_relevant_unresolved_shaping_fields() -> None:
    prefix = build_frame_generation_role_prefix()
    assert "minimal sufficient set" in prefix.lower()
    assert "clearly grounded" in prefix.lower()
    assert "still not determined" in prefix.lower()
    assert "left blank" in prefix.lower()


def test_role_prefix_declares_initial_frame_philosophy() -> None:
    prefix = build_frame_generation_role_prefix()
    lowered = prefix.lower()
    assert "initial frame philosophy" in lowered
    assert "not the final implementation-ready frame" in lowered
    assert "do not treat the initial frame as a mini-spec" in lowered
    assert "when in doubt, preserve ambiguity" in lowered


def test_role_prefix_locks_first_four_sections_to_branch_compatible_language() -> None:
    prefix = build_frame_generation_role_prefix()
    lowered = prefix.lower()
    assert "invariant, branch-compatible language" in lowered
    assert "do not let user story, functional requirements, success criteria, or out of scope" in lowered
    assert (
        "if a sentence is only true for one plausible but unconfirmed branch, it does not"
        in lowered
    )


def test_role_prefix_no_longer_pushes_infer_first_policy() -> None:
    prefix = build_frame_generation_role_prefix()
    lowered = prefix.lower()
    assert "reasonably implied" not in lowered
    assert "do not ask clarification questions directly" not in lowered
    assert "produce the best frame from available information" not in lowered


# Output schema


def test_output_schema_shape() -> None:
    schema = build_frame_output_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "content" in schema["properties"]
    assert schema["required"] == ["content"]


# Generation prompt


def test_build_prompt_includes_task_context() -> None:
    context = {
        "current_node_prompt": "Build a login page",
        "root_prompt": "Create a web app",
        "parent_chain_prompts": ["Phase 1: Auth"],
        "prior_node_summaries_compact": [],
    }
    prompt = build_frame_generation_prompt(
        chat_messages=[],
        task_context=context,
    )
    assert "Build a login page" in prompt
    assert "Create a web app" in prompt
    assert "Phase 1: Auth" in prompt


def test_build_prompt_includes_chat_history() -> None:
    messages = [
        {"role": "user", "content": "I want a login page with OAuth"},
        {"role": "assistant", "content": "Sure, I can help with that."},
    ]
    prompt = build_frame_generation_prompt(
        chat_messages=messages,
        task_context={"current_node_prompt": "Login"},
    )
    assert "login page with OAuth" in prompt
    assert "[user]:" in prompt
    assert "[assistant]:" in prompt


def test_build_prompt_truncates_long_chat() -> None:
    messages = [{"role": "user", "content": "x" * 10000}]
    prompt = build_frame_generation_prompt(
        chat_messages=messages,
        task_context={"current_node_prompt": "Test"},
    )
    assert "truncated" in prompt.lower()


def test_build_prompt_empty_chat() -> None:
    prompt = build_frame_generation_prompt(
        chat_messages=[],
        task_context={"current_node_prompt": "Test"},
    )
    assert "Conversation history" not in prompt
    assert "structured JSON output" in prompt


def test_build_prompt_with_role_prefix() -> None:
    prefix = "You are a frame assistant."
    prompt = build_frame_generation_prompt(
        chat_messages=[],
        task_context={"current_node_prompt": "Test"},
        role_prefix=prefix,
    )
    assert prompt.startswith(prefix)


def test_build_prompt_includes_current_task_only_policy_when_using_default_prefix() -> None:
    prompt = build_frame_generation_prompt(
        chat_messages=[],
        task_context={"current_node_prompt": "Test"},
        role_prefix=build_frame_generation_role_prefix(),
    )
    assert "current task only" in prompt.lower()
    assert "structured json output" in prompt.lower()


def test_build_prompt_uses_ambiguity_preserving_template_hints() -> None:
    prompt = build_frame_generation_prompt(
        chat_messages=[],
        task_context={"current_node_prompt": "Test"},
        role_prefix=build_frame_generation_role_prefix(),
    )
    lowered = prompt.lower()
    assert "use capability language, not unconfirmed local interaction patterns" in lowered
    assert "without assuming unresolved local solution choices" in lowered
    assert "observable outcomes that remain valid across unresolved" in lowered
    assert "shaping decisions" in lowered


def test_build_prompt_without_role_prefix() -> None:
    prompt = build_frame_generation_prompt(
        chat_messages=[],
        task_context={"current_node_prompt": "Test"},
    )
    assert prompt.startswith("Task context:")


# Extract from tool_calls (tier 2 fallback)


def test_extract_frame_content_from_tool_calls() -> None:
    tool_calls = [
        {
            "tool_name": "emit_frame_content",
            "arguments": {"content": "# Task Title\nBuild login page"},
        }
    ]
    result = extract_frame_content(tool_calls)
    assert result == "# Task Title\nBuild login page"


def test_extract_frame_content_ignores_other_tools() -> None:
    tool_calls = [
        {"tool_name": "other_tool", "arguments": {"content": "ignored"}},
    ]
    result = extract_frame_content(tool_calls)
    assert result is None


def test_extract_frame_content_returns_none_for_empty() -> None:
    assert extract_frame_content([]) is None
    assert extract_frame_content(None) is None
    assert extract_frame_content("not a list") is None


def test_extract_frame_content_skips_empty_content() -> None:
    tool_calls = [
        {"tool_name": "emit_frame_content", "arguments": {"content": "  "}},
    ]
    result = extract_frame_content(tool_calls)
    assert result is None


# Extract from structured output (tier 1)


def test_extract_structured_output_valid_json() -> None:
    import json

    stdout = json.dumps({"content": "# Frame\nHello"})
    result = extract_frame_content_from_structured_output(stdout)
    assert result == "# Frame\nHello"


def test_extract_structured_output_with_fence() -> None:
    stdout = '```json\n{"content": "# Frame\\nHello"}\n```'
    result = extract_frame_content_from_structured_output(stdout)
    assert result == "# Frame\nHello"


def test_extract_structured_output_invalid_json() -> None:
    assert extract_frame_content_from_structured_output("not json") is None


def test_extract_structured_output_empty() -> None:
    assert extract_frame_content_from_structured_output("") is None
    assert extract_frame_content_from_structured_output("  ") is None


def test_extract_structured_output_missing_content_key() -> None:
    import json

    assert extract_frame_content_from_structured_output(json.dumps({"other": "val"})) is None


def test_extract_structured_output_empty_content() -> None:
    import json

    assert extract_frame_content_from_structured_output(json.dumps({"content": "  "})) is None
