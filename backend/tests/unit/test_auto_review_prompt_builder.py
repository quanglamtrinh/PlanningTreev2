from __future__ import annotations

import json

from backend.ai.auto_review_prompt_builder import (
    build_auto_review_output_schema,
    extract_auto_review_result,
)


def test_auto_review_output_schema_requires_all_finding_keys() -> None:
    schema = build_auto_review_output_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "summary",
        "checkpoint_summary",
        "overall_severity",
        "overall_score",
        "findings",
    ]

    findings = schema["properties"]["findings"]
    items = findings["items"]
    assert items["additionalProperties"] is False
    assert items["required"] == [
        "title",
        "severity",
        "description",
        "file_path",
        "evidence",
        "suggested_followup",
    ]


def test_extract_auto_review_result_omits_blank_optional_values() -> None:
    payload = json.dumps(
        {
            "summary": "Looks solid overall.",
            "checkpoint_summary": "Looks solid overall.",
            "overall_severity": "info",
            "overall_score": 92,
            "findings": [
                {
                    "title": "No blocking issues",
                    "severity": "info",
                    "description": "Implementation matches the spec.",
                    "file_path": "",
                    "evidence": "",
                    "suggested_followup": "",
                }
            ],
        }
    )

    result = extract_auto_review_result(payload)

    assert result == {
        "summary": "Looks solid overall.",
        "checkpoint_summary": "Looks solid overall.",
        "overall_severity": "info",
        "overall_score": 92,
        "findings": [
            {
                "title": "No blocking issues",
                "severity": "info",
                "description": "Implementation matches the spec.",
            }
        ],
    }
