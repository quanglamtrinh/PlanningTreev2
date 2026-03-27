from __future__ import annotations

import json

from backend.ai.spec_prompt_builder import (
    build_spec_generation_prompt,
    build_spec_generation_role_prefix,
    build_spec_output_schema,
    extract_spec_content,
    extract_spec_content_from_structured_output,
    extract_spec_content_from_text,
)


# ── Role prefix ──────────────────────────────────────────────────


def test_role_prefix_contains_spec_context() -> None:
    prefix = build_spec_generation_role_prefix()
    assert "technical implementation spec" in prefix.lower()
    assert "do not inspect the workspace" in prefix.lower()


def test_role_prefix_has_no_emit_references() -> None:
    prefix = build_spec_generation_role_prefix()
    assert "emit_" not in prefix


# ── Output schema ────────────────────────────────────────────────


def test_output_schema_shape() -> None:
    schema = build_spec_output_schema()
    assert schema["type"] == "object"
    assert "content" in schema["properties"]
    assert schema["required"] == ["content"]


# ── Generation prompt ────────────────────────────────────────────


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


def test_build_prompt_closing_instruction() -> None:
    prompt = build_spec_generation_prompt(
        frame_content="# Frame",
        task_context={"current_node_prompt": "Test"},
    )
    assert "structured JSON output" in prompt


def test_build_prompt_with_role_prefix() -> None:
    prefix = "You are a spec writer."
    prompt = build_spec_generation_prompt(
        frame_content="# Frame",
        task_context={"current_node_prompt": "Test"},
        role_prefix=prefix,
    )
    assert prompt.startswith(prefix)


# ── Extract from tool_calls (tier 2 fallback) ───────────────────


def test_extract_spec_content_from_tool_calls() -> None:
    tool_calls = [
        {
            "tool_name": "emit_spec_content",
            "arguments": {"content": "# Overview\nUse OAuth2."},
        }
    ]
    assert extract_spec_content(tool_calls) == "# Overview\nUse OAuth2."


# ── Extract from structured output (tier 1) ─────────────────────


def test_extract_structured_output_valid() -> None:
    stdout = json.dumps({"content": "# Overview\nUse OAuth2."})
    assert extract_spec_content_from_structured_output(stdout) == "# Overview\nUse OAuth2."


def test_extract_structured_output_with_fence() -> None:
    stdout = '```json\n{"content": "# Spec"}\n```'
    assert extract_spec_content_from_structured_output(stdout) == "# Spec"


def test_extract_structured_output_invalid_json() -> None:
    assert extract_spec_content_from_structured_output("not json") is None


def test_extract_structured_output_empty() -> None:
    assert extract_spec_content_from_structured_output("") is None


def test_extract_structured_output_empty_content() -> None:
    assert extract_spec_content_from_structured_output(json.dumps({"content": "  "})) is None


# ── Extract from text (tier 3 fallback) ──────────────────────────


def test_extract_spec_content_from_text_markdown() -> None:
    stdout = "# Overview\nUse OAuth2.\n\n## Testing Strategy\nAdd unit tests."
    assert extract_spec_content_from_text(stdout) == stdout


def test_extract_spec_content_from_text_json_fallback() -> None:
    stdout = '{"content": "# Overview\\nUse OAuth2."}'
    assert extract_spec_content_from_text(stdout) == "# Overview\nUse OAuth2."
