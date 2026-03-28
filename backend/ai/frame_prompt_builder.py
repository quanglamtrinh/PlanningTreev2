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
{Key-value pairs for decisions that shape this specific task.
 Include only the minimal sufficient set of shaping fields.
 Resolved fields have a value. Unresolved fields are left blank.
 Example:
- target surface: responsive
- scope: storefront only
- realism level:
- visual style:}
"""

_FRAME_RULES = """\
Rules:
1. Derive the task's scope, requirements, and success criteria from the conversation
   history and task context provided. Do not invent committed requirements that are
   not grounded in the available context.

2. Your most important job is to select the right Task-Shaping Fields for the
   CURRENT TASK only.

3. Task-Shaping Fields are NOT all missing information. They are only the open
   decisions or constraints that materially shape this task.

4. Include a Task-Shaping Field only if it would meaningfully affect one or more of:
   - this task's scope
   - this task's decomposition
   - this task's success criteria
   - this task's core UX or behavior
   - this task's integration or technical approach
   - the rework cost if the agent assumes incorrectly

5. Do NOT generate a large candidate list and then filter it.
   Select Task-Shaping Fields directly.
   Use only the minimal sufficient set needed to avoid major misunderstanding,
   bad decomposition, or costly rework for this task.

6. Reuse parent or ancestor task-shaping decisions selectively.
   If a relevant parent or ancestor decision still directly affects this task,
   restate it in the most specific form that applies here.
   If an inherited decision is too broad for this task, specialize it with a
   narrower task-level field.
   If an inherited decision no longer shapes this task, omit it.

7. Do not reopen, contradict, or remove settled parent or ancestor decisions unless
   the conversation explicitly changes them.

8. Use decision axes only as attention lenses to notice what may shape this task.
   Use only the axes that matter here. Do NOT force all of them into every task:
   - Product boundary axis: what is included or excluded?
   - User surface axis: where and in what usage context does the user interact?
   - Experience axis: what interaction or experience direction shapes this task?
   - Realism axis: how real should implementation be at this task?
   - Workflow / operational axis: are there workflow or operational constraints?
   - Quality emphasis axis: is there a quality priority that materially changes
     solution direction?

9. A Task-Shaping Field should strongly satisfy most of the following:
   - Relevance: it directly matters to this task
   - Steering impact: changing it would change scope, decomposition, UX/behavior,
     or solution direction in a meaningful way
   - Rework risk: assuming it incorrectly would cause non-trivial rework
   - Depth fit: it matches the specificity of this task's title and scope
   - User steerability: it is something the user can reasonably specify

10. Fill in a Task-Shaping Field only when the value is clearly grounded by:
    - the user's request
    - conversation history
    - inherited confirmed context
    - or the explicit scope of this task

11. If a shaping decision is relevant but still not determined, include it as an
    unresolved Task-Shaping Field with nothing after the colon.

12. Do NOT add generic, low-value, speculative, or implementation-detail fields
    unless they still materially shape this task at this level.

13. Do NOT turn every missing detail into a Task-Shaping Field.
    Do NOT ask child-level design questions in a broad parent task.
    Do NOT keep overly broad parent-level fields in a narrow child task if a more
    specific field is needed.

14. Prefer fewer high-impact shaping fields over many low-impact ones.
    Stop once this task is sufficiently shaped.

15. Use the exact bullet format `- field name: value` for resolved fields and
    `- field name:` for unresolved fields.

16. Keep section content concise, concrete, and actionable.

17. Output only the full frame markdown content as structured JSON output.
"""

_SHARED_PROMPT_PREFIX = """\
You are a task-framing assistant for the PlanningTree project planning tool.

Your job is to generate a frame document (frame.md) for a task node.
The frame is a structured markdown document that captures the task's scope,
requirements, and shaping decisions for the CURRENT TASK only.

The conversation history may include inherited context from parent and ancestor
tasks, including confirmed frame snapshots. Use that context when deciding which
task-shaping decisions this task should inherit, restate, specialize, or omit.

Frame format:
""" + _FRAME_SECTION_TEMPLATE + "\n\n" + _FRAME_RULES

_SYSTEM_PROMPT = _SHARED_PROMPT_PREFIX

_GENERATION_ROLE_PREFIX = _SHARED_PROMPT_PREFIX

_CHAT_CHAR_LIMIT = 8000
_CONTEXT_CHAR_LIMIT = 2000


def build_frame_generation_role_prefix() -> str:
    return _GENERATION_ROLE_PREFIX


def build_frame_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
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
