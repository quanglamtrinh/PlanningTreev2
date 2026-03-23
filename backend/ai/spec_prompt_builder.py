from __future__ import annotations

import json
import re
from typing import Any


_SYSTEM_PROMPT = """\
You are a technical specification writer for the PlanningTree project planning tool.

Your job is to generate a technical implementation spec from a confirmed frame document.
The frame document contains all task-shaping decisions (from clarify rounds) already
embedded in its Task-Shaping Fields section — you do not need to ask any questions.

The spec is a concrete technical proposal that explains HOW to implement the task
described in the frame. It is NOT a copy of the frame.

Spec sections (generate all that apply):
1. **Overview** — 2-3 sentence summary of what this spec proposes.
2. **Architecture Decisions** — Key technical choices and their rationale.
3. **Implementation Plan** — Ordered steps to implement the task.
4. **Data Model** — Any data structures, schemas, or storage changes.
5. **API / Interface** — Endpoints, function signatures, or UI components.
6. **Edge Cases** — Error handling, boundary conditions, failure modes.
7. **Testing Strategy** — What to test and how.

Rules:
1. Read the frame document carefully. All shaping fields are already resolved.
2. Be specific and actionable — avoid vague "consider doing X" language.
3. Reference specific technologies, patterns, or libraries when appropriate.
4. Keep the spec concise — aim for 200-500 words total.
5. Use markdown formatting with headers for each section.
6. Call emit_spec_content exactly once with the full spec as a markdown string.
7. After the tool call, write a brief summary (do not repeat the spec).
"""

_FRAME_CHAR_LIMIT = 6000
_CONTEXT_CHAR_LIMIT = 2000


def spec_render_tool() -> dict[str, Any]:
    return {
        "name": "emit_spec_content",
        "description": (
            "Emit the generated technical spec for the app to store. "
            "Call this exactly once with the full spec as a markdown string. "
            "Do not duplicate the spec in plain text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The full technical spec in markdown format.",
                },
            },
            "required": ["content"],
        },
    }


def build_spec_base_instructions() -> str:
    return _SYSTEM_PROMPT


def build_spec_generation_prompt(
    frame_content: str,
    task_context: dict[str, Any],
) -> str:
    sections: list[str] = []

    sections.append(_format_task_context(task_context))
    sections.append(_format_frame_content(frame_content))

    sections.append(
        "Generate a technical implementation spec for this task now. "
        "Call emit_spec_content with the full spec as markdown."
    )

    return "\n\n".join(s for s in sections if s.strip())


def extract_spec_content(tool_calls: Any) -> str | None:
    if not isinstance(tool_calls, list):
        return None
    for raw_call in tool_calls:
        if not isinstance(raw_call, dict):
            continue
        if str(raw_call.get("tool_name") or "") != "emit_spec_content":
            continue
        arguments = raw_call.get("arguments")
        if not isinstance(arguments, dict):
            continue
        content = arguments.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def extract_spec_content_from_text(stdout: str) -> str | None:
    """Fallback: try to extract spec content from stdout."""
    text = stdout.strip()
    if not text:
        return None
    # If stdout looks like markdown with headers, use it directly
    if re.search(r"^#{1,3}\s+", text, re.MULTILINE):
        return text
    # Try to find JSON with content field
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict) and isinstance(parsed.get("content"), str):
                return parsed["content"].strip() or None
        except (json.JSONDecodeError, ValueError):
            pass
    return None


# ── Internal helpers ────────────────────────────────────────────


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
