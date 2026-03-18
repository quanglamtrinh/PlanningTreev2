from __future__ import annotations

import json
from typing import Any

from backend.ai.json_extract import extract_first_json_object
from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY, CanonicalSplitModeId

STRICTNESS_LEVELS = ["standard", "guided", "strict"]
_REQUIRED_TOP_LEVEL_KEYS = {"subtasks"}
_REQUIRED_SUBTASK_KEYS = {"id", "title", "objective", "why_now"}
_CANONICAL_MODE_INTENTS: dict[CanonicalSplitModeId, str] = {
    "workflow": "workflow-first sequential split",
    "simplify_workflow": "minimum valid core workflow first, then additive reintroduction",
    "phase_breakdown": "phase-based sequential delivery split",
    "agent_breakdown": "conservative non-workflow split when the other shapes are a weak fit",
}


def planning_render_tool() -> dict[str, Any]:
    return {
        "name": "emit_render_data",
        "description": (
            "Send structured payload for the app UI to render. "
            "Call this before writing your summary message. "
            "Do not duplicate the structured payload in plain text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["split_result"],
                },
                "payload": {
                    "type": "object",
                },
            },
            "required": ["kind", "payload"],
        },
    }


def build_planning_base_instructions(mode: CanonicalSplitModeId | None = None) -> str:
    if mode is None:
        mode_section = [
            "Support only these canonical split modes: workflow, simplify_workflow, phase_breakdown, agent_breakdown.",
            "All canonical split modes must emit the same flat_subtasks_v1 payload shape.",
            "Respect the selected mode's configured subtask count limits.",
            "Canonical payload shape example:",
            json.dumps(_shared_schema_example(), indent=2, ensure_ascii=True),
        ]
        mode_section.extend(
            [f"- {mode_id}: {_CANONICAL_MODE_INTENTS[mode_id]}" for mode_id in CANONICAL_SPLIT_MODE_REGISTRY]
        )
    else:
        spec = _canonical_mode_spec_or_raise(mode)
        mode_section = [
            f"Planning mode: {mode}.",
            f"Mode label: {spec['label']}.",
            f"Mode intent: {_CANONICAL_MODE_INTENTS[mode]}.",
            _mode_count_instruction(mode),
            "Emit only the flat_subtasks_v1 payload shape:",
            json.dumps(split_payload_schema_example(mode), indent=2, ensure_ascii=True),
        ]

    return "\n\n".join(
        [
            "You are the PlanningTree planning assistant.",
            *mode_section,
            "When splitting a node, first call emit_render_data(kind='split_result', payload=...).",
            "After the tool call, write a brief human-readable summary for the user.",
            "Do not duplicate the structured payload in the summary text.",
        ]
    )


def build_split_user_message(mode: CanonicalSplitModeId, task_context: dict[str, Any]) -> str:
    spec = _canonical_mode_spec_or_raise(mode)
    root_goal = str(task_context.get("root_prompt", "")).strip()
    current_prompt = str(task_context.get("current_node_prompt", "")).strip()
    parent_chain = task_context.get("parent_chain_prompts", [])
    prior_summaries = task_context.get("prior_node_summaries_compact", [])

    lines = [
        f"Decompose this node using {spec['label'].lower()} mode.",
        f"Mode intent: {_CANONICAL_MODE_INTENTS[mode]}.",
        _mode_count_instruction(mode),
    ]
    if current_prompt:
        lines.extend(["", f'Node: "{current_prompt}"'])
    if root_goal:
        lines.extend(["", f"Project goal: {root_goal}"])
    if isinstance(parent_chain, list) and parent_chain:
        lines.append("")
        lines.append("Parent chain:")
        lines.extend(f"- {item}" for item in parent_chain if isinstance(item, str) and item.strip())
    if isinstance(prior_summaries, list) and prior_summaries:
        lines.append("")
        lines.append("Completed sibling context:")
        for item in prior_summaries:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            description = str(item.get("description", "")).strip()
            if title and description:
                lines.append(f"- {title}: {description}")
            elif title or description:
                lines.append(f"- {title or description}")
    return "\n".join(lines).strip()


