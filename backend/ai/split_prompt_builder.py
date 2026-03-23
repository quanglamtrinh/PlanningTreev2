from __future__ import annotations

import json
from typing import Any

from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY, CanonicalSplitModeId

_REQUIRED_TOP_LEVEL_KEYS = {"subtasks"}
_REQUIRED_SUBTASK_KEYS = {"id", "title", "objective", "why_now"}

_MODE_PROMPT_BODIES: dict[CanonicalSplitModeId, str] = {
    "workflow": """
You are a decomposition agent working inside an existing repository.

Task:
Split a parent task into a small set of sequential workflow-based subtasks.

Goal:
Produce a workflow-first split that is easy for the user to review and easy for the next step to execute as child nodes.

Important:
- The source input is a parent task.
- If a task frame is provided, treat it as supporting task-shaping context and honor its decisions when they are relevant.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task or repository context.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Rules:
1. Split by workflow or outcome first, not by technical layers.
2. Keep subtasks sequential and dependency-aware.
3. Prefer the golden path first.
4. Keep the number of subtasks small but sufficient.
5. Each subtask must have one clear outcome and one clear boundary.
6. Do not split into tiny implementation chores.
7. Do not merge unrelated workflows into one subtask.
8. Do not restate the parent task as a single broad subtask.
9. If the task is underspecified, prefer reversible and low-risk workflow boundaries.
10. If the task frame fixes relevant choices, reflect those choices concretely in affected subtasks instead of generic wording.
""".strip(),
    "simplify_workflow": """
You are a decomposition agent working inside an existing repository.

Task:
Simplify a parent task into a sequential set of child subtasks.

Goal:
Identify the smallest core workflow that still proves the task is real, then add the remaining parts back step by step.

Important:
- The source input is a parent task.
- If a task frame is provided, treat it as supporting task-shaping context and honor its decisions when they are relevant.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task or repository context.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Rules:
1. Preserve the parent task's real product meaning.
2. Find the smallest version of the task that still validates the core outcome.
3. Add deferred parts back in a dependency-aware sequence.
4. Keep the number of subtasks small but sufficient.
5. Each subtask must have one clear outcome and one clear boundary.
6. Do not split into tiny implementation chores.
7. Do not split by technical layers unless simplification cannot be expressed as workflow steps.
8. Do not restate the parent task as a single broad subtask.
9. If the task is underspecified, prefer reversible and low-risk simplifications.
10. If the task frame fixes relevant choices, reflect those choices concretely in affected subtasks instead of generic wording.
""".strip(),
    "phase_breakdown": """
You are a decomposition agent working inside an existing repository.

Task:
Break a parent task into a small set of sequential implementation phases.

Goal:
Produce a phase-based split that is easy for the user to review and easy for the next step to execute as child nodes.

Important:
- The source input is a parent task.
- If a task frame is provided, treat it as supporting task-shaping context and honor its decisions when they are relevant.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task or repository context.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Rules:
1. Split by delivery phase, not by technical layer.
2. Use the fewest phases that still meaningfully reduce risk and improve execution clarity.
3. Phase 1 must prove the target shape with the lowest reasonable blast radius.
4. Later phases add realism and harden behavior in dependency order.
5. Keep phases sequential and dependency-aware.
6. Each phase must have one clear purpose and one clear boundary.
7. Do not split into tiny implementation chores.
8. Do not restate the parent task as a single broad phase.
9. If the task is underspecified, prefer reversible and low-risk early phases.
10. If the task frame fixes relevant choices, reflect those choices concretely in affected phases instead of generic wording.
""".strip(),
    "agent_breakdown": """
You are a decomposition agent working inside an existing repository.

Task:
Break a parent task into the best sequential child subtasks when workflow or phase breakdown are weak fits.

Goal:
Produce the best agent-driven breakdown for downstream child-node execution.

Important:
- The source input is a parent task.
- If a task frame is provided, treat it as supporting task-shaping context and honor its decisions when they are relevant.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task or repository context.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Rules:
1. Use the most natural decomposition shape for this task.
2. Prefer decomposition by stable boundary, dependency unlock, risk reduction, migration cutline, or cleanup isolation.
3. Keep subtasks sequential and dependency-aware.
4. Keep the number of subtasks small but sufficient.
5. Each subtask must have one clear objective and one clear boundary.
6. Do not default to frontend/backend/database split unless that is the only clean ownership boundary.
7. Do not split into tiny implementation chores.
8. Do not restate the parent task as a single broad subtask.
9. If the task is underspecified, prefer conservative and reversible boundaries.
10. If the task frame fixes relevant choices, reflect those choices concretely in affected subtasks instead of generic wording.
""".strip(),
}


