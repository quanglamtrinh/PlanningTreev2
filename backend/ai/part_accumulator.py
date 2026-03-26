"""Converts raw Codex callbacks into ordered message parts."""

from __future__ import annotations

from typing import Any

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
        self.parts: list[dict[str, Any]] = []
        self.items: list[dict[str, Any]] = []
        self._current_text_part: dict[str, Any] | None = None
        self._current_plan_part: dict[str, Any] | None = None
        self._tool_item_by_call_id: dict[str, str] = {}
        self._running_tool_item_ids: list[str] = []
        self._next_anonymous_tool_id = 1
        self._next_anonymous_item_id = 1

    def _phase_to_status(self, phase: str) -> str:
        if phase == "started":
            return "started"
        if phase == "delta":
            return "streaming"
        if phase == "completed":
            return "completed"
        return "error"

    def _find_item(self, item_id: str) -> dict[str, Any] | None:
        for item in self.items:
            if item.get("item_id") == item_id:
                return item
        return None

    def _record_item_lifecycle(
        self,
        *,
        item_id: str,
        item_type: str,
        phase: str,
        payload: dict[str, Any] | None = None,
        text: str | None = None,
    ) -> None:
        normalized_id = str(item_id or "").strip()
        normalized_type = str(item_type or "").strip()
        if not normalized_id or not normalized_type:
            return

        now = iso_now()
        item = self._find_item(normalized_id)
        if item is None:
            item = {
                "item_id": normalized_id,
                "item_type": normalized_type,
                "status": "started",
                "started_at": now,
                "completed_at": None,
                "last_payload": payload,
                "lifecycle": [],
            }
            self.items.append(item)

        entry: dict[str, Any] = {
            "phase": phase,
            "timestamp": now,
        }
        if payload is not None:
            entry["payload"] = payload
            item["last_payload"] = payload
        if isinstance(text, str):
            entry["text"] = text
        item["lifecycle"].append(entry)
        item["status"] = self._phase_to_status(phase)
        if phase in {"completed", "error"}:
            item["completed_at"] = now

    def on_delta(self, delta: str) -> None:
        """Text delta -> append to current assistant_text part, or create new one."""
        self._close_plan_part()
        if self._current_text_part is None:
            self._current_text_part = {
                "type": "assistant_text",
                "content": "",
                "is_streaming": True,
            }
            self.parts.append(self._current_text_part)
        self._current_text_part["content"] += delta
        self._record_item_lifecycle(
            item_id="assistant_text",
            item_type="assistant_text",
            phase="delta",
            text=delta,
            payload={"length": len(delta)},
        )

    def on_plan_delta(self, delta: str, item: dict) -> None:
        """Plan delta -> append to current plan_item part, or create a new one."""
        item_id = str(item.get("id") or "").strip()
        if not item_id or not isinstance(delta, str) or not delta:
            return

        if (
            self._current_plan_part is not None
            and self._current_plan_part.get("item_id") == item_id
        ):
            self._current_plan_part["content"] += delta
            self._current_plan_part["timestamp"] = iso_now()
            self._record_item_lifecycle(
                item_id=item_id,
                item_type="plan_item",
                phase="delta",
                text=delta,
                payload={"item": dict(item)},
            )
            return

        self._close_text_part()
        self._close_plan_part()
        self._current_plan_part = {
            "type": "plan_item",
            "item_id": item_id,
            "content": delta,
            "is_streaming": True,
            "timestamp": iso_now(),
        }
        self.parts.append(self._current_plan_part)
        self._record_item_lifecycle(
            item_id=item_id,
            item_type="plan_item",
            phase="delta",
            text=delta,
            payload={"item": dict(item)},
        )

    def on_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        *,
        call_id: str | None = None,
    ) -> str:
        """Tool call -> close current text part, add tool_call part."""
        self._close_text_part()
        self._close_plan_part()
        raw_call_id = str(call_id or "").strip()
        if not raw_call_id:
            raw_call_id = f"anon-tool-{self._next_anonymous_tool_id}"
            self._next_anonymous_tool_id += 1
        item_id = f"tool:{raw_call_id}"
        self.parts.append({
            "type": "tool_call",
            "tool_name": tool_name,
            "arguments": arguments,
            "call_id": call_id,
            "status": "running",
            "output": None,
            "exit_code": None,
        })
        self._tool_item_by_call_id[raw_call_id] = item_id
        self._running_tool_item_ids.append(item_id)
        self._record_item_lifecycle(
            item_id=item_id,
            item_type="tool_call",
            phase="started",
            payload={
                "tool_name": tool_name,
                "arguments": dict(arguments),
                "call_id": call_id,
            },
        )
        return item_id

    def on_tool_result(
        self,
        call_id: str | None,
        *,
        status: str,
        output: str | None = None,
        exit_code: int | None = None,
    ) -> str | None:
        """Tool completion -> update matching tool_call part with result details."""
        target = None
        if call_id:
            for part in reversed(self.parts):
                if part.get("type") == "tool_call" and part.get("call_id") == call_id:
                    target = part
                    break
        if target is None:
            for part in reversed(self.parts):
                if part.get("type") == "tool_call" and part.get("status") == "running":
                    target = part
                    break
        if target is None:
            return None
        target["status"] = status
        target["output"] = output
        target["exit_code"] = exit_code
        raw_call_id = str(call_id or "").strip()
        item_id: str | None = None
        if raw_call_id:
            item_id = self._tool_item_by_call_id.get(raw_call_id)
        if item_id is None and self._running_tool_item_ids:
            item_id = self._running_tool_item_ids[-1]
        phase = "error" if status == "error" else "completed"
        if item_id is not None:
            self._record_item_lifecycle(
                item_id=item_id,
                item_type="tool_call",
                phase=phase,
                payload={
                    "status": status,
                    "output": output,
                    "exit_code": exit_code,
                    "call_id": call_id,
                },
            )
            self._running_tool_item_ids = [i for i in self._running_tool_item_ids if i != item_id]
        return item_id

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
        self._close_plan_part()
        self.parts.append({
            "type": "status_block",
            "status_type": status_type,
            "label": _status_label(status_type),
            "timestamp": iso_now(),
        })
        self._record_item_lifecycle(
            item_id="thread_status",
            item_type="thread_status",
            phase="delta",
            payload=dict(payload),
        )

    def on_item_event(self, phase: str, item: dict[str, Any]) -> str:
        """Capture typed item lifecycle from upstream app-server payloads."""
        item_type = str(item.get("type") or "").strip() or "unknown"
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            item_id = f"{item_type}:{self._next_anonymous_item_id}"
            self._next_anonymous_item_id += 1
        normalized_phase = phase if phase in {"started", "delta", "completed"} else "delta"
        self._record_item_lifecycle(
            item_id=item_id,
            item_type=item_type,
            phase=normalized_phase,
            payload=dict(item),
        )
        return item_id

    def finalize(self, *, keep_status_blocks: bool = False) -> None:
        """Called on turn completion. Close open parts, mark tool calls completed,
        remove trailing status pills."""
        self._close_text_part()
        self._close_plan_part()

        for part in self.parts:
            if part.get("type") == "tool_call" and part.get("status") == "running":
                part["status"] = "completed"
        now = iso_now()
        for item in self.items:
            if item.get("status") in {"started", "streaming"}:
                item["status"] = "completed"
                item["completed_at"] = now

        if not keep_status_blocks:
            # Remove trailing status blocks — they are transient by default.
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

    def snapshot_items(self) -> list[dict[str, Any]]:
        """Return a shallow copy of item lifecycle list for persistence."""
        copied: list[dict[str, Any]] = []
        for item in self.items:
            clone = dict(item)
            lifecycle = item.get("lifecycle", [])
            if isinstance(lifecycle, list):
                clone["lifecycle"] = [dict(entry) for entry in lifecycle if isinstance(entry, dict)]
            copied.append(clone)
        return copied

    def _close_text_part(self) -> None:
        if self._current_text_part is not None:
            self._current_text_part["is_streaming"] = False
            self._current_text_part = None

    def _close_plan_part(self) -> None:
        if self._current_plan_part is not None:
            self._current_plan_part["is_streaming"] = False
            self._current_plan_part = None
