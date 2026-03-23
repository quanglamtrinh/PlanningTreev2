from __future__ import annotations

from backend.ai.frame_prompt_builder import (
    build_frame_base_instructions,
    build_frame_generation_prompt,
    extract_frame_content,
    frame_render_tool,
)


def test_frame_render_tool_shape() -> None:
    tool = frame_render_tool()
    assert tool["name"] == "emit_frame_content"
    assert "content" in tool["inputSchema"]["properties"]
    assert tool["inputSchema"]["required"] == ["content"]


def test_base_instructions_mentions_frame() -> None:
    instructions = build_frame_base_instructions()
    assert "frame" in instructions.lower()
    assert "emit_frame_content" in instructions


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
    assert "emit_frame_content" in prompt


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
