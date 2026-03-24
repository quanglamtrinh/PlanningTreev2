from __future__ import annotations

import json
from typing import Any


_SYSTEM_PROMPT = """\
You are an automated execution agent for the PlanningTree project planning tool.

Your job is to implement a confirmed task spec directly in the workspace.
The spec and frame below are already confirmed. Do not ask follow-up questions.

Rules:
1. Treat the confirmed spec as the contract for this execution run.
2. Use the confirmed frame as supporting context when the spec leaves room for interpretation.
3. Make concrete workspace changes when the spec calls for them.
4. Keep the implementation aligned with the existing codebase instead of inventing a parallel architecture.
5. When you finish, provide a concise summary of what you changed and any notable limitations.
"""

_FRAME_CHAR_LIMIT = 12000
_SPEC_CHAR_LIMIT = 16000
_CONTEXT_CHAR_LIMIT = 3000


def build_execution_base_instructions() -> str:
    return _SYSTEM_PROMPT


def build_execution_prompt(
    *,
    spec_content: str,
    frame_content: str,
    task_context: dict[str, Any],
) -> str:
    sections: list[str] = [
        _format_task_context(task_context),
        _format_confirmed_frame(frame_content),
        _format_confirmed_spec(spec_content),
        (
            "Implement the task in the workspace now. "
            "When complete, provide a brief summary of the concrete changes made."
        ),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def _format_task_context(task_context: dict[str, Any]) -> str:
    payload = {
        "root_goal": str(task_context.get("root_prompt") or ""),
        "current_node": str(task_context.get("current_node_prompt") or ""),
        "node_id": str(task_context.get("node_id") or ""),
        "tree_depth": int(task_context.get("tree_depth", 0) or 0),
        "parent_chain_prompts": task_context.get("parent_chain_prompts") or [],
        "prior_node_summaries_compact": task_context.get("prior_node_summaries_compact") or [],
        "existing_children_count": int(task_context.get("existing_children_count", 0) or 0),
    }
    rendered = json.dumps(payload, ensure_ascii=True, indent=2)
    if len(rendered) > _CONTEXT_CHAR_LIMIT:
        rendered = rendered[: _CONTEXT_CHAR_LIMIT - 3] + "..."
    return "Task context:\n```json\n" + rendered + "\n```"


def _format_confirmed_frame(frame_content: str) -> str:
    content = frame_content.strip()
    if not content:
        return "Confirmed frame:\n(omitted)"
    if len(content) > _FRAME_CHAR_LIMIT:
        content = content[: _FRAME_CHAR_LIMIT - 3] + "..."
    return "Confirmed frame:\n```markdown\n" + content + "\n```"


def _format_confirmed_spec(spec_content: str) -> str:
    content = spec_content.strip()
    if len(content) > _SPEC_CHAR_LIMIT:
        content = content[: _SPEC_CHAR_LIMIT - 3] + "..."
    return "Confirmed spec:\n```markdown\n" + content + "\n```"
