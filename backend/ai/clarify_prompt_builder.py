from __future__ import annotations

import json
from typing import Any


_SYSTEM_PROMPT = """\
You are a task-clarification assistant for the PlanningTree project planning tool.

Your job is to generate clarifying questions for a task node based on its confirmed
frame document. These questions help the user resolve ambiguities and missing
information before writing a detailed specification.

Rules:
1. Read the frame document carefully. Identify areas where information is missing,
   ambiguous, or where a decision is needed before implementation can begin.
2. Generate 3-8 focused questions. Each question should target a specific aspect
   that would affect the spec or implementation.
3. Use the Task-Shaping Fields section as a starting point — any field with an empty
   value should get a question. But also generate questions about other ambiguities.
4. Each question needs a unique field_name (snake_case, descriptive key) and a
   clear question text.
5. Do not ask about things that are already resolved in the frame.
6. Do not ask generic questions — each question should be specific to this task.
7. Output the questions by calling emit_clarify_questions with the full list.
8. After the tool call, write a brief summary for the user (do not repeat the questions).
"""

_FRAME_CHAR_LIMIT = 6000
_CONTEXT_CHAR_LIMIT = 2000


def clarify_render_tool() -> dict[str, Any]:
    return {
        "name": "emit_clarify_questions",
        "description": (
            "Emit the generated clarifying questions for the app to store. "
            "Call this exactly once with the full list of questions. "
            "Do not duplicate the questions in plain text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "List of clarifying questions for the task.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_name": {
                                "type": "string",
                                "description": (
                                    "A unique snake_case key for this question "
                                    "(e.g. 'auth_provider', 'error_handling_strategy')."
                                ),
                            },
                            "question": {
                                "type": "string",
                                "description": "The clarifying question to ask the user.",
                            },
                        },
                        "required": ["field_name", "question"],
                    },
                },
            },
            "required": ["questions"],
        },
    }


def build_clarify_base_instructions() -> str:
    return _SYSTEM_PROMPT


def build_clarify_generation_prompt(
    frame_content: str,
    task_context: dict[str, Any],
) -> str:
    sections: list[str] = []

    sections.append(_format_task_context(task_context))
    sections.append(_format_frame_content(frame_content))

    sections.append(
        "Generate clarifying questions for this task now. "
        "Call emit_clarify_questions with the full list of questions."
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
        if isinstance(questions, list) and len(questions) > 0:
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
            if isinstance(parsed, list) and len(parsed) > 0:
                return _normalize_questions(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


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
        result.append({
            "field_name": field_name,
            "question": question,
            "answer": "",
            "resolution_status": "open",
        })
    return result if result else []


def _format_frame_content(frame_content: str) -> str:
    content = frame_content.strip()
    if not content:
        return "Frame document: (empty)"
    if len(content) > _FRAME_CHAR_LIMIT:
        content = content[:_FRAME_CHAR_LIMIT - 3] + "..."
    return f"Confirmed frame document:\n\n{content}"


def _format_task_context(task_context: dict[str, Any]) -> str:
    lines = ["Task context:"]

    current = _normalize_text(task_context.get("current_node_prompt"))
    if current:
        lines.append(f"- Current task: {_truncate(current, 500)}")

    root = _normalize_text(task_context.get("root_prompt"))
    if root:
        lines.append(f"- Root goal: {_truncate(root, 300)}")

    parent_chain = task_context.get("parent_chain_prompts")
    if isinstance(parent_chain, list) and parent_chain:
        lines.append("- Parent chain:")
        for item in parent_chain:
            normalized = _normalize_text(item)
            if normalized:
                lines.append(f"  - {_truncate(normalized, 300)}")

    return "\n".join(lines)


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
