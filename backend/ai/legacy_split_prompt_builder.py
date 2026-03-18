from __future__ import annotations

import json
from typing import Any

from backend.ai.json_extract import extract_first_json_object
from backend.split_contract import TemporaryLegacyRouteModeId

LEGACY_STRICTNESS_LEVELS = ["standard", "guided", "strict"]
_PHASE_KEYS = ["A", "B", "C", "D", "E"]


def build_legacy_planning_base_instructions(mode: TemporaryLegacyRouteModeId | None = None) -> str:
    if mode is not None and mode not in {"walking_skeleton", "slice"}:
        raise ValueError(f"Unsupported split mode: {mode}")

    if mode == "walking_skeleton":
        mode_section = [
            "Planning mode: walking_skeleton.",
            "Generate 1 to 3 epics. Each epic must contain 2 to 5 lifecycle phases.",
            json.dumps(legacy_split_payload_schema_example(mode), indent=2, ensure_ascii=True),
        ]
    elif mode == "slice":
        mode_section = [
            "Planning mode: slice.",
            "Generate 2 to 10 sequential vertical slices.",
            json.dumps(legacy_split_payload_schema_example(mode), indent=2, ensure_ascii=True),
        ]
    else:
        mode_section = [
            "Support both split modes: walking_skeleton and slice.",
            "For walking_skeleton, emit payloads shaped like:",
            json.dumps(legacy_split_payload_schema_example("walking_skeleton"), indent=2, ensure_ascii=True),
            "For slice, emit payloads shaped like:",
            json.dumps(legacy_split_payload_schema_example("slice"), indent=2, ensure_ascii=True),
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


def build_legacy_split_user_message(mode: TemporaryLegacyRouteModeId, task_context: dict[str, Any]) -> str:
    if mode not in {"walking_skeleton", "slice"}:
        raise ValueError(f"Unsupported split mode: {mode}")

    mode_label = "walking skeleton" if mode == "walking_skeleton" else "vertical slice"
    root_goal = str(task_context.get("root_prompt", "")).strip()
    current_prompt = str(task_context.get("current_node_prompt", "")).strip()
    parent_chain = task_context.get("parent_chain_prompts", [])
    prior_summaries = task_context.get("prior_node_summaries_compact", [])

    lines = [f"Decompose this node using {mode_label} mode."]
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


def build_legacy_generation_prompt(
    mode: TemporaryLegacyRouteModeId,
    task_context: dict[str, Any],
    strictness: str,
    retry_feedback: dict[str, Any] | None,
) -> str:
    if mode not in {"walking_skeleton", "slice"}:
        raise ValueError(f"Unsupported split mode: {mode}")
    if strictness not in LEGACY_STRICTNESS_LEVELS:
        raise ValueError(f"Unsupported strictness level: {strictness}")

    schema = (
        legacy_split_payload_schema_example("walking_skeleton")
        if mode == "walking_skeleton"
        else legacy_split_payload_schema_example("slice")
    )
    mode_instructions = (
        "Generate 1 to 3 epics. Each epic must contain 2 to 5 lifecycle phases that move from setup through delivery."
        if mode == "walking_skeleton"
        else "Generate 2 to 10 sequential vertical slices. Each subtask should unlock the next step."
    )

    prompt_parts = [
        "You are decomposing a planning-tree node into implementation-ready child tasks.",
        f"Planning mode: {mode}.",
        mode_instructions,
        _legacy_strictness_instructions(strictness),
        "Return exactly one JSON object. Do not use markdown fences. Do not add any explanation before or after the JSON.",
        "Task context:",
        json.dumps(task_context, indent=2, ensure_ascii=True),
        "Required JSON shape example:",
        json.dumps(schema, indent=2, ensure_ascii=True),
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


# Temporary alias during the bridge period for any older imports.
legacy_build_generation_prompt = build_legacy_generation_prompt


def parse_legacy_generation_response(
    mode: TemporaryLegacyRouteModeId,
    raw_text: str,
) -> dict[str, Any] | None:
    payload = extract_first_json_object(raw_text)
    if payload is None:
        return None
    if mode == "walking_skeleton":
        return _parse_ws_generation_payload(payload)
    if mode == "slice":
        return _parse_slice_generation_payload(payload)
    return None


def validate_legacy_split_payload(mode: TemporaryLegacyRouteModeId, payload: dict[str, Any]) -> bool:
    return not legacy_split_payload_issues(mode, payload)


def legacy_split_payload_schema_example(mode: TemporaryLegacyRouteModeId) -> dict[str, Any]:
    if mode == "walking_skeleton":
        return _ws_generation_schema()
    if mode == "slice":
        return _slice_generation_schema()
    raise ValueError(f"Unsupported split mode: {mode}")


def legacy_split_payload_issues(mode: TemporaryLegacyRouteModeId, payload: dict[str, Any]) -> list[str]:
    if mode == "walking_skeleton":
        epics = payload.get("epics")
        if not isinstance(epics, list):
            return ["payload.epics must be a list"]
        if not 1 <= len(epics) <= 3:
            return ["payload.epics must contain 1 to 3 items"]
        issues: list[str] = []
        for epic_index, epic in enumerate(epics, start=1):
            if not isinstance(epic, dict):
                issues.append(f"payload.epics[{epic_index - 1}] must be an object")
                continue
            if not _normalize_text(epic.get("title")):
                issues.append(f"payload.epics[{epic_index - 1}].title is required")
            if not _normalize_text(epic.get("prompt")):
                issues.append(f"payload.epics[{epic_index - 1}].prompt is required")
            phases = epic.get("phases")
            if not isinstance(phases, list):
                issues.append(f"payload.epics[{epic_index - 1}].phases must be a list")
                continue
            if not 2 <= len(phases) <= 5:
                issues.append(f"payload.epics[{epic_index - 1}].phases must contain 2 to 5 items")
                continue
            for phase_index, phase in enumerate(phases, start=1):
                if not isinstance(phase, dict):
                    issues.append(
                        f"payload.epics[{epic_index - 1}].phases[{phase_index - 1}] must be an object"
                    )
                    continue
                if not _normalize_text(phase.get("prompt")):
                    issues.append(
                        f"payload.epics[{epic_index - 1}].phases[{phase_index - 1}].prompt is required"
                    )
        return issues

    if mode == "slice":
        subtasks = payload.get("subtasks")
        if not isinstance(subtasks, list):
            return ["payload.subtasks must be a list"]
        if not 2 <= len(subtasks) <= 10:
            return ["payload.subtasks must contain 2 to 10 items"]
        issues = []
        for index, subtask in enumerate(subtasks, start=1):
            if not isinstance(subtask, dict):
                issues.append(f"payload.subtasks[{index - 1}] must be an object")
                continue
            if not _normalize_text(subtask.get("prompt")):
                issues.append(f"payload.subtasks[{index - 1}].prompt is required")
        return issues

    return [f"Unsupported split mode: {mode}"]


def build_legacy_hidden_retry_feedback(mode: TemporaryLegacyRouteModeId, issues: list[str]) -> str:
    issue_lines = issues or ["No valid emit_render_data(kind='split_result', payload=...) tool call was captured."]
    schema = json.dumps(legacy_split_payload_schema_example(mode), indent=2, ensure_ascii=True)
    issue_block = "\n".join(f"- {issue}" for issue in issue_lines)
    return "\n".join(
        [
            f"The previous {mode} split attempt did not produce a valid split_result payload.",
            "Fix the structured payload and call emit_render_data before writing your summary.",
            "Validation issues:",
            issue_block,
            "Required payload example:",
            schema,
        ]
    )


def _ws_generation_schema() -> dict[str, Any]:
    return {
        "epics": [
            {
                "title": "Epic title",
                "prompt": "What this epic achieves",
                "phases": [
                    {
                        "prompt": "Phase task",
                        "definition_of_done": "Done condition",
                    }
                ],
            }
        ]
    }


def _slice_generation_schema() -> dict[str, Any]:
    return {
        "subtasks": [
            {
                "order": 1,
                "prompt": "Subtask prompt",
                "risk_reason": "Optional risk",
                "what_unblocks": "Optional dependency or unblocker",
            }
        ]
    }


def _legacy_strictness_instructions(strictness: str) -> str:
    if strictness == "standard":
        return (
            "Keep the decomposition concrete and concise. Respect the item-count limits and return JSON only."
        )
    if strictness == "guided":
        return (
            "Use the exact required keys, stay within the allowed counts, and make every prompt actionable. Return JSON only."
        )
    return (
        "Output ONLY a valid JSON object with the exact top-level keys shown in the schema. No prose, no code fences, no extra keys."
    )


def _parse_ws_generation_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw_epics = payload.get("epics")
    if not isinstance(raw_epics, list):
        return None

    epics: list[dict[str, Any]] = []
    for raw_epic in raw_epics:
        if not isinstance(raw_epic, dict):
            return None
        epics.append(
            {
                "title": _normalize_text(raw_epic.get("title")),
                "prompt": _normalize_text(
                    raw_epic.get("prompt")
                    or raw_epic.get("description")
                    or raw_epic.get("summary")
                ),
                "phases": _normalize_ws_phase_collection(raw_epic.get("phases")),
            }
        )

    return {"epics": epics}


def _normalize_ws_phase_collection(raw_phases: Any) -> list[dict[str, str]]:
    if isinstance(raw_phases, list):
        phase_items = raw_phases
    elif isinstance(raw_phases, dict):
        ordered_keys = list(raw_phases.keys())
        if all(isinstance(key, str) and key.upper() in _PHASE_KEYS for key in ordered_keys):
            ordered_keys = sorted(ordered_keys, key=lambda key: _PHASE_KEYS.index(str(key).upper()))
        phase_items = [raw_phases[key] for key in ordered_keys]
    else:
        return []

    phases: list[dict[str, str]] = []
    for index, phase_item in enumerate(phase_items[: len(_PHASE_KEYS)]):
        prompt = ""
        definition_of_done = ""
        if isinstance(phase_item, str):
            prompt = _normalize_text(phase_item)
        elif isinstance(phase_item, dict):
            prompt = _normalize_text(
                phase_item.get("prompt")
                or phase_item.get("task")
                or phase_item.get("title")
            )
            definition_of_done = _normalize_text(
                phase_item.get("definition_of_done")
                or phase_item.get("done")
                or phase_item.get("definition")
            )
        phases.append(
            {
                "phase_key": _PHASE_KEYS[index],
                "prompt": prompt,
                "definition_of_done": definition_of_done,
            }
        )

    return phases


def _parse_slice_generation_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw_subtasks = payload.get("subtasks")
    if not isinstance(raw_subtasks, list):
        return None

    subtasks = [item for item in raw_subtasks if isinstance(item, (dict, str))]
    provided_orders = [item.get("order") for item in subtasks if isinstance(item, dict)]
    valid_ordering = (
        len(provided_orders) == len(subtasks)
        and len(set(provided_orders)) == len(subtasks)
        and all(isinstance(order, int) and 1 <= order <= len(subtasks) for order in provided_orders)
    )
    if valid_ordering:
        subtasks = sorted(subtasks, key=lambda item: int(item["order"]))  # type: ignore[index]

    normalized: list[dict[str, Any]] = []
    for index, raw_subtask in enumerate(subtasks, start=1):
        if isinstance(raw_subtask, str):
            prompt = _normalize_text(raw_subtask)
            risk_reason = ""
            what_unblocks = ""
        else:
            prompt = _normalize_text(
                raw_subtask.get("prompt")
                or raw_subtask.get("title")
                or raw_subtask.get("task")
            )
            risk_reason = _normalize_text(raw_subtask.get("risk_reason"))
            what_unblocks = _normalize_text(raw_subtask.get("what_unblocks"))
        normalized.append(
            {
                "order": index,
                "prompt": prompt,
                "risk_reason": risk_reason,
                "what_unblocks": what_unblocks,
            }
        )

    return {"subtasks": normalized}


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())
