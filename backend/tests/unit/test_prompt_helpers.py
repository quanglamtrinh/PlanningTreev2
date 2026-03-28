from __future__ import annotations

from backend.ai.prompt_helpers import (
    format_frame_content,
    normalize_text,
    strip_json_fence,
    truncate,
)


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  hello   world  ") == "hello world"


def test_normalize_text_non_string() -> None:
    assert normalize_text(None) == ""
    assert normalize_text(42) == ""


def test_truncate_short_text() -> None:
    assert truncate("hello", 10) == "hello"


def test_truncate_long_text() -> None:
    assert truncate("hello world", 8) == "hello..."


def test_format_frame_content_normal() -> None:
    result = format_frame_content("# Frame\ncontent", 1000)
    assert result.startswith("Confirmed frame document:")
    assert "# Frame" in result


def test_format_frame_content_empty() -> None:
    assert "(empty)" in format_frame_content("", 1000)
    assert "(empty)" in format_frame_content("   ", 1000)


def test_format_frame_content_truncates() -> None:
    long = "x" * 200
    result = format_frame_content(long, 100)
    assert "..." in result


def test_strip_json_fence_with_fence() -> None:
    assert strip_json_fence('```json\n{"key": "val"}\n```') == '{"key": "val"}'


def test_strip_json_fence_with_json_uppercase() -> None:
    assert strip_json_fence('```JSON\n{"key": "val"}\n```') == '{"key": "val"}'


def test_strip_json_fence_without_language() -> None:
    assert strip_json_fence('```\n{"key": "val"}\n```') == '{"key": "val"}'


def test_strip_json_fence_no_fence() -> None:
    assert strip_json_fence('{"key": "val"}') == '{"key": "val"}'


def test_strip_json_fence_empty() -> None:
    assert strip_json_fence("") == ""
    assert strip_json_fence("  ") == ""
