from __future__ import annotations

import json
from typing import Any

from backend.ai.json_extract import extract_first_json_object

PLAN_TURN_FIELDS = (
    "kind",
    "assistant_summary",
    "change_summary",
    "changed_contract_axes",
    "recommended_next_step",
)

VALID_PLAN_KINDS = {"plan_ready", "requires_spec_update"}
ALLOWED_CONTRACT_AXES = {"scope", "constraints", "acceptance", "dependencies", "environment"}


def build_plan_turn_prompt(
    context: dict[str, Any],
    *,
    user_message: str,
    retry_feedback: str | None = None,
) -> str:
    prompt_parts = [
        "You are the PlanningTree planner for a single node.",
        "You are in planning-only mode. Do not mutate the workspace.",
        (
            "Use the confirmed Spec as the governing contract. "
            "Use the Brief only as durable workflow context. Brief must never override the Spec."
        ),
        (
            "Your job is to finish execution planning for this node. "
            "Use native requestUserInput only when high-impact execution information is missing."
        ),
        (
            "High-impact missing information means information whose absence would likely make the plan wrong, "
            "materially change what should be done, materially change how it should be done, create avoidable risk "
            "or side effects, or materially change how success should be evaluated."
        ),
        (
            "Do not ask follow-up questions when a reasonable default is sufficient. "
            "Never ask for information that can be derived from the Spec, Brief, or repo context."
        ),
        (
            "If you must ask the user, keep the elicitation budget tight: ask 1 short question if possible, "
            "ask at most 3 short questions total, and prefer multiple-choice options before free-form input."
        ),
        (
            "Planner answers are plan-scoped, not automatic Spec edits. "
            "If the user answer changes scope, constraints, acceptance criteria, dependencies, or environment in a way "
            "that changes the confirmed contract, do not silently continue with a ready plan."
        ),
        (
            "When the confirmed contract still holds, produce the execution plan as a plan item. "
            "The final assistant message must contain only the structured branching JSON. "
            "Do not include plan text in the final JSON."
        ),
        (
            "When the user answer changes the confirmed contract, return kind='requires_spec_update' with a concise "
            "handoff for Spec review instead of finalizing a ready plan."
        ),
        (
            "Return exactly one JSON object. Do not use markdown fences. "
            "Do not include any explanation before or after the JSON."
        ),
        "Canonical planning context:",
        json.dumps(context, indent=2, ensure_ascii=True),
        "Latest user message for this planning turn:",
        user_message,
        "Required JSON shape example:",
        json.dumps(plan_turn_schema_example(), indent=2, ensure_ascii=True),
    ]

    if retry_feedback:
        prompt_parts.extend(
            [
                "The previous attempt was invalid.",
                retry_feedback,
                "Fix the issues and return a valid JSON object that matches the required schema exactly.",
            ]
        )

    return "\n\n".join(prompt_parts)


def plan_turn_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "kind": {"const": "plan_ready"},
                    "assistant_summary": {"type": "string", "minLength": 1},
                },
                "required": ["kind", "assistant_summary"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "kind": {"const": "requires_spec_update"},
                    "change_summary": {"type": "string", "minLength": 1},
                    "changed_contract_axes": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "enum": sorted(ALLOWED_CONTRACT_AXES)},
                    },
                    "recommended_next_step": {"type": "string", "minLength": 1},
                },
                "required": [
                    "kind",
                    "change_summary",
                    "changed_contract_axes",
                    "recommended_next_step",
                ],
                "additionalProperties": False,
            },
        ],
    }


def parse_plan_turn_response(raw_text: str) -> dict[str, Any] | None:
    payload = extract_first_json_object(raw_text)
    if payload is None or not isinstance(payload, dict):
        return None
    return {field: payload[field] for field in PLAN_TURN_FIELDS if field in payload}


def plan_turn_issues(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return ["No JSON object found in the model response."]

    issues: list[str] = []
    kind = str(payload.get("kind") or "").strip()
    if kind not in VALID_PLAN_KINDS:
        issues.append("kind must be 'plan_ready' or 'requires_spec_update'.")

    assistant_summary = payload.get("assistant_summary")
    change_summary = payload.get("change_summary")
    changed_contract_axes = payload.get("changed_contract_axes")
    recommended_next_step = payload.get("recommended_next_step")

    if kind == "plan_ready":
        if not isinstance(assistant_summary, str) or not assistant_summary.strip():
            issues.append("assistant_summary is required when kind='plan_ready'.")
        unknown_fields = [field for field in payload if field not in {"kind", "assistant_summary"}]
        if unknown_fields:
            issues.append(
                f"Unknown top-level fields for kind='plan_ready': {', '.join(sorted(unknown_fields))}."
            )
        return issues

    if kind == "requires_spec_update":
        if not isinstance(change_summary, str) or not change_summary.strip():
            issues.append("change_summary is required when kind='requires_spec_update'.")
        if not isinstance(recommended_next_step, str) or not recommended_next_step.strip():
            issues.append("recommended_next_step is required when kind='requires_spec_update'.")
        if not isinstance(changed_contract_axes, list) or not changed_contract_axes:
            issues.append("changed_contract_axes must contain at least one item when kind='requires_spec_update'.")
        else:
            for index, item in enumerate(changed_contract_axes):
                axis = str(item or "").strip()
                if axis not in ALLOWED_CONTRACT_AXES:
                    issues.append(
                        "changed_contract_axes"
                        f"[{index}] must be one of: {', '.join(sorted(ALLOWED_CONTRACT_AXES))}."
                    )
        unknown_fields = [
            field
            for field in payload
            if field
            not in {"kind", "change_summary", "changed_contract_axes", "recommended_next_step"}
        ]
        if unknown_fields:
            issues.append(
                "Unknown top-level fields for kind='requires_spec_update': "
                f"{', '.join(sorted(unknown_fields))}."
            )
        return issues

    unknown_fields = [field for field in payload if field not in PLAN_TURN_FIELDS]
    if unknown_fields:
        issues.append(f"Unknown top-level fields: {', '.join(sorted(unknown_fields))}.")
    return issues


def normalize_plan_turn_payload(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or "").strip()
    if kind == "requires_spec_update":
        axes: list[str] = []
        if isinstance(payload.get("changed_contract_axes"), list):
            for item in payload["changed_contract_axes"]:
                axis = str(item or "").strip()
                if axis in ALLOWED_CONTRACT_AXES and axis not in axes:
                    axes.append(axis)
        return {
            "kind": kind,
            "change_summary": str(payload.get("change_summary") or "").strip(),
            "changed_contract_axes": axes,
            "recommended_next_step": str(payload.get("recommended_next_step") or "").strip(),
        }
    return {
        "kind": "plan_ready",
        "assistant_summary": str(payload.get("assistant_summary") or "").strip(),
    }


def build_plan_turn_retry_feedback(issues: list[str]) -> str:
    issue_block = "\n".join(f"- {issue}" for issue in issues) if issues else "- No JSON object found."
    return "\n".join(
        [
            "The response did not match the required planner JSON shape.",
            "Validation issues:",
            issue_block,
            "Required JSON shape example:",
            json.dumps(plan_turn_schema_example(), indent=2, ensure_ascii=True),
        ]
    )


def plan_turn_schema_example() -> dict[str, Any]:
    return {
        "kind": "plan_ready",
        "assistant_summary": "Plan is ready and bound to the current confirmed contract.",
    }
