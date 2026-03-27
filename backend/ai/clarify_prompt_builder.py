from __future__ import annotations

import json
import re
from typing import Any

from backend.ai.prompt_helpers import (
    format_frame_content,
    normalize_text,
    strip_json_fence,
    truncate,
)


_SYSTEM_PROMPT = """\
You are a task-clarification assistant for the PlanningTree project planning tool.

Your job is to generate clarifying questions ONLY for unresolved task-shaping fields
in a confirmed frame document. Task-shaping fields are steering-level decisions that
affect implementation scope, approach, or constraints.

For each question you MUST provide 2-4 concrete options the user can choose from.

Rules:
1. Read the frame document carefully. Focus on the "Task-Shaping Fields" section.
2. For each field that has NO value or an EMPTY value — generate one question asking
   the user to resolve it. The field_name must match the field name from the frame.
3. For each field that ALREADY has a value — skip it. It is already resolved.
4. Do NOT invent new questions beyond the task-shaping fields in the frame. Only
   unresolved steering-level fields become clarify questions.
5. If ALL task-shaping fields are already resolved, call emit_clarify_questions
   with an empty list.
6. Do not ask generic questions — each question must target a specific unresolved
   task-shaping field from this frame.

Per-question requirements:
- Provide 2-4 concrete options. Each option must have: id, label, value, rationale, recommended.
- The `id` field must be the snake_case form of `value` (e.g., value "Mobile Web" → id "mobile_web").
- Exactly 1 option per question must have `recommended: true`.
- Include `why_it_matters` explaining the steering significance of this field.
- Include `current_value` with what the frame currently says (empty string if unresolved).
- Set `allow_custom: true` for all questions.

Output:
7. Call emit_clarify_questions with the full list of questions.
8. After the tool call, write a brief summary for the user (do not repeat the questions).
"""

_GENERATION_ROLE_PREFIX = """\
You are a task-clarification assistant for the PlanningTree project planning tool.

Your job is to generate clarifying questions ONLY for unresolved task-shaping fields
in a confirmed frame document. Task-shaping fields are steering-level decisions that
affect implementation scope, approach, or constraints.

For each question you MUST provide 2-4 concrete options the user can choose from.

Rules:
1. Read the frame document carefully. Focus on the "Task-Shaping Fields" section.
2. For each field that has NO value or an EMPTY value — generate one question asking
   the user to resolve it. The field_name must match the field name from the frame.
3. For each field that ALREADY has a value — skip it. It is already resolved.
4. Do NOT invent new questions beyond the task-shaping fields in the frame. Only
   unresolved steering-level fields become clarify questions.
5. If ALL task-shaping fields are already resolved, return {"questions": []} as the
   structured output.
6. Do not ask generic questions — each question must target a specific unresolved
   task-shaping field from this frame.

Per-question requirements:
- Provide 2-4 concrete options. Each option must have: id, label, value, rationale, recommended.
- The `id` field must be the snake_case form of `value` (e.g., value "Mobile Web" → id "mobile_web").
- Exactly 1 option per question must have `recommended: true`.
- Include `why_it_matters` explaining the steering significance of this field.
- Include `current_value` with what the frame currently says (empty string if unresolved).
- Set `allow_custom: true` for all questions.
"""

_FRAME_CHAR_LIMIT = 6000
_CONTEXT_CHAR_LIMIT = 2000


def build_clarify_generation_role_prefix() -> str:
    return _GENERATION_ROLE_PREFIX


def build_clarify_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["questions"],
        "properties": {
            "questions": {
                "type": "array",
                "description": "List of clarifying questions for the task.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field_name": {
                            "type": "string",
                            "description": (
                                "The exact field name from the frame's Task-Shaping Fields section "
                                "(e.g. 'target platform', 'auth provider'). Must match verbatim."
                            ),
                        },
                        "question": {
                            "type": "string",
                            "description": "The clarifying question to ask the user.",
                        },
                        "why_it_matters": {
                            "type": "string",
                            "description": "Why this field affects steering.",
                        },
                        "current_value": {
                            "type": "string",
                            "description": "Value from frame (empty if unresolved).",
                        },
                        "options": {
                            "type": "array",
                            "description": "2-4 concrete options for the user.",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "id": {
                                        "type": "string",
                                        "description": "snake_case of value.",
                                    },
                                    "label": {
                                        "type": "string",
                                        "description": "Short display label.",
                                    },
                                    "value": {
                                        "type": "string",
                                        "description": "Concrete value this option represents.",
                                    },
                                    "rationale": {
                                        "type": "string",
                                        "description": "Why this option makes sense.",
                                    },
                                    "recommended": {
                                        "type": "boolean",
                                        "description": "True for exactly one option per question.",
                                    },
                                },
                                "required": ["id", "label", "value", "rationale", "recommended"],
                            },
                        },
                        "allow_custom": {
                            "type": "boolean",
                            "description": "Whether custom freeform answer is allowed.",
                        },
                    },
                    "required": [
                        "field_name",
                        "question",
                        "why_it_matters",
                        "current_value",
                        "options",
                        "allow_custom",
                    ],
                },
            },
        },
    }


