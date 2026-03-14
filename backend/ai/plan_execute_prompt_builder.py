from __future__ import annotations

import json
from typing import Any

from backend.ai.json_extract import extract_first_json_object

PLAN_EXECUTE_FIELDS = (
    "status",
    "plan_markdown",
    "assistant_summary",
    "spec_question_title",
    "spec_question_details",
)

VALID_STATUSES = {"completed", "blocked_on_spec_question"}


def build_plan_execute_prompt(context: dict[str, Any], retry_feedback: str | None = None) -> str:
    prompt_parts = [
        "You are the PlanningTree execution assistant for a single node.",
        "Use the confirmed Spec as the governing contract for execution.",
        "Use the Brief only as durable workflow context. Brief must never override the Spec.",
        (
            "Your task is to first create a concrete execution plan for this node, "
            "then execute against that plan in the current workspace."
        ),
        (
            "If you encounter a blocking conflict with the Spec or a missing decision that matters for the current "
            "action, stop immediately before additional workspace mutation and return a spec question instead of continuing."
        ),
        (
            "Return exactly one JSON object. Do not use markdown fences. "
            "Do not include any explanation before or after the JSON."
        ),
        (
            "Use exactly these top-level keys: "
            "status, plan_markdown, assistant_summary, spec_question_title, spec_question_details."
        ),
        (
            "status must be either 'completed' or 'blocked_on_spec_question'. "
            "When status is 'completed', plan_markdown and assistant_summary must be non-empty. "
            "When status is 'blocked_on_spec_question', assistant_summary, spec_question_title, and spec_question_details "
            "must be non-empty. plan_markdown may be empty if no stable plan was produced."
        ),
        "Execution context:",
        json.dumps(context, indent=2, ensure_ascii=True),
        "Required JSON shape example:",
        json.dumps(plan_execute_schema_example(), indent=2, ensure_ascii=True),
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


def parse_plan_execute_response(raw_text: str) -> dict[str, Any] | None:
    payload = extract_first_json_object(raw_text)
    if payload is None or not isinstance(payload, dict):
        return None
    return {field: payload[field] for field in PLAN_EXECUTE_FIELDS if field in payload}


def plan_execute_issues(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return ["No JSON object found in the model response."]

    issues: list[str] = []
    for field in PLAN_EXECUTE_FIELDS:
        if field not in payload:
            issues.append(f"{field} is required.")
            continue
        if not isinstance(payload.get(field), str):
            issues.append(f"{field} must be a string.")

    status = str(payload.get("status") or "").strip()
    if status not in VALID_STATUSES:
        issues.append("status must be 'completed' or 'blocked_on_spec_question'.")
    if status == "completed":
        if not str(payload.get("plan_markdown") or "").strip():
            issues.append("plan_markdown is required when status='completed'.")
        if not str(payload.get("assistant_summary") or "").strip():
            issues.append("assistant_summary is required when status='completed'.")
    if status == "blocked_on_spec_question":
        if not str(payload.get("assistant_summary") or "").strip():
            issues.append("assistant_summary is required when status='blocked_on_spec_question'.")
        if not str(payload.get("spec_question_title") or "").strip():
            issues.append("spec_question_title is required when status='blocked_on_spec_question'.")
        if not str(payload.get("spec_question_details") or "").strip():
            issues.append("spec_question_details is required when status='blocked_on_spec_question'.")
    return issues


def normalize_plan_execute_payload(payload: dict[str, Any]) -> dict[str, str]:
    return {
        field: str(payload.get(field) or "").strip()
        for field in PLAN_EXECUTE_FIELDS
    }


def build_plan_execute_retry_feedback(issues: list[str]) -> str:
    issue_block = "\n".join(f"- {issue}" for issue in issues) if issues else "- No JSON object found."
    return "\n".join(
        [
            "The response did not match the required plan-and-execute JSON shape.",
            "Validation issues:",
            issue_block,
            "Required JSON shape example:",
            json.dumps(plan_execute_schema_example(), indent=2, ensure_ascii=True),
        ]
    )


def plan_execute_schema_example() -> dict[str, str]:
    return {
        "status": "completed",
        "plan_markdown": "# Plan\n\n1. Inspect the existing implementation.\n2. Apply the required change.\n3. Run targeted verification.",
        "assistant_summary": "Created the execution plan, applied the change, and verified the result.",
        "spec_question_title": "",
        "spec_question_details": "",
    }
