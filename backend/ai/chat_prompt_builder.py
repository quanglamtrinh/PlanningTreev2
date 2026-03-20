from __future__ import annotations

from typing import Any

from backend.ai.split_context_builder import (
    _build_parent_chain_prompts,
    _build_prior_node_summaries_compact,
)

_PROJECT_CHAR_LIMIT = 200
_NODE_CHAR_LIMIT = 500
_ANCESTOR_CHAR_LIMIT = 300
_MAX_ANCESTORS = 6
_SIBLING_CHAR_LIMIT = 200
_MAX_SIBLINGS = 5


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_chat_prompt(
    snapshot: dict[str, Any],
    node: dict[str, Any] | None,
    node_by_id: dict[str, dict[str, Any]],
    user_content: str,
) -> str:
    parts: list[str] = []

    project = snapshot.get("project", {})
    project_name = str(project.get("name", "")).strip()
    root_goal = str(project.get("root_goal", "")).strip()
    if project_name or root_goal:
        project_line = f"Project: {project_name}" if project_name else ""
        if root_goal:
            project_line = f"{project_line}\nRoot goal: {root_goal}" if project_line else f"Root goal: {root_goal}"
        parts.append(_truncate(project_line, _PROJECT_CHAR_LIMIT))

    if node is not None:
        title = str(node.get("title", "")).strip()
        description = str(node.get("description", "")).strip()
        node_text = ""
        if title:
            node_text = f"Current task: {title}"
        if description:
            node_text = f"{node_text}\nDescription: {description}" if node_text else f"Description: {description}"
        if node_text:
            parts.append(_truncate(node_text, _NODE_CHAR_LIMIT))

        ancestors = _build_parent_chain_prompts(node, node_by_id)
        if len(ancestors) > _MAX_ANCESTORS:
            ancestors = [ancestors[0], *ancestors[-(_MAX_ANCESTORS - 1):]]
        if ancestors:
            ancestor_lines = [
                _truncate(f"  - {a}", _ANCESTOR_CHAR_LIMIT) for a in ancestors
            ]
            parts.append("Ancestors:\n" + "\n".join(ancestor_lines))

        siblings = _build_prior_node_summaries_compact(node, node_by_id)
        siblings = siblings[-_MAX_SIBLINGS:]
        if siblings:
            sibling_lines = [
                _truncate(f"  - {s['title']}: {s['description']}", _SIBLING_CHAR_LIMIT)
                for s in siblings
            ]
            parts.append("Completed siblings:\n" + "\n".join(sibling_lines))

    hidden_context = "\n\n".join(parts)
    if hidden_context:
        return f"{hidden_context}\n\n---\n\nUser message:\n{user_content}"
    return user_content
