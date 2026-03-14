from __future__ import annotations

import json
from typing import Any

from backend.ai.json_extract import extract_first_json_object

SPEC_SCHEMA: dict[str, dict[str, str]] = {
    "mission": {
        "goal": "scalar",
        "success_outcome": "scalar",
        "implementation_level": "scalar",
    },
    "scope": {
        "must_do": "list",
        "must_not_do": "list",
        "deferred_work": "list",
    },
    "constraints": {
        "hard_constraints": "list",
        "change_budget": "scalar",
        "touch_boundaries": "list",
        "external_dependencies": "list",
    },
    "autonomy": {
        "allowed_decisions": "list",
        "requires_confirmation": "list",
        "default_policy_when_unclear": "scalar",
    },
    "verification": {
        "acceptance_checks": "list",
        "definition_of_done": "scalar",
        "evidence_expected": "list",
    },
    "execution_controls": {
        "quality_profile": "scalar",
        "tooling_limits": "list",
        "output_expectation": "scalar",
        "conflict_policy": "scalar",
        "missing_decision_policy": "scalar",
    },
    "assumptions": {
        "assumptions_in_force": "list",
    },
}

SPEC_FIELDS = tuple(SPEC_SCHEMA.keys())


def build_spec_generation_prompt(
    context: dict[str, Any],
    retry_feedback: str | None = None,
) -> str:
    prompt_parts = [
        "You are generating a PlanningTree spec draft for a single node.",
        "Generate a complete replacement draft for spec.md using only the canonical node context provided.",
        (
            "This is an agent-recommended starting draft for user review. "
            "Fill only high-confidence fields and leave uncertain strings as empty strings and uncertain lists as empty arrays."
        ),
        (
            "Return exactly one JSON object. Do not use markdown fences. "
            "Do not include any explanation before or after the JSON."
        ),
        (
            "Use exactly these top-level object keys: "
            "mission, scope, constraints, autonomy, verification, execution_controls, assumptions."
        ),
        (
            "Inside each section, use only the required scalar string fields and array-of-string list fields shown "
            "in the schema example. Do not return markdown-encoded strings."
        ),
        (
            "Treat Brief as durable node context. The Spec you produce is the editable execution contract. "
            "Do not copy context into the contract unless it constrains, permits, verifies, or governs the work."
        ),
        (
            "Do not run tools. Do not inspect files. Do not browse the workspace. "
            "The canonical context below is sufficient to answer."
        ),
        "Canonical context:",
        json.dumps(context, indent=2, ensure_ascii=True),
        "Required JSON shape example:",
        json.dumps(spec_generation_schema_example(), indent=2, ensure_ascii=True),
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


def parse_spec_generation_response(raw_text: str) -> dict[str, Any] | None:
    payload = extract_first_json_object(raw_text)
    if payload is None or not isinstance(payload, dict):
        return None
    return {field: payload[field] for field in SPEC_FIELDS if field in payload}


def spec_generation_issues(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return ["No JSON object found in the model response."]

    issues: list[str] = []
    for section_key, fields in SPEC_SCHEMA.items():
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
    unknown_sections = [section_key for section_key in payload if section_key not in SPEC_SCHEMA]
    if unknown_sections:
        issues.append(f"Unknown top-level sections: {', '.join(sorted(unknown_sections))}.")
    return issues


def validate_spec_generation_payload(payload: dict[str, Any] | None) -> bool:
    return not spec_generation_issues(payload)


def normalize_spec_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for section_key, fields in SPEC_SCHEMA.items():
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


def build_spec_retry_feedback(issues: list[str]) -> str:
    issue_block = "\n".join(f"- {issue}" for issue in issues) if issues else "- No JSON object found."
    return "\n".join(
        [
            "The response did not match the required spec-generation JSON shape.",
            "Validation issues:",
            issue_block,
            "Required JSON shape example:",
            json.dumps(spec_generation_schema_example(), indent=2, ensure_ascii=True),
        ]
    )


def spec_generation_schema_example() -> dict[str, Any]:
    return {
        "mission": {
            "goal": "State what this node should achieve.",
            "success_outcome": "Describe the concrete deliverable.",
            "implementation_level": "working",
        },
        "scope": {
            "must_do": ["Required deliverable"],
            "must_not_do": ["Out of scope item"],
            "deferred_work": ["Follow-up item"],
        },
        "constraints": {
            "hard_constraints": ["Non-negotiable rule"],
            "change_budget": "Keep edits limited to this node's scope.",
            "touch_boundaries": ["Allowed paths or systems"],
            "external_dependencies": ["Upstream artifact or API"],
        },
        "autonomy": {
            "allowed_decisions": ["Safe local decision"],
            "requires_confirmation": ["Product decision needing approval"],
            "default_policy_when_unclear": "ask_user",
        },
        "verification": {
            "acceptance_checks": ["Specific pass/fail check"],
            "definition_of_done": "Conditions for completion.",
            "evidence_expected": ["Tests or artifacts"],
        },
        "execution_controls": {
            "quality_profile": "standard",
            "tooling_limits": ["Stay within workspace root"],
            "output_expectation": "concise progress updates",
            "conflict_policy": "reopen_spec",
            "missing_decision_policy": "reopen_spec",
        },
        "assumptions": {
            "assumptions_in_force": ["Assumption that still needs confirmation"],
        },
    }
