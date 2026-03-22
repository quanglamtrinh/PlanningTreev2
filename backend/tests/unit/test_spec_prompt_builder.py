from __future__ import annotations

from backend.ai.spec_prompt_builder import (
    build_spec_base_instructions,
    build_spec_generation_prompt,
    extract_spec_content,
    extract_spec_content_from_text,
    spec_render_tool,
)


def test_spec_render_tool_shape() -> None:
    tool = spec_render_tool()
    assert tool["name"] == "emit_spec_content"
    assert "content" in tool["inputSchema"]["properties"]
    assert tool["inputSchema"]["required"] == ["content"]


def test_base_instructions_mentions_spec_generation() -> None:
    instructions = build_spec_base_instructions()
    assert "technical implementation spec" in instructions.lower()
    assert "emit_spec_content" in instructions


def test_build_prompt_includes_confirmed_frame_content() -> None:
    prompt = build_spec_generation_prompt(
        frame_content="# Task Title\nBuild login page\n\n# Task-Shaping Fields\n- target platform: web",
        task_context={
            "current_node_prompt": "Build a login page",
            "root_prompt": "Create a web app",
            "parent_chain_prompts": ["Phase 1: Auth"],
        },
    )
    assert "Build login page" in prompt
    assert "target platform: web" in prompt
    assert "Create a web app" in prompt
    assert "Phase 1: Auth" in prompt


def test_extract_spec_content_from_tool_calls() -> None:
    tool_calls = [
        {
            "tool_name": "emit_spec_content",
            "arguments": {"content": "# Overview\nUse OAuth2."},
        }
    ]
    assert extract_spec_content(tool_calls) == "# Overview\nUse OAuth2."


def test_extract_spec_content_from_text_markdown() -> None:
    stdout = "# Overview\nUse OAuth2.\n\n## Testing Strategy\nAdd unit tests."
    assert extract_spec_content_from_text(stdout) == stdout


def test_extract_spec_content_from_text_json_fallback() -> None:
    stdout = '{"content": "# Overview\\nUse OAuth2."}'
    assert extract_spec_content_from_text(stdout) == "# Overview\nUse OAuth2."