def build_generation_prompt(
    mode: CanonicalSplitModeId,
    task_context: dict[str, Any],
    strictness: str,
    retry_feedback: dict[str, Any] | None,
) -> str:
    _canonical_mode_spec_or_raise(mode)
    if strictness not in STRICTNESS_LEVELS:
        raise ValueError(f"Unsupported strictness level: {strictness}")

    prompt_parts = [
        "You are decomposing a planning-tree node into implementation-ready child tasks.",
        f"Planning mode: {mode}.",
        f"Mode intent: {_CANONICAL_MODE_INTENTS[mode]}.",
        _mode_count_instruction(mode),
        "Return exactly one JSON object. Do not use markdown fences. Do not add any explanation before or after the JSON.",
        "The JSON must have exactly one top-level key: subtasks.",
        "Each subtask must contain exactly: id, title, objective, why_now.",
        "Preserve the intended execution order in the list. Do not sort by id.",
        _strictness_instructions(strictness),
        "Task context:",
        json.dumps(task_context, indent=2, ensure_ascii=True),
        "Required JSON shape example:",
        json.dumps(split_payload_schema_example(mode), indent=2, ensure_ascii=True),
    ]

    if retry_feedback:
        prompt_parts.extend(
            [
                "The previous attempt failed validation.",
                json.dumps(retry_feedback, indent=2, ensure_ascii=True),
                "Fix the issues and return a JSON object that matches the required structure exactly.",
            ]
        )

    return "\n\n".join(prompt_parts)


def parse_generation_response(mode: CanonicalSplitModeId, raw_text: str) -> dict[str, Any] | None:
    _canonical_mode_spec_or_raise(mode)
    payload = extract_first_json_object(raw_text)
    if payload is None or not isinstance(payload, dict):
        return None
    return _parse_canonical_generation_payload(mode, payload)


def validate_split_payload(mode: CanonicalSplitModeId, payload: dict[str, Any]) -> bool:
    return not split_payload_issues(mode, payload)


def split_payload_schema_example(mode: CanonicalSplitModeId) -> dict[str, Any]:
    spec = _canonical_mode_spec_or_raise(mode)
    subtasks = []
    for index in range(1, spec["min_items"] + 1):
        subtasks.append(
            {
                "id": f"S{index}",
                "title": f"Subtask {index}",
                "objective": f"What step {index} achieves",
                "why_now": f"Why step {index} happens now",
            }
        )
    return {"subtasks": subtasks}


def split_payload_issues(mode: CanonicalSplitModeId, payload: dict[str, Any]) -> list[str]:
    spec = _canonical_mode_spec_or_raise(mode)
    if not isinstance(payload, dict):
        return ["payload must be an object"]

    issues: list[str] = []
    payload_keys = set(payload.keys())
    for missing_key in sorted(_REQUIRED_TOP_LEVEL_KEYS - payload_keys):
        issues.append(f"payload.{missing_key} is required")
    for extra_key in sorted(payload_keys - _REQUIRED_TOP_LEVEL_KEYS):
        issues.append(f"payload.{extra_key} is not allowed")

    raw_subtasks = payload.get("subtasks")
    if not isinstance(raw_subtasks, list):
        if "subtasks" in payload:
            issues.append("payload.subtasks must be a list")
        return issues

    if not spec["min_items"] <= len(raw_subtasks) <= spec["max_items"]:
        issues.append(f"payload.subtasks must contain {spec['min_items']} to {spec['max_items']} items")

    seen_ids: set[str] = set()
    for index, subtask in enumerate(raw_subtasks):
        if not isinstance(subtask, dict):
            issues.append(f"payload.subtasks[{index}] must be an object")
            continue

        subtask_keys = set(subtask.keys())
        for missing_key in sorted(_REQUIRED_SUBTASK_KEYS - subtask_keys):
            issues.append(f"payload.subtasks[{index}].{missing_key} is required")
        for extra_key in sorted(subtask_keys - _REQUIRED_SUBTASK_KEYS):
            issues.append(f"payload.subtasks[{index}].{extra_key} is not allowed")

        normalized_id = ""
        for field in sorted(_REQUIRED_SUBTASK_KEYS):
            if field not in subtask:
                continue
            value = subtask.get(field)
            normalized_value = _normalize_text(value)
            if not normalized_value:
                issues.append(f"payload.subtasks[{index}].{field} must be a non-empty string")
                continue
            if field == "id":
                normalized_id = normalized_value

        if normalized_id:
            if normalized_id in seen_ids:
                issues.append(f"payload.subtasks[{index}].id must be unique")
            else:
                seen_ids.add(normalized_id)

    return issues