def build_clarify_generation_prompt(
    frame_content: str,
    task_context: dict[str, Any],
    *,
    role_prefix: str | None = None,
) -> str:
    sections: list[str] = []

    if role_prefix:
        sections.append(role_prefix)

    sections.append(_format_task_context(task_context))
    sections.append(_format_frame_content(frame_content))

    sections.append(
        "Generate clarifying questions for this task now. "
        "Respond with the questions as structured JSON output."
    )

    return "\n\n".join(s for s in sections if s.strip())


def extract_clarify_questions(tool_calls: Any) -> list[dict[str, Any]] | None:
    if not isinstance(tool_calls, list):
        return None
    for raw_call in tool_calls:
        if not isinstance(raw_call, dict):
            continue
        if str(raw_call.get("tool_name") or "") != "emit_clarify_questions":
            continue
        arguments = raw_call.get("arguments")
        if not isinstance(arguments, dict):
            continue
        questions = arguments.get("questions")
        if isinstance(questions, list):
            return _normalize_questions(questions)
    return None


def extract_clarify_questions_from_structured_output(
    stdout: str,
) -> list[dict[str, Any]] | None:
    """Parse structured JSON output for clarify questions.

    Returns [] (not None) when the model returns {"questions": []},
    which is a valid success case (all fields resolved → auto-confirm).
    """
    text = strip_json_fence(stdout)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(parsed, dict):
        questions = parsed.get("questions")
        if isinstance(questions, list):
            return _normalize_questions(questions)
    return None


def extract_clarify_questions_from_text(stdout: str) -> list[dict[str, Any]] | None:
    """Fallback: try to parse questions from stdout JSON."""
    text = stdout.strip()
    if not text:
        return None
    # Try to find a JSON array
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, list):
                return _normalize_questions(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# ── Normalization helpers ────────────────────────────────────────────


def _to_snake_case(text: str) -> str:
    """Convert text to snake_case for stable option IDs."""
    s = text.strip()
    # Replace non-alphanumeric with spaces, collapse, then join with _
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip()
    # Insert space before uppercase letters that follow lowercase
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return "_".join(s.lower().split())


def _normalize_options(raw_options: list[Any]) -> list[dict[str, Any]]:
    """Validate and normalize option objects from AI output.

    Enforces stable IDs by overwriting id = _to_snake_case(value).
    """
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in raw_options:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        if not value or not label:
            continue
        # Derive stable ID from value
        option_id = _to_snake_case(value)
        if not option_id or option_id in seen_ids:
            continue
        seen_ids.add(option_id)
        result.append({
            "id": option_id,
            "label": label,
            "value": value,
            "rationale": str(item.get("rationale") or "").strip(),
            "recommended": bool(item.get("recommended")),
        })
    # Ensure exactly one recommended
    recommended_count = sum(1 for o in result if o["recommended"])
    if recommended_count == 0 and result:
        result[0]["recommended"] = True
    elif recommended_count > 1:
        found_first = False
        for o in result:
            if o["recommended"]:
                if found_first:
                    o["recommended"] = False
                else:
                    found_first = True
    return result


def _normalize_questions(raw_questions: list[Any]) -> list[dict[str, Any]]:
    """Validate and normalize question objects from AI output."""
    result: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field_name") or "").strip()
        question = str(item.get("question") or "").strip()
        if not field_name or not question:
            continue
        # Deduplicate
        if field_name in seen_fields:
            continue
        seen_fields.add(field_name)
        raw_opts = item.get("options")
        options = _normalize_options(raw_opts) if isinstance(raw_opts, list) else []
        result.append({
            "field_name": field_name,
            "question": question,
            "why_it_matters": str(item.get("why_it_matters") or "").strip(),
            "current_value": str(item.get("current_value") or "").strip(),
            "options": options,
            "selected_option_id": None,
            "custom_answer": "",
            "allow_custom": True,
        })
    return result if result else []


def _format_frame_content(frame_content: str) -> str:
    return format_frame_content(frame_content, _FRAME_CHAR_LIMIT)


def _format_task_context(task_context: dict[str, Any]) -> str:
    lines = ["Task context:"]

    current = normalize_text(task_context.get("current_node_prompt"))
    if current:
        lines.append(f"- Current task: {truncate(current, 500)}")

    root = normalize_text(task_context.get("root_prompt"))
    if root:
        lines.append(f"- Root goal: {truncate(root, 300)}")

    parent_chain = task_context.get("parent_chain_prompts")
    if isinstance(parent_chain, list) and parent_chain:
        lines.append("- Parent chain:")
        for item in parent_chain:
            normalized = normalize_text(item)
            if normalized:
                lines.append(f"  - {truncate(normalized, 300)}")

    return "\n".join(lines)
