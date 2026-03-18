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
Produce a workflow-first split that is easy for the user to review and easy for the next step to turn into a child spec.

Important:
- The source input is a parent task, not a parent spec.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task, repository context, or locked constraints.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Context:
- The parent task, repository context, and locked constraints are the source of truth.
- Follow the repository's existing conventions and structure.
- Respect constraints already present in AGENTS.md and local repo guidance.
- Because there is no parent spec yet, prefer conservative boundaries and low-blast-radius sequencing.

Rules:
1. Split by workflow or outcome first, not by technical layers.
2. Keep subtasks sequential and dependency-aware.
3. Prefer the golden path first.
4. Keep the number of subtasks small but sufficient.
5. Each subtask must have one clear outcome and one clear boundary.
6. Do not split into tiny implementation chores.
7. Do not merge unrelated workflows into one subtask.
8. Defer local implementation details to the future child spec.
9. Preserve all locked requirements.
10. Each subtask must be specific enough for a child spec to be created next.
11. Do not restate the parent task as a single broad subtask.
12. If workflow split is a weak fit, still produce the best possible workflow-first split without asking questions.
13. If the parent task is underspecified, prefer reversible and low-risk workflow boundaries rather than guessing hidden product decisions.

Good subtask:
- a meaningful user-visible, operator-visible, or system-validating outcome
- narrow enough to stand on its own
- clearly placed in sequence
- ready for child-spec creation

Avoid:
- frontend/backend/database split unless workflow split is clearly impossible
- vague buckets like "core system", "polish", or "misc"
- tiny tasks like "create button", "add API route", or "write schema"
- implementation plans, code suggestions, or architecture rewrites
""".strip(),
    "simplify_workflow": """
You are a decomposition agent working inside an existing repository.

Task:
Simplify a parent task into a sequential set of child subtasks.

Goal:
Identify the smallest core workflow that still proves the task is real, then add the remaining parts back step by step in the best order for downstream child-spec creation.

Important:
- The source input is a parent task, not a parent spec.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task, repository context, or locked constraints.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Context:
- The parent task, repository context, and locked constraints are the source of truth.
- Follow the repository's existing conventions and structure.
- Respect constraints already present in AGENTS.md and local repo guidance.
- Because there is no parent spec yet, prefer conservative boundaries and low-blast-radius sequencing.

Rules:
1. Preserve the parent task's real product meaning.
2. Find the smallest version of the task that still validates the core outcome.
3. Remove supporting parts that are not required to prove the core workflow.
4. Add deferred parts back in a dependency-aware sequence.
5. Prefer earlier steps that unlock learning, validation, and future child specs.
6. Keep the number of subtasks small but sufficient.
7. Each subtask must have one clear outcome and one clear boundary.
8. Do not split into tiny implementation chores.
9. Do not split by technical layers unless simplification clearly cannot be expressed as workflow steps.
10. Defer local implementation details to the future child spec.
11. Preserve all locked requirements.
12. Do not restate the parent task as a single broad subtask.
13. If the parent task is underspecified, prefer reversible and low-risk simplifications rather than guessing hidden product decisions.

Definition of core workflow:
A core workflow is the smallest end-to-end version that still proves the essential user-visible or system-validating outcome of the parent task.
It must not remove something that changes the nature of the task.
It may temporarily omit supporting concerns such as auth, analytics, logging, admin controls, polish, resilience, or hardening if the task remains meaningfully valid without them.

Good subtask:
- a meaningful outcome, not a component
- specific enough for a child spec to be written next
- clearly placed in the additive sequence
- adds one coherent omitted part back into the workflow

Avoid:
- vague buckets like "core", "extras", or "polish"
- frontend/backend/database split unless necessary
- tiny chores like "add button", "create table", or "make endpoint"
- speculative future-proofing
- implementation plans or architecture rewrites
""".strip(),
    "phase_breakdown": """
You are a decomposition agent working inside an existing repository.

