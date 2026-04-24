from __future__ import annotations

from typing import Any

# Keep ask_planning instructions explicit and non-empty so bootstrap and turns
# remain valid across Codex runtime versions.
_ASK_PLANNING_BASE_INSTRUCTIONS = """
You are the ask_planning assistant for PlanningTree.
Help shape and clarify tasks before execution.

Priorities:
- Keep responses concise, concrete, and actionable.
- Ground guidance in the current repository and task context.
- Surface assumptions and risks when they materially affect implementation.
- Ask focused clarifying questions only when required to proceed safely.

Do not produce unrelated output or filler text.
""".strip()


def build_ask_planning_base_instructions() -> str:
    return _ASK_PLANNING_BASE_INSTRUCTIONS


def build_ask_planning_dynamic_tools() -> list[dict[str, Any]]:
    return []


def build_ask_planning_thread_config() -> tuple[str, list[dict[str, Any]]]:
    return build_ask_planning_base_instructions(), build_ask_planning_dynamic_tools()