def build_hidden_retry_feedback(mode: CanonicalSplitModeId, issues: list[str]) -> str:
    issue_lines = issues or ["No valid emit_render_data(kind='split_result', payload=...) tool call was captured."]
    issue_block = "\n".join(f"- {issue}" for issue in issue_lines)
    schema = json.dumps(split_payload_schema_example(mode), indent=2, ensure_ascii=True)
    return "\n".join(
        [
            f"The previous {mode} split attempt did not produce a valid split_result payload.",
            f"Mode count rule: {_mode_count_instruction(mode)}",
            "Fix the structured payload and call emit_render_data before writing your summary.",
            "Validation issues:",
            issue_block,
            "Required payload example:",
            schema,
        ]
    )


def _canonical_mode_spec_or_raise(mode: CanonicalSplitModeId | str) -> dict[str, Any]:
    spec = CANONICAL_SPLIT_MODE_REGISTRY.get(mode)  # type: ignore[arg-type]
    if spec is None:
        raise ValueError(f"Unsupported split mode: {mode}")
    return spec


def _mode_count_instruction(mode: CanonicalSplitModeId) -> str:
    spec = _canonical_mode_spec_or_raise(mode)
    return f"Generate {spec['min_items']} to {spec['max_items']} ordered subtasks."


def _shared_schema_example() -> dict[str, Any]:
    return {
        "subtasks": [
            {
                "id": "S1",
                "title": "Subtask title",
                "objective": "What this step achieves",
                "why_now": "Why this should happen now",
            }
        ]
    }


def _strictness_instructions(strictness: str) -> str:
    if strictness == "standard":
        return "Keep the decomposition concrete and concise. Respect the mode's item-count limits and return JSON only."
    if strictness == "guided":
        return "Use the exact required keys, stay within the configured count range, and make every subtask actionable. Return JSON only."
    return (
        "Output ONLY a valid JSON object with exactly one top-level key: subtasks. "
        "Each subtask must contain exactly id, title, objective, why_now."
    )


def _parse_canonical_generation_payload(mode: CanonicalSplitModeId, payload: dict[str, Any]) -> dict[str, Any] | None:
    if set(payload.keys()) != _REQUIRED_TOP_LEVEL_KEYS:
        return None

    raw_subtasks = payload.get("subtasks")
    if not isinstance(raw_subtasks, list):
        return None

    normalized_subtasks: list[dict[str, str]] = []
    for raw_subtask in raw_subtasks:
        if not isinstance(raw_subtask, dict):
            return None
        if set(raw_subtask.keys()) != _REQUIRED_SUBTASK_KEYS:
            return None

        normalized_subtask: dict[str, str] = {}
        for field in ("id", "title", "objective", "why_now"):
            value = raw_subtask.get(field)
            if not isinstance(value, str):
                return None
            normalized_subtask[field] = _normalize_text(value)
        normalized_subtasks.append(normalized_subtask)

    normalized_payload = {"subtasks": normalized_subtasks}
    if not validate_split_payload(mode, normalized_payload):
        return None
    return normalized_payload


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())