Task:
Break a parent task into a small set of sequential implementation phases.

Goal:
Produce a phase-based split that is easy for the user to review and easy for the next step to turn into a child spec.

Important:
- The source input is a parent task, not a parent spec.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task, repository context, or locked constraints.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Context:
- The parent task, repository context, and locked constraints are the source of truth.
- Follow the repository's existing conventions and structure.
- Respect constraints already present in AGENTS.md and local repo guidance.
- Because there is no parent spec yet, prefer conservative boundaries and low-blast-radius sequencing.

Rules:
1. Split by delivery phase, not by technical layer.
2. Use the fewest phases that still meaningfully reduce risk and improve execution clarity.
3. Phase 1 must prove the shape of the target workflow with the lowest reasonable blast radius.
4. Later phases must add realism, replace temporary paths, and harden behavior in dependency order.
5. Do not force a fixed template; use only the phases this parent task actually needs.
6. Prefer end-to-end validation earlier and deeper completeness later.
7. Keep phases sequential and dependency-aware.
8. Each phase must have one clear purpose and one clear boundary.
9. Do not split into tiny implementation chores.
10. Preserve all locked requirements.
11. Defer local implementation details to the future child spec.
12. Do not restate the parent task as a single broad phase.
13. If the parent task is underspecified, prefer reversible and low-risk early phases rather than guessing hidden product decisions.

Definition of a good phase:
A good phase is a coherent delivery checkpoint that changes the system's level of proof or realism.
Examples:
- establish a walking skeleton or controlled fake path
- replace fake or temporary paths with real integration
- harden correctness, resilience, validation, replay, recovery, or edge cases
A phase is not just a component bucket or a list of unrelated chores.

Avoid:
- frontend/backend/database split
- vague buckets like "core", "main work", or "cleanup"
- ultra-small tasks like "create API route", "add table", or "make button"
- forcing fake -> real -> harden if the parent task does not actually need all three
- architecture rewrites or speculative future-proofing
- implementation details that belong in the child spec
""".strip(),
    "agent_breakdown": """
You are a decomposition agent working inside an existing repository.

Task:
Break a parent task into the best sequential child subtasks when workflow split, simplify workflow split, or phase breakdown split are not the right fit.

Goal:
Produce the best agent-driven breakdown for downstream child-spec creation.

Important:
- The source input is a parent task.
- Do not ask clarification questions.
- Do not implement anything.
- Do not redesign the project.
- Do not invent requirements that are not grounded in the parent task, repository context, or locked constraints.
- Do not output internal reasoning.
- Return only the information the user needs to see.

Context:
- The parent task, repository context, and locked constraints are the source of truth.
- Follow the repository's existing conventions and structure.
- Respect constraints already present in AGENTS.md and local repo guidance.
- Prefer conservative boundaries and low-blast-radius sequencing.

Rules:
1. Use agent judgment to choose the most natural decomposition shape for this task.
2. Prefer decomposition by stable boundary, dependency unlock, risk reduction, invariant preservation, migration cutline, or cleanup isolation.
3. Do not force workflow phases or user-story framing when the task is fundamentally technical or cross-cutting.
4. Do not default to frontend/backend/database split unless that is the only clean ownership boundary.
5. Keep subtasks sequential and dependency-aware.
6. Keep the number of subtasks small but sufficient.
7. Each subtask must have one clear objective and one clear boundary.
8. Each subtask must reduce uncertainty, unlock later work, or isolate blast radius.
9. Preserve all locked requirements.
10. Defer local implementation details to the future child spec.
11. Explicitly prevent overlap between siblings.
12. If the parent task is underspecified, prefer reversible and low-risk child boundaries rather than guessing hidden product decisions.
13. Do not restate the parent task as a single broad subtask.

Allowed decomposition modes:
- boundary_first: split by stable module, interface, or ownership boundary
- dependency_unlock: split by prerequisite work that unlocks later work
- risk_first: split by highest-risk unknowns or failure points first
- invariant_first: split by contracts, correctness rules, or behavior invariants
- migration_cutline: split by compatibility boundary or cutover seam
- cleanup_isolation: split by safe removal, convergence, or closeout boundary
- custom: use only if none of the above fit cleanly