def split_render_tool() -> dict[str, Any]:
    return {
        "name": "emit_render_data",
        "description": (
            "Send structured payload for the app UI to render. "
            "For split turns, call this before writing your summary message. "
            "Do not duplicate the structured payload in plain text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["split_result"]},
                "payload": {"type": "object"},
            },
            "required": ["kind", "payload"],
        },
    }


def build_split_base_instructions(mode: CanonicalSplitModeId | None = None) -> str:
    lines = [
        "You are the PlanningTree split assistant.",
        "For split turns, produce structured UI data with emit_render_data(kind='split_result', payload=...).",
        "The split payload must use exactly one top-level key: subtasks.",
        "Each subtask item must use exactly: id, title, objective, why_now.",
        "If a task frame is provided, treat its shaping decisions as constraints for relevant subtasks.",
        "If you can produce a valid split, call emit_render_data before writing a short summary for the user.",
        "Do not duplicate the structured payload in the summary text.",
    ]
    if mode is not None:
        lines.append(f"The active split mode for this turn is {mode}.")
    return "\n".join(lines)


def build_split_attempt_prompt(
    mode: CanonicalSplitModeId,
    task_context: dict[str, Any],
    retry_feedback: str | None = None,
) -> str:
    _canonical_mode_spec_or_raise(mode)
    prompt_sections: list[str] = []
    if retry_feedback:
        prompt_sections.append(retry_feedback.strip())
    prompt_sections.extend(
        [
            _MODE_PROMPT_BODIES[mode],
            _format_runtime_context_block(task_context),
            _structured_output_contract(mode),
        ]
    )
    return "\n\n".join(section for section in prompt_sections if section.strip())


def build_hidden_retry_feedback(mode: CanonicalSplitModeId, issues: list[str]) -> str:
    _canonical_mode_spec_or_raise(mode)
    issue_lines = issues or ["No valid emit_render_data(kind='split_result', payload=...) tool call was captured."]
    issue_block = "\n".join(f"- {issue}" for issue in issue_lines)
    return "\n".join(
        [
            f"Retry: your previous {mode} split output was invalid.",
            "Validation issues:",
            issue_block,
            "Produce a corrected split using the same task, repository context, and output contract below.",
        ]
    )


def validate_split_payload(mode: CanonicalSplitModeId, payload: dict[str, Any]) -> bool:
    return not split_payload_issues(mode, payload)


def split_payload_issues(mode: CanonicalSplitModeId, payload: dict[str, Any]) -> list[str]:
    _canonical_mode_spec_or_raise(mode)
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

    if not raw_subtasks:
        issues.append("payload.subtasks must contain at least one item")
        return issues

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
        for field in ("id", "title", "objective", "why_now"):
            if field not in subtask:
                continue
            normalized_value = _normalize_text(subtask.get(field))
            if not normalized_value:
                issues.append(f"payload.subtasks[{index}].{field} must be a non-empty string")
                continue
            if field == "id":
                normalized_id = normalized_value

        if normalized_id and normalized_id != f"S{index + 1}":
            issues.append(f"payload.subtasks[{index}].id must be 'S{index + 1}'")

    return issues


