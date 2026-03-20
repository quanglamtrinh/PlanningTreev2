"""Converts raw Codex callbacks into ordered message parts."""

from __future__ import annotations

from backend.storage.file_utils import iso_now


def _status_label(status_type: str) -> str:
    labels = {
        "running": "Working...",
        "idle": "Idle",
        "notLoaded": "Loading...",
    }
    return labels.get(status_type, status_type)


class PartAccumulator:
    """Accumulates streaming events into an ordered list of message parts.

    Part types produced:
      assistant_text  — streaming markdown text
      tool_call       — collapsible tool invocation block
      status_block    — transient status pill (removed on finalize)
    """

    def __init__(self) -> None:
        self.parts: list[dict] = []
        self._current_text_part: dict | None = None

    def on_delta(self, delta: str) -> None:
        """Text delta -> append to current assistant_text part, or create new one."""
        if self._current_text_part is None:
            self._current_text_part = {
                "type": "assistant_text",
                "content": "",
                "is_streaming": True,
            }
            self.parts.append(self._current_text_part)
        self._current_text_part["content"] += delta

    def on_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Tool call -> close current text part, add tool_call part."""
        self._close_text_part()
        self.parts.append({
            "type": "tool_call",
            "tool_name": tool_name,
            "arguments": arguments,
            "call_id": None,
            "status": "running",
        })

    def on_thread_status(self, payload: dict) -> None:
        """Thread status change -> add or update status_block part."""
        status = payload.get("status", {})
        if not isinstance(status, dict):
            return
        status_type = status.get("type", "unknown")

        # Update existing trailing status block instead of adding a new one.
        if self.parts and self.parts[-1].get("type") == "status_block":
            self.parts[-1]["status_type"] = status_type
            self.parts[-1]["label"] = _status_label(status_type)
            self.parts[-1]["timestamp"] = iso_now()
            return

        self._close_text_part()
        self.parts.append({
            "type": "status_block",
            "status_type": status_type,
            "label": _status_label(status_type),
            "timestamp": iso_now(),
        })

    def finalize(self) -> None:
        """Called on turn completion. Close open parts, mark tool calls completed,
        remove trailing status pills."""
        self._close_text_part()

        for part in self.parts:
            if part.get("type") == "tool_call" and part.get("status") == "running":
                part["status"] = "completed"

        # Remove trailing status blocks — they are transient.
        while self.parts and self.parts[-1].get("type") == "status_block":
            self.parts.pop()

    def content_projection(self) -> str:
        """Concatenate all assistant_text content into a single string."""
        return "".join(
            part["content"]
            for part in self.parts
            if part.get("type") == "assistant_text"
        )

    def snapshot_parts(self) -> list[dict]:
        """Return a shallow copy of the current parts list for persistence."""
        return [dict(part) for part in self.parts]

    def _close_text_part(self) -> None:
        if self._current_text_part is not None:
            self._current_text_part["is_streaming"] = False
            self._current_text_part = None