Mode selection rules:
- Choose exactly one primary mode internally.
- Choose the mode that creates the clearest child-spec boundaries with the lowest blast radius.
- Do not mix multiple primary modes unless absolutely necessary.
- If multiple modes seem possible, choose the one that best preserves clean sequencing and minimal overlap.

Good subtask:
- one clear technical or system-level purpose
- a stable ownership boundary
- specific enough for a child spec to be written next
- clearly placed in sequence
- grounded in the parent task and known repository context

Avoid:
- vague buckets like "main work", "infrastructure", "cleanup", or "misc"
- child tasks that are just implementation chores
- splitting one coherent change across many tiny tasks
- combining unrelated risks into one child
- architecture rewrites or speculative future-proofing
- pretending missing product decisions are already settled
""".strip(),
}

_MODE_SENTINEL_RULES: dict[CanonicalSplitModeId, str] = {
    "workflow": 'If the parent task is not sufficient for a valid workflow split, return the sentinel payload {"subtasks":[]}.',
    "simplify_workflow": 'If the task cannot be meaningfully simplified without breaking its nature, return the sentinel payload {"subtasks":[]}.',
    "phase_breakdown": 'If the parent task does not benefit from phase breakdown, return the sentinel payload {"subtasks":[]}.',
    "agent_breakdown": 'If a valid split cannot be made from the parent task, return the sentinel payload {"subtasks":[]}.',
}


def planning_render_tool() -> dict[str, Any]:
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
    lines = [
        "You are the PlanningTree planning assistant.",
        "For split turns, produce structured UI data with emit_render_data(kind='split_result', payload=...).",
        "The split payload must use exactly one top-level key: subtasks.",
        "Each subtask item must use exactly: id, title, objective, why_now.",
        "If you can produce a valid split, call emit_render_data before writing a short summary for the user.",
        "Do not duplicate the structured payload in the summary text.",
        "If the split cannot be made from the provided task and repository context, do not invent a generic fallback split.",
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


def split_payload_schema_example(mode: CanonicalSplitModeId) -> dict[str, Any]:
    _canonical_mode_spec_or_raise(mode)
    return _shared_schema_example()


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


def is_failure_sentinel_payload(mode: CanonicalSplitModeId, payload: dict[str, Any]) -> bool:
    _canonical_mode_spec_or_raise(mode)
    if not validate_split_payload(mode, payload):
        return False
    subtasks = payload.get("subtasks")
    return isinstance(subtasks, list) and len(subtasks) == 0


def _canonical_mode_spec_or_raise(mode: CanonicalSplitModeId | str) -> dict[str, Any]:
    spec = CANONICAL_SPLIT_MODE_REGISTRY.get(mode)  # type: ignore[arg-type]
    if spec is None:
        raise ValueError(f"Unsupported split mode: {mode}")
    return spec


def _format_runtime_context_block(task_context: dict[str, Any]) -> str:
    lines = [
        "Runtime context:",
        f"- Parent task: {_context_value(task_context.get('current_node_prompt'))}",
        f"- Root goal: {_context_value(task_context.get('root_prompt'))}",
    ]

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

    lines.extend(
        [
            "- Locked constraints and repo guidance:",
            "  - Respect AGENTS.md and local repo guidance.",
            "  - Follow existing repository conventions and structure.",
            "  - Preserve locked requirements already present in the parent task and inherited context.",
        ]
    )

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
            "- Subtasks must be sequential, non-overlapping, and suitable for downstream child-spec creation.",
            "- Do not include implementation details, architecture plans, code suggestions, clarification questions, assumptions lists, done criteria, scope breakdown, rationale bullets, or internal notes.",
            f"- {_MODE_SENTINEL_RULES[mode]}",
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
