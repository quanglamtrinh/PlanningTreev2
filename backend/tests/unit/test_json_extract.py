from __future__ import annotations

from backend.ai.json_extract import extract_first_json_object


def test_extract_first_json_object_from_plain_json() -> None:
    payload = extract_first_json_object('{"epics": [{"title": "Core"}]}')

    assert payload == {"epics": [{"title": "Core"}]}


def test_extract_first_json_object_from_markdown_wrapped_text() -> None:
    payload = extract_first_json_object(
        "Here is the plan:\n```json\n{\"subtasks\": [{\"prompt\": \"Build it\"}]}\n```\nThanks."
    )

    assert payload == {"subtasks": [{"prompt": "Build it"}]}


def test_extract_first_json_object_returns_none_for_invalid_text() -> None:
    assert extract_first_json_object("not json at all") is None
