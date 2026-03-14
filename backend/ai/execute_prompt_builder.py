from __future__ import annotations

import json
from typing import Any

from backend.ai.json_extract import extract_first_json_object

EXECUTE_FIELDS = (
    "status",
    "assistant_summary",
)

VALID_EXECUTE_STATUSES = {"completed", "failed"}


def build_execute_prompt(context: dict[str, Any], retry_feedback: str | None = None) -> str:
    prompt_parts = [
        "You are the PlanningTree execution assistant for a single node.",
        (
            "Execute only from the current confirmed Spec and current Plan. "
            "Use the Brief only as supporting context. Brief must never override the Spec."
        ),
        (
            "Do not ask the user any new questions in this mode. "
            "If execution is blocked by a missing decision or conflict, stop and return a failure summary."
        ),
        (
            "Return exactly one JSON object. Do not use markdown fences. "
            "Do not include any explanation before or after the JSON."
        ),
        "Use exactly these top-level keys: status, assistant_summary.",
        (
            "status must be either 'completed' or 'failed'. "
            "assistant_summary must always be a non-empty string."
        ),
        "Execution context:",
        json.dumps(context, indent=2, ensure_ascii=True),
        "Required JSON shape example:",
        json.dumps(execute_schema_example(), indent=2, ensure_ascii=True),
    ]

    if retry_feedback:
        prompt_parts.extend(
            [
                "The previous attempt was invalid.",
                retry_feedback,
                "Fix the issues and return a valid JSON object with the exact required keys.",
            ]
        )

    return "\n\n".join(prompt_parts)


def parse_execute_response(raw_text: str) -> dict[str, Any] | None:
    payload = extract_first_json_object(raw_text)
    if payload is None or not isinstance(payload, dict):
        return None
    return {field: payload[field] for field in EXECUTE_FIELDS if field in payload}


def execute_issues(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return ["No JSON object found in the model response."]

    issues: list[str] = []
    for field in EXECUTE_FIELDS:
        if field not in payload:
            issues.append(f"{field} is required.")
            continue
        if not isinstance(payload.get(field), str):
            issues.append(f"{field} must be a string.")

    status = str(payload.get("status") or "").strip()
    if status not in VALID_EXECUTE_STATUSES:
        issues.append("status must be 'completed' or 'failed'.")
    if not str(payload.get("assistant_summary") or "").strip():
        issues.append("assistant_summary is required.")

    unknown = [field for field in payload if field not in EXECUTE_FIELDS]
    if unknown:
        issues.append(f"Unknown top-level fields: {', '.join(sorted(unknown))}.")
    return issues


def normalize_execute_payload(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "status": str(payload.get("status") or "").strip(),
        "assistant_summary": str(payload.get("assistant_summary") or "").strip(),
    }


def build_execute_retry_feedback(issues: list[str]) -> str:
    issue_block = "\n".join(f"- {issue}" for issue in issues) if issues else "- No JSON object found."
    return "\n".join(
        [
            "The response did not match the required execute JSON shape.",
            "Validation issues:",
            issue_block,
            "Required JSON shape example:",
            json.dumps(execute_schema_example(), indent=2, ensure_ascii=True),
        ]
    )


def execute_schema_example() -> dict[str, str]:
    return {
        "status": "completed",
        "assistant_summary": "Executed the approved plan and verified the node outcome.",
    }
