from __future__ import annotations

from typing import Any

TERMINAL_STATUSES = {"completed", "failed", "interrupted"}
DELTA_METHODS = {
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/commandExecution/outputDelta",
    "item/commandExecution/terminalInteraction",
    "item/fileChange/outputDelta",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/textDelta",
}


class ThreadHistoryBuilder:
    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.current_turn: dict[str, Any] | None = None
        self.next_item_index = 1
        self.current_rollout_index = 0
        self.next_rollout_index = 0
        self._turn_by_id: dict[str, dict[str, Any]] = {}

    def finish(self) -> list[dict[str, Any]]:
        return [self._public_turn(turn) for turn in self.turns]

    def handle_rollout_item(self, item: dict[str, Any]) -> None:
        self.current_rollout_index = self.next_rollout_index
        self.next_rollout_index += 1
        variant = str(item.get("type") or "").strip()
        if variant == "turn_context":
            turn_id = self._extract_turn_id(item.get("turn") if isinstance(item.get("turn"), dict) else item)
            if turn_id:
                self._ensure_turn(turn_id, status="inProgress")
            return
        if variant == "response_item":
            self._append_response_item(item)
            return
        if variant != "event_msg":
            return
        event = item.get("event")
        if not isinstance(event, dict):
            return
        self.handle_event(event)

    def handle_event(self, event: dict[str, Any]) -> None:
        method = str(event.get("method") or event.get("type") or "").strip()
        params = event.get("params")
        if not isinstance(params, dict):
            params = {}
        turn_id = self._extract_turn_id(event) or self._extract_turn_id(params)
        thread_id = self._extract_thread_id(event) or self._extract_thread_id(params)
        occurred_at_ms = self._extract_timestamp_ms(event) or self._extract_timestamp_ms(params)

        if method == "turn/started":
            payload_turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
            started_turn_id = turn_id or self._extract_turn_id(payload_turn)
            if started_turn_id:
                metadata = payload_turn.get("metadata") if isinstance(payload_turn, dict) else None
                self._ensure_turn(
                    started_turn_id,
                    status="inProgress",
                    thread_id=thread_id,
                    timestamp_ms=occurred_at_ms,
                    metadata=metadata if isinstance(metadata, dict) else None,
                )
            return

        if method in {"user/message", "user_message"}:
            self._append_item(
                turn_id=turn_id,
                item=self._legacy_message_item(
                    event=event,
                    params=params,
                    item_type="userMessage",
                    timestamp_ms=occurred_at_ms,
                ),
                thread_id=thread_id,
                timestamp_ms=occurred_at_ms,
            )
            return

        if method in {"assistant/message", "assistant_message", "agent/message"}:
            self._append_item(
                turn_id=turn_id,
                item=self._legacy_message_item(
                    event=event,
                    params=params,
                    item_type="agentMessage",
                    timestamp_ms=occurred_at_ms,
                ),
                thread_id=thread_id,
                timestamp_ms=occurred_at_ms,
            )
            return

        if method == "item/started":
            item = self._item_from_params(method=method, params=params, thread_id=thread_id, turn_id=turn_id, status="inProgress", timestamp_ms=occurred_at_ms)
            if item is not None:
                self._upsert_item(
                    turn_id=turn_id or self._extract_turn_id(item),
                    item=item,
                    thread_id=thread_id or self._extract_thread_id(item),
                    timestamp_ms=occurred_at_ms,
                )
            return

        if method == "item/completed":
            item = params.get("item")
            if isinstance(item, dict):
                self._upsert_item(
                    turn_id=turn_id or self._extract_turn_id(item),
                    item=item,
                    thread_id=thread_id or self._extract_thread_id(item),
                    timestamp_ms=occurred_at_ms,
                )
            return

        if method in DELTA_METHODS:
            item = self._item_from_params(method=method, params=params, thread_id=thread_id, turn_id=turn_id, status="inProgress", timestamp_ms=occurred_at_ms)
            if item is not None:
                self._merge_delta_item(
                    turn_id=turn_id or self._extract_turn_id(item),
                    item=item,
                    method=method,
                    thread_id=thread_id or self._extract_thread_id(item),
                    timestamp_ms=occurred_at_ms,
                )
            return

        if method in {"serverRequest/created", "serverRequest/updated", "serverRequest/resolved"}:
            request = params.get("request")
            if isinstance(request, dict):
                request_turn_id = turn_id or self._extract_turn_id(request)
                if request_turn_id:
                    self._upsert_item(
                        turn_id=request_turn_id,
                        item={
                            "id": str(request.get("requestId") or f"{method}:{self.current_rollout_index}"),
                            "type": "serverRequest",
                            "method": str(request.get("method") or method),
                            "status": str(request.get("status") or "pending"),
                            "request": dict(request),
                            "occurredAtMs": occurred_at_ms,
                        },
                        thread_id=thread_id or self._extract_thread_id(request),
                        timestamp_ms=occurred_at_ms,
                    )
            return

        if method in {"task/started", "task/completed", "task/failed"}:
            task = dict(params)
            task["type"] = task.get("type") or method.replace("/", "_")
            task["status"] = task.get("status") or ("completed" if method == "task/completed" else "failed" if method == "task/failed" else "inProgress")
            if occurred_at_ms is not None:
                task.setdefault("occurredAtMs", occurred_at_ms)
            self._upsert_item(turn_id=turn_id, item=task, thread_id=thread_id, timestamp_ms=occurred_at_ms)
            if method == "task/failed":
                self._set_turn_status(turn_id, "failed", error=params.get("error") if isinstance(params.get("error"), dict) else None, thread_id=thread_id, timestamp_ms=occurred_at_ms)
            return

        if method == "turn/completed":
            turn_payload = params.get("turn")
            completed_turn_id = turn_id or self._extract_turn_id(turn_payload if isinstance(turn_payload, dict) else {})
            status = "completed"
            error = None
            if isinstance(turn_payload, dict):
                status = str(turn_payload.get("status") or status)
                metadata = turn_payload.get("metadata")
                if isinstance(metadata, dict):
                    self._ensure_turn(
                        completed_turn_id,
                        thread_id=thread_id,
                        timestamp_ms=occurred_at_ms,
                        metadata=metadata,
                    )
                items = turn_payload.get("items")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            self._upsert_item(
                                turn_id=completed_turn_id,
                                item=item,
                                thread_id=thread_id or self._extract_thread_id(item),
                                timestamp_ms=occurred_at_ms,
                            )
                raw_error = turn_payload.get("error")
                error = raw_error if isinstance(raw_error, dict) else None
            if status not in {"completed", "failed", "interrupted", "inProgress"}:
                status = "failed"
            self._set_turn_status(completed_turn_id, status, error=error, thread_id=thread_id, timestamp_ms=occurred_at_ms)
            return

        if method in {"turn/failed", "error"}:
            error = params.get("error") if isinstance(params.get("error"), dict) else dict(params)
            self._set_turn_status(turn_id, "failed", error=error, thread_id=thread_id, timestamp_ms=occurred_at_ms)
            return

    def _append_response_item(self, item: dict[str, Any]) -> None:
        response_item = item.get("item")
        if not isinstance(response_item, dict):
            response_item = {k: v for k, v in item.items() if k != "type"}
        turn_id = self._extract_turn_id(response_item)
        self._upsert_item(turn_id=turn_id, item=response_item, thread_id=self._extract_thread_id(response_item), timestamp_ms=self._extract_timestamp_ms(response_item))

    def _legacy_message_item(
        self,
        *,
        event: dict[str, Any],
        params: dict[str, Any],
        item_type: str,
        timestamp_ms: int | None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "type": item_type,
            "text": self._text_from_params(params),
            "occurredAtMs": timestamp_ms,
        }
        item_id = self._legacy_message_item_id(event=event, params=params)
        if item_id:
            item["id"] = item_id
        return item

    @staticmethod
    def _legacy_message_item_id(*, event: dict[str, Any], params: dict[str, Any]) -> str | None:
        for payload in (params, event):
            for key in ("itemId", "item_id", "id", "eventId", "event_id"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _ensure_turn(
        self,
        turn_id: str | None,
        *,
        status: str = "inProgress",
        thread_id: str | None = None,
        timestamp_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_turn_id = str(turn_id or "").strip() or f"synthetic-turn-{len(self.turns) + 1}"
        if not str(turn_id or "").strip():
            raise ValueError("rollout event is missing turnId; write path must persist canonical turn ids")
        existing = self._turn_by_id.get(normalized_turn_id)
        if existing is not None:
            if str(existing.get("status") or "") not in TERMINAL_STATUSES:
                existing["status"] = status
            if thread_id and not existing.get("threadId"):
                existing["threadId"] = thread_id
            if timestamp_ms is not None:
                existing["updatedAtMs"] = max(int(existing.get("updatedAtMs") or timestamp_ms), timestamp_ms)
            if metadata:
                existing_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
                existing["metadata"] = {**existing_metadata, **metadata}
            self.current_turn = existing
            return existing
        started_at_ms = timestamp_ms or 0
        turn = {
            "id": normalized_turn_id,
            "threadId": thread_id or "",
            "status": status,
            "lastCodexStatus": status if status in {"inProgress", "completed", "failed", "interrupted"} else None,
            "startedAtMs": started_at_ms,
            "completedAtMs": None,
            "items": [],
            "error": None,
            "updatedAtMs": started_at_ms,
            "rolloutStartIndex": self.current_rollout_index,
        }
        if metadata:
            turn["metadata"] = dict(metadata)
        self.turns.append(turn)
        self._turn_by_id[normalized_turn_id] = turn
        self.current_turn = turn
        return turn

    def _append_item(
        self,
        *,
        turn_id: str | None,
        item: dict[str, Any],
        thread_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        turn = self._ensure_turn(turn_id or self._active_turn_id(), thread_id=thread_id, timestamp_ms=timestamp_ms)
        normalized = dict(item)
        if not str(normalized.get("id") or "").strip():
            normalized["id"] = f"item-{self.next_item_index}"
            self.next_item_index += 1
        if timestamp_ms is not None:
            normalized.setdefault("createdAtMs", timestamp_ms)
            normalized.setdefault("updatedAtMs", timestamp_ms)
        turn["items"].append(normalized)

    def _upsert_item(
        self,
        *,
        turn_id: str | None,
        item: dict[str, Any],
        thread_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        turn = self._ensure_turn(turn_id or self._active_turn_id(), thread_id=thread_id, timestamp_ms=timestamp_ms)
        item_id = str(item.get("id") or "").strip()
        if item_id:
            for index, existing in enumerate(turn["items"]):
                if isinstance(existing, dict) and str(existing.get("id") or "").strip() == item_id:
                    turn["items"][index] = {**existing, **item}
                    return
        duplicate_index = self._matching_message_item_index(turn, item)
        if duplicate_index is not None:
            existing = turn["items"][duplicate_index]
            turn["items"][duplicate_index] = {**existing, **item}
            return
        self._append_item(turn_id=str(turn["id"]), item=item, thread_id=thread_id, timestamp_ms=timestamp_ms)


    @classmethod
    def _matching_message_item_index(cls, turn: dict[str, Any], item: dict[str, Any]) -> int | None:
        item_type = str(item.get("type") or "").strip()
        if item_type not in {"userMessage", "agentMessage"}:
            return None
        item_text = cls._message_item_text(item)
        if item_text == "":
            return None
        for index, existing in enumerate(turn["items"]):
            if not isinstance(existing, dict):
                continue
            if str(existing.get("type") or "").strip() != item_type:
                continue
            if cls._message_item_text(existing) == item_text:
                return index
        return None

    @staticmethod
    def _message_item_text(item: dict[str, Any]) -> str:
        for key in ("text", "message", "content"):
            value = item.get(key)
            if isinstance(value, str):
                return value
        return ""

    def _set_turn_status(
        self,
        turn_id: str | None,
        status: str,
        *,
        error: dict[str, Any] | None = None,
        thread_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        turn = self._ensure_turn(turn_id or self._active_turn_id(), status="inProgress", thread_id=thread_id, timestamp_ms=timestamp_ms)
        turn["status"] = status if status in {"inProgress", "completed", "failed", "interrupted"} else "failed"
        if turn["status"] in TERMINAL_STATUSES:
            turn["completedAtMs"] = timestamp_ms or turn.get("completedAtMs") or turn.get("updatedAtMs") or turn.get("startedAtMs") or 0
        turn["lastCodexStatus"] = turn["status"] if turn["status"] in {"inProgress", "completed", "failed", "interrupted"} else None
        if timestamp_ms is not None:
            turn["updatedAtMs"] = timestamp_ms
        if error:
            turn["error"] = error

    def _merge_delta_item(
        self,
        *,
        turn_id: str | None,
        item: dict[str, Any],
        method: str,
        thread_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        turn = self._ensure_turn(turn_id or self._active_turn_id(), thread_id=thread_id, timestamp_ms=timestamp_ms)
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            return
        for index, existing in enumerate(turn["items"]):
            if not isinstance(existing, dict) or str(existing.get("id") or "").strip() != item_id:
                continue
            merged = {**existing, **item}
            if method == "item/commandExecution/terminalInteraction":
                output = str(existing.get("aggregatedOutput") or existing.get("output") or "")
                output += self._format_terminal_interaction_block(current_output=output, payload=item)
                merged["aggregatedOutput"] = output
                merged["output"] = output
                turn["items"][index] = merged
                return
            delta = str(item.get("delta") or "")
            if delta:
                if method in {"item/agentMessage/delta", "item/plan/delta"}:
                    merged["text"] = str(existing.get("text") or "") + delta
                elif method == "item/commandExecution/outputDelta":
                    output = str(existing.get("aggregatedOutput") or existing.get("output") or "") + delta
                    merged["aggregatedOutput"] = output
                    merged["output"] = output
                elif method == "item/fileChange/outputDelta":
                    merged["output"] = str(existing.get("output") or "") + delta
                elif method in {"item/reasoning/summaryTextDelta", "item/reasoning/textDelta"}:
                    merged["text"] = str(existing.get("text") or "") + delta
            turn["items"][index] = merged
            return
        self._append_item(turn_id=str(turn["id"]), item=item, thread_id=thread_id, timestamp_ms=timestamp_ms)

    def _item_from_params(
        self,
        *,
        method: str,
        params: dict[str, Any],
        thread_id: str | None,
        turn_id: str | None,
        status: str,
        timestamp_ms: int | None,
    ) -> dict[str, Any] | None:
        raw_item = params.get("item")
        if isinstance(raw_item, dict):
            item = dict(raw_item)
            if status and not str(item.get("status") or "").strip():
                item["status"] = status
            if turn_id and not self._extract_turn_id(item):
                item["turnId"] = turn_id
            if thread_id and not self._extract_thread_id(item):
                item["threadId"] = thread_id
            return item
        item_id = str(params.get("itemId") or params.get("item_id") or "").strip()
        if not item_id:
            return None
        item_type = self._item_type_for_method(method)
        item = {
            "id": item_id,
            "type": item_type,
            "status": status,
            "turnId": turn_id,
            "threadId": thread_id,
            **dict(params),
        }
        if method in {"item/agentMessage/delta", "item/plan/delta"}:
            item["text"] = str(params.get("delta") or "")
        if method == "item/commandExecution/terminalInteraction":
            item["output"] = self._format_terminal_interaction_block(current_output="", payload=params)
            item["aggregatedOutput"] = item["output"]
        if timestamp_ms is not None:
            item.setdefault("createdAtMs", timestamp_ms)
            item.setdefault("updatedAtMs", timestamp_ms)
        return item

    @staticmethod
    def _item_type_for_method(method: str) -> str:
        if method == "item/agentMessage/delta":
            return "agentMessage"
        if method == "item/plan/delta":
            return "plan"
        if method.startswith("item/commandExecution/"):
            return "commandExecution"
        if method.startswith("item/fileChange/"):
            return "fileChange"
        if method.startswith("item/reasoning/"):
            return "reasoning"
        return "unknown"

    @staticmethod
    def _extract_terminal_interaction_text(payload: dict[str, Any]) -> str:
        for key in ("stdin", "input", "text", "delta", "content"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        interaction = payload.get("interaction")
        if isinstance(interaction, dict):
            for key in ("stdin", "input", "text", "delta", "content"):
                value = interaction.get(key)
                if isinstance(value, str):
                    return value
        return ""

    @classmethod
    def _format_terminal_interaction_block(cls, *, current_output: str, payload: dict[str, Any]) -> str:
        raw_text = cls._extract_terminal_interaction_text(payload)
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        prefix = "" if not current_output or current_output.endswith("\n") else "\n"
        if not normalized:
            return f"{prefix}[stdin]\n"
        return f"{prefix}[stdin]\n{normalized}\n"

    def _active_turn_id(self) -> str | None:
        if self.current_turn is None:
            return None
        return str(self.current_turn.get("id") or "").strip() or None

    @staticmethod
    def _extract_turn_id(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("turnId", "turn_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        turn = payload.get("turn")
        if isinstance(turn, dict):
            value = turn.get("id")
            if isinstance(value, str) and value.strip():
                return value.strip()
        value = payload.get("id")
        if isinstance(value, str) and value.startswith("turn") and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _extract_thread_id(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("threadId", "thread_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_timestamp_ms(payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        for key in ("occurredAtMs", "createdAtMs", "updatedAtMs", "timestampMs"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
        return None

    @staticmethod
    def _text_from_params(params: dict[str, Any]) -> str:
        for key in ("text", "message", "content"):
            value = params.get(key)
            if isinstance(value, str):
                return value
        return ""

    @staticmethod
    def _public_turn(turn: dict[str, Any]) -> dict[str, Any]:
        payload = {k: v for k, v in turn.items() if k != "rolloutStartIndex"}
        if "items" not in payload or not isinstance(payload["items"], list):
            payload["items"] = []
        payload.setdefault("threadId", "")
        payload.setdefault("status", "inProgress")
        payload.setdefault("lastCodexStatus", payload.get("status") if payload.get("status") in {"inProgress", "completed", "failed", "interrupted"} else None)
        payload.setdefault("startedAtMs", 0)
        payload.setdefault("completedAtMs", None)
        payload.setdefault("error", None)
        return payload


def build_turns_from_rollout_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    builder = ThreadHistoryBuilder()
    for item in items:
        if isinstance(item, dict):
            builder.handle_rollout_item(item)
    return builder.finish()


def paginate_turns(
    turns: list[dict[str, Any]],
    *,
    cursor: str | None = None,
    limit: int | None = None,
    sort_direction: str = "desc",
) -> dict[str, Any]:
    ordered = list(turns)
    if sort_direction.lower() != "asc":
        ordered.reverse()
    start = 0
    if cursor:
        for index, turn in enumerate(ordered):
            if str(turn.get("id") or "") == cursor:
                start = index + 1
                break
    page_limit = 50 if limit is None else max(0, int(limit))
    page = ordered[start : start + page_limit]
    next_cursor = None
    if start + page_limit < len(ordered) and page:
        next_cursor = str(page[-1].get("id") or "") or None
    return {"data": page, "nextCursor": next_cursor}
