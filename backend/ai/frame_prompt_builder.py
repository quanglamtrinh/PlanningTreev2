from __future__ import annotations

import json
from typing import Any

from backend.ai.prompt_helpers import normalize_text, strip_json_fence, truncate


_FRAME_SECTION_TEMPLATE = """\
# Task Title
{A short, concrete title for the task}

# User Story
{One sentence: As a <role>, I want <capability> so that <benefit>}

# Functional Requirements
{Bulleted list of concrete behaviors the implementation must support}

# Success Criteria
{Bulleted list of observable, testable outcomes}

# Out of Scope
{Bulleted list of what this task explicitly does NOT cover}

# Task-Shaping Fields
{Key-value pairs for decisions that steer the implementation.
 Resolved fields have a value. Unresolved fields are left blank.
 Example:
 - target platform: web
 - auth provider:
 - storage backend: SQLite}
"""

_SYSTEM_PROMPT = """\
You are a task-framing assistant for the PlanningTree project planning tool.

Your job is to generate a frame document (frame.md) for a task node.
The frame is a structured markdown document that captures the task's scope,
requirements, and shaping decisions.

Frame format:
""" + _FRAME_SECTION_TEMPLATE + """

Rules:
1. Derive the frame entirely from the conversation history and task context provided.
2. Do not invent requirements that are not grounded in the conversation or context.
3. Do not ask clarification questions — produce the best frame from available information.
4. Leave Task-Shaping Fields blank (no value after the colon) when the conversation
   does not provide enough information to decide.
5. Keep section content concise and actionable.
6. Output the frame by calling emit_frame_content with the full markdown string.
7. After the tool call, write a brief summary for the user (do not repeat the frame).
"""

_GENERATION_ROLE_PREFIX = """\
You are a task-framing assistant for the PlanningTree project planning tool.

Your job is to generate a frame document (frame.md) for a task node.
The frame is a structured markdown document that captures the task's scope,
requirements, and shaping decisions.

Frame format:
""" + _FRAME_SECTION_TEMPLATE + """

Rules:
1. Derive the frame entirely from the conversation history and task context provided.
2. Do not invent requirements that are not grounded in the conversation or context.
3. Do not ask clarification questions — produce the best frame from available information.
4. Leave Task-Shaping Fields blank (no value after the colon) when the conversation
   does not provide enough information to decide.
5. Keep section content concise and actionable.
"""

_CHAT_CHAR_LIMIT = 8000
_CONTEXT_CHAR_LIMIT = 2000


def build_frame_generation_role_prefix() -> str:
    return _GENERATION_ROLE_PREFIX


def build_frame_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["content"],
        "properties": {
            "content": {
                "type": "string",
                "description": "The full markdown content for frame.md",
            },
        },
    }


def build_frame_generation_prompt(
    chat_messages: list[dict[str, Any]],
    task_context: dict[str, Any],
    *,
    role_prefix: str | None = None,
) -> str:
    sections: list[str] = []

    if role_prefix:
        sections.append(role_prefix)

    sections.append(_format_task_context(task_context))

    chat_block = _format_chat_history(chat_messages)
    if chat_block:
        sections.append(chat_block)

    sections.append(
        "Generate the frame document now. "
        "Respond with the full markdown content as structured JSON output."
    )

    return "\n\n".join(s for s in sections if s.strip())


def extract_frame_content(tool_calls: Any) -> str | None:
    if not isinstance(tool_calls, list):
        return None
    for raw_call in tool_calls:
        if not isinstance(raw_call, dict):
            continue
        if str(raw_call.get("tool_name") or "") != "emit_frame_content":
            continue
        arguments = raw_call.get("arguments")
        if not isinstance(arguments, dict):
            continue
        content = arguments.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None


def extract_frame_content_from_structured_output(stdout: str) -> str | None:
    """Parse structured JSON output for frame content."""
    text = strip_json_fence(stdout)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(parsed, dict):
        content = parsed.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


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

    siblings = task_context.get("prior_node_summaries_compact")
    if isinstance(siblings, list) and siblings:
        lines.append("- Completed siblings:")
        for item in siblings:
            if not isinstance(item, dict):
                continue
            title = normalize_text(item.get("title"))
            desc = normalize_text(item.get("description"))
            summary = f"{title}: {desc}" if title and desc else title or desc
            if summary:
                lines.append(f"  - {truncate(summary, 200)}")

    return "\n".join(lines)


def _format_chat_history(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""

    lines = ["Conversation history:"]
    total_chars = 0
    for msg in messages:
        role = str(msg.get("role", "")).strip()
        content = str(msg.get("content", "")).strip()
        if not role or not content:
            continue
        entry = f"[{role}]: {content}"
        if total_chars + len(entry) > _CHAT_CHAR_LIMIT:
            lines.append("... (earlier messages truncated)")
            break
        lines.append(entry)
        total_chars += len(entry)

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)