def _canonical_mode_spec_or_raise(mode: CanonicalSplitModeId | str) -> dict[str, Any]:
    spec = CANONICAL_SPLIT_MODE_REGISTRY.get(mode)  # type: ignore[arg-type]
    if spec is None:
        raise ValueError(f"Unsupported split mode: {mode}")
    return spec


def _format_runtime_context_block(task_context: dict[str, Any]) -> str:
    lines = [
        "Runtime context:",
        f"- Parent task: {_context_value(task_context.get('current_node_prompt'))}",
    ]

    frame_content = (task_context.get("frame_content") or "").strip()
    if frame_content:
        truncated = frame_content[:4000]
        if len(frame_content) > 4000:
            truncated += "\n... (truncated)"
        lines.append(f"- Task frame:\n{truncated}")

    lines.append(f"- Root goal: {_context_value(task_context.get('root_prompt'))}")

    parent_chain = task_context.get("parent_chain_prompts")
    if isinstance(parent_chain, list) and parent_chain:
        lines.append("- Parent chain:")
        for item in parent_chain:
            normalized = _normalize_text(item)
            if normalized:
                lines.append(f"  - {normalized}")
    else:
        lines.append("- Parent chain: none")

    sibling_context = task_context.get("prior_node_summaries_compact")
    if isinstance(sibling_context, list) and sibling_context:
        lines.append("- Completed sibling context:")
        for item in sibling_context:
            if not isinstance(item, dict):
                continue
            title = _normalize_text(item.get("title"))
            description = _normalize_text(item.get("description"))
            summary = f"{title}: {description}" if title and description else title or description
            if summary:
                lines.append(f"  - {summary}")
    else:
        lines.append("- Completed sibling context: none")

    if task_context.get("parent_chain_truncated"):
        lines.append("- Parent chain note: lineage was truncated for prompt compactness.")

    return "\n".join(lines)


def _structured_output_contract(mode: CanonicalSplitModeId) -> str:
    spec = _canonical_mode_spec_or_raise(mode)
    schema = json.dumps(_shared_schema_example(), indent=2, ensure_ascii=True)
    return "\n".join(
        [
            "Output contract:",
            "- First call emit_render_data(kind='split_result', payload=...).",
            "- The payload must be valid JSON in this exact shape:",
            schema,
            "Hard output rules:",
            "- The payload must contain exactly one top-level key: \"subtasks\".",
            f"- \"subtasks\" should usually contain {spec['min_items']} to {spec['max_items']} items unless the parent task clearly requires fewer or more.",
            "- Each subtask object must contain exactly these 4 keys and no others: id, title, objective, why_now.",
            "- \"id\" must use sequential values: \"S1\", \"S2\", \"S3\", ...",
            "- \"title\" must be short, concrete, and user-readable.",
            "- \"objective\" must be exactly 1 sentence focused on the outcome of that subtask.",
            "- \"why_now\" must explain why this subtask belongs at this point in the sequence.",
            "- \"why_now\" must not simply restate the objective.",
            "- If a task frame is provided, its shaping decisions are constraints for any relevant subtask.",
            "- When the frame fixes a stack, platform, UX boundary, or similar steering choice, reflect that choice concretely instead of writing a generic subtask.",
            "- Subtasks must be sequential, non-overlapping, and suitable for child-node creation.",
            "- Do not include implementation details, architecture plans, code suggestions, clarification questions, assumptions lists, done criteria, scope breakdown, rationale bullets, or internal notes.",
            "- After the tool call, write a brief user-facing summary without repeating the payload.",
        ]
    )


def _shared_schema_example() -> dict[str, Any]:
    return {
        "subtasks": [
            {
                "id": "S1",
                "title": "Subtask title",
                "objective": "What this step achieves.",
                "why_now": "Why this should happen now.",
            }
        ]
    }


def _context_value(value: Any) -> str:
    normalized = _normalize_text(value)
    return normalized or "none"


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())
