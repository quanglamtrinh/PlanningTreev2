from __future__ import annotations

from typing import Any


def make_planning_stream_id(turn_id: str) -> str:
    return f"planning_stream:{turn_id}"


def make_planning_user_message_id(turn_id: str) -> str:
    return f"planning_msg:{turn_id}:user"


def make_planning_assistant_message_id(turn_id: str) -> str:
    return f"planning_msg:{turn_id}:assistant"


def make_planning_assistant_text_part_id(turn_id: str) -> str:
    return f"planning_part:{turn_id}:assistant_text"


def make_planning_tool_call_part_id(turn_id: str, index: int) -> str:
    return f"planning_part:{turn_id}:tool_call:{index}"


def extract_split_payload(tool_calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    for tool_call in tool_calls:
        if str(tool_call.get("tool_name") or "") != "emit_render_data":
            continue
        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            continue
        if str(arguments.get("kind") or "") != "split_result":
            continue
        payload = arguments.get("payload")
        if isinstance(payload, dict):
            return payload
    return None


def build_planning_split_summary(
    *,
    payload: dict[str, Any] | None,
    created_child_ids: list[str] | None = None,
) -> str:
    created_count = len(created_child_ids or [])
    if isinstance(payload, dict):
        subtasks = payload.get("subtasks")
        if isinstance(subtasks, list):
            valid_subtasks = [
                subtask
                for subtask in subtasks
                if isinstance(subtask, dict)
                and all(
                    isinstance(subtask.get(field), str) and str(subtask.get(field) or "").strip()
                    for field in ("id", "title", "objective", "why_now")
                )
            ]
            if valid_subtasks:
                subtask_count = len(valid_subtasks)
                return f"Split completed. Created {subtask_count} child tasks."
    if created_count > 0:
        return f"Split completed. Created {created_count} child tasks."
    return "Split completed."


def build_context_merge_text(summary: str | None, content: str | None) -> str:
    summary_text = str(summary or "").strip()
    content_text = str(content or "").strip()
    if summary_text and content_text:
        return f"{summary_text}\n\n{content_text}"
    return summary_text or content_text
