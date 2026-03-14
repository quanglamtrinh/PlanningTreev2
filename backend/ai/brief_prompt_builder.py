from __future__ import annotations

import json
from typing import Any

from backend.ai.json_extract import extract_first_json_object

BRIEF_SCHEMA: dict[str, dict[str, str]] = {
    "node_snapshot": {
        "node_summary": "scalar",
        "why_this_node_exists_now": "scalar",
        "current_focus": "scalar",
    },
    "active_inherited_context": {
        "active_goals_from_parent": "list",
        "active_constraints_from_parent": "list",
        "active_decisions_in_force": "list",
    },
    "accepted_upstream_facts": {
        "accepted_outputs": "list",
        "available_artifacts": "list",
        "confirmed_dependencies": "list",
    },
    "runtime_state": {
        "status": "scalar",
        "completed_so_far": "list",
        "current_blockers": "list",
        "next_best_action": "scalar",
    },
    "pending_escalations": {
        "open_risks": "list",
        "pending_user_decisions": "list",
        "fallback_direction_if_unanswered": "scalar",
    },
}

BRIEF_FIELDS = tuple(BRIEF_SCHEMA.keys())


def build_brief_generation_prompt(
    context: dict[str, Any],
    retry_feedback: str | None = None,
) -> str:
    prompt_parts = [
        "You are generating a locked PlanningTree Brief for a single node handoff.",
        (
            "The Brief is a durable workflow snapshot for this node because planning threads are not durable enough "
            "to be trusted as workflow truth."
        ),
        (
            "Synthesize only context that is still in force at handoff time. "
            "Do not invent details. Do not turn the Brief into an execution contract."
        ),
        (
            "Return exactly one JSON object. Do not use markdown fences. "
            "Do not include any explanation before or after the JSON."
        ),
        (
            "Use exactly these top-level object keys: "
            "node_snapshot, active_inherited_context, accepted_upstream_facts, runtime_state, pending_escalations."
        ),
        (
            "Inside each section, use only the required scalar string fields and array-of-string list fields shown "
            "in the schema example. Do not return markdown-encoded strings."
        ),
        "Canonical handoff context:",
        json.dumps(context, indent=2, ensure_ascii=True),
        "Required JSON shape example:",
        json.dumps(brief_generation_schema_example(), indent=2, ensure_ascii=True),
    ]

    if retry_feedback:
        prompt_parts.extend(
            [
                "The previous attempt was invalid.",
                retry_feedback,
                "Fix the issues and return a valid JSON object with the exact required keys and field types.",
            ]
        )

    return "\n\n".join(prompt_parts)


def parse_brief_generation_response(raw_text: str) -> dict[str, Any] | None:
    payload = extract_first_json_object(raw_text)
    if payload is None or not isinstance(payload, dict):
        return None
    return {field: payload[field] for field in BRIEF_FIELDS if field in payload}


def brief_generation_issues(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return ["No JSON object found in the model response."]

    issues: list[str] = []
    for section_key, fields in BRIEF_SCHEMA.items():
        section = payload.get(section_key)
        if section_key not in payload:
            issues.append(f"{section_key} is required.")
            continue
        if not isinstance(section, dict):
            issues.append(f"{section_key} must be an object.")
            continue
        for field_key, field_type in fields.items():
            if field_key not in section:
                issues.append(f"{section_key}.{field_key} is required.")
                continue
            value = section.get(field_key)
            if field_type == "list":
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    issues.append(f"{section_key}.{field_key} must be a list of strings.")
            elif not isinstance(value, str):
                issues.append(f"{section_key}.{field_key} must be a string.")
        unknown = [field_key for field_key in section if field_key not in fields]
        if unknown:
            issues.append(
                f"{section_key} contains unknown fields: {', '.join(sorted(unknown))}."
            )
    unknown_sections = [section_key for section_key in payload if section_key not in BRIEF_SCHEMA]
    if unknown_sections:
        issues.append(f"Unknown top-level sections: {', '.join(sorted(unknown_sections))}.")
    return issues


def normalize_brief_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for section_key, fields in BRIEF_SCHEMA.items():
        raw_section = payload.get(section_key, {})
        section = raw_section if isinstance(raw_section, dict) else {}
        normalized[section_key] = {}
        for field_key, field_type in fields.items():
            value = section.get(field_key)
            if field_type == "list":
                normalized[section_key][field_key] = [
                    str(item).strip()
                    for item in (value if isinstance(value, list) else [])
                    if str(item).strip()
                ]
            else:
                normalized[section_key][field_key] = str(value or "").strip()
    return normalized


def build_brief_retry_feedback(issues: list[str]) -> str:
    issue_block = "\n".join(f"- {issue}" for issue in issues) if issues else "- No JSON object found."
    return "\n".join(
        [
            "The response did not match the required brief-generation JSON shape.",
            "Validation issues:",
            issue_block,
            "Required JSON shape example:",
            json.dumps(brief_generation_schema_example(), indent=2, ensure_ascii=True),
        ]
    )


def brief_generation_schema_example() -> dict[str, Any]:
    return {
        "node_snapshot": {
            "node_summary": "What this node owns now.",
            "why_this_node_exists_now": "Why this work is next.",
            "current_focus": "Immediate focus for the node.",
        },
        "active_inherited_context": {
            "active_goals_from_parent": ["Parent goal still in force"],
            "active_constraints_from_parent": ["Constraint that still applies"],
            "active_decisions_in_force": ["Decision already settled upstream"],
        },
        "accepted_upstream_facts": {
            "accepted_outputs": ["Completed upstream result"],
            "available_artifacts": ["Artifact available to use"],
            "confirmed_dependencies": ["Dependency already confirmed"],
        },
        "runtime_state": {
            "status": "ready",
            "completed_so_far": [],
            "current_blockers": [],
            "next_best_action": "Draft and confirm the Spec.",
        },
        "pending_escalations": {
            "open_risks": ["Known risk if any"],
            "pending_user_decisions": [],
            "fallback_direction_if_unanswered": "Stay within confirmed constraints.",
        },
    }
