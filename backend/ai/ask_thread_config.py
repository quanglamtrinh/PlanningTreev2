from __future__ import annotations

from typing import Any

# Placeholder — base instructions for ask_planning threads will be configured
# later.  Sent as "" explicitly so the forked thread does NOT inherit the
# source (audit) thread's base instructions.
_ASK_PLANNING_BASE_INSTRUCTIONS_PLACEHOLDER = ""


def build_ask_planning_base_instructions() -> str:
    return _ASK_PLANNING_BASE_INSTRUCTIONS_PLACEHOLDER


def build_ask_planning_dynamic_tools() -> list[dict[str, Any]]:
    return []


def build_ask_planning_thread_config() -> tuple[str, list[dict[str, Any]]]:
    return build_ask_planning_base_instructions(), build_ask_planning_dynamic_tools()
