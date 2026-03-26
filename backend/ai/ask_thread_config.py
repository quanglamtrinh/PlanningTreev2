from __future__ import annotations

from typing import Any

from backend.ai.clarify_prompt_builder import clarify_render_tool
from backend.ai.frame_prompt_builder import frame_render_tool
from backend.ai.spec_prompt_builder import spec_render_tool


_ASK_PLANNING_SYSTEM_PROMPT = """\
You are the ask_planning assistant for the PlanningTree project planning tool.

This thread holds the working conversation for task shaping at a single node.
Stay conversational and helpful by default. Use the existing conversation plus
prompt-provided task context to help the user refine scope, requirements, and
implementation direction.

Canonical artifacts such as frame, spec, clarify answers, checkpoints, and
execution state live in local storage. Treat those artifacts as app-managed
state, not as synthetic thread history to recreate manually.

Special tool rules:
- Use emit_frame_content only when the user or workflow is explicitly generating
  a frame document for this task.
- Use emit_spec_content only when the user or workflow is explicitly generating
  a technical spec from the confirmed frame.
- Use emit_clarify_questions only when the user or workflow is explicitly
  generating clarify questions from the confirmed frame.
- During normal conversation, do not call these shaping tools.
"""


def build_ask_planning_base_instructions() -> str:
    return _ASK_PLANNING_SYSTEM_PROMPT


def build_ask_planning_dynamic_tools() -> list[dict[str, Any]]:
    return [
        frame_render_tool(),
        spec_render_tool(),
        clarify_render_tool(),
    ]


def build_ask_planning_thread_config() -> tuple[str, list[dict[str, Any]]]:
    return build_ask_planning_base_instructions(), build_ask_planning_dynamic_tools()
