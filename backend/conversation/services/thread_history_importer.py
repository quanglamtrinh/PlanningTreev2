from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.conversation.domain.types import ThreadSnapshotV2, copy_snapshot, normalize_item, normalize_tool_output_file
from backend.storage.file_utils import iso_now

_BOOTSTRAP_READY = "READY"
_BOOTSTRAP_PROMPT_SNIPPET = "Initialization only. Do not call any tools. Reply with exactly READY."


def hydrate_snapshot_from_thread_read(
    snapshot: ThreadSnapshotV2,
    payload: dict[str, Any] | Any,
) -> tuple[ThreadSnapshotV2, bool]:
    thread = payload.get("thread") if isinstance(payload, dict) else None
    if not isinstance(thread, dict):
        return snapshot, False
    turns = thread.get("turns")
    if not isinstance(turns, list) or not turns:
        return snapshot, False

    thread_id = str(snapshot.get("threadId") or thread.get("id") or "").strip()
    if not thread_id:
        return snapshot, False

    updated = copy_snapshot(snapshot)
    existing_ids = {str(item.get("id") or "").strip() for item in updated.get("items", [])}
    next_sequence = max((int(item.get("sequence") or 0) for item in updated.get("items", [])), default=0)
    thread_created_ms = _thread_created_ms(thread, thread_id)
    thread_updated_ms = _thread_updated_ms(thread)
    snapshot_updated_ms = _parse_iso_ms(updated.get("updatedAt"))
    import_base = _import_base_datetime(thread_created_ms, updated.get("createdAt"))
    latest_visible_turn_ms: int | None = None
    latest_visible_turn_status: str | None = None
    imported_any = False

    for turn in turns:
        if not isinstance(turn, dict):
            continue
        turn_id = str(turn.get("id") or "").strip()
        turn_ms = _uuidv7_ms(turn_id)
        if thread_created_ms is not None and turn_ms is not None and turn_ms < thread_created_ms:
            continue
        if _is_bootstrap_turn(turn):
            continue
        imported_items = _visible_items_from_turn(
            snapshot=snapshot,
            thread_id=thread_id,
            turn=turn,
            import_base=import_base,
        )
        if not imported_items:
            continue
        latest_visible_turn_ms = turn_ms if turn_ms is not None else latest_visible_turn_ms
        latest_visible_turn_status = str(turn.get("status") or "").strip().lower() or latest_visible_turn_status
        for raw_item in imported_items:
            item_id = str(raw_item.get("id") or "").strip()
            if not item_id or item_id in existing_ids:
                continue
            next_sequence += 1
            timestamp = _synthetic_item_timestamp(import_base, next_sequence)
            raw_item["sequence"] = next_sequence
            raw_item["createdAt"] = timestamp
            raw_item["updatedAt"] = timestamp
            normalized = normalize_item(raw_item, thread_id=thread_id)
            updated["items"].append(normalized)
            existing_ids.add(item_id)
            imported_any = True

    if not imported_any:
        return snapshot, False

    updated["items"].sort(key=lambda item: (int(item.get("sequence") or 0), str(item.get("id") or "")))
    changed = True

    if (
        str(snapshot.get("processingState") or "") == "running"
        and latest_visible_turn_ms is not None
        and snapshot_updated_ms is not None
        and max(latest_visible_turn_ms, thread_updated_ms or latest_visible_turn_ms) >= snapshot_updated_ms
        and latest_visible_turn_status in {"completed", "failed", "error", "interrupted", "cancelled"}
    ):
        updated["processingState"] = "idle"
        updated["activeTurnId"] = None

    return updated, changed


def _visible_items_from_turn(
    *,
    snapshot: ThreadSnapshotV2,
    thread_id: str,
    turn: dict[str, Any],
    import_base: datetime,
) -> list[dict[str, Any]]:
    turn_id = str(turn.get("id") or "").strip() or None
    turn_status = str(turn.get("status") or "").strip().lower()
    item_status = _item_status_from_turn_status(turn_status)
    items = turn.get("items")
    if not isinstance(items, list):
        return []

    visible: list[dict[str, Any]] = []
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            continue
        item_type = str(raw.get("type") or "").strip()
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            continue
        metadata = {
            "importedFromThreadRead": True,
            "threadReadTurnStatus": turn_status or None,
            "threadReadOrder": index,
        }
        if item_type == "agentMessage":
            text = _extract_agent_text(raw)
            if not text.strip() or text.strip() == _BOOTSTRAP_READY:
                continue
            phase = str(raw.get("phase") or "").strip().lower() or None
            if phase:
                metadata["phase"] = phase
            visible.append(
                {
                    "id": item_id,
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "status": item_status,
                    "source": "upstream",
                    "tone": "muted" if phase == "commentary" else "neutral",
                    "metadata": metadata,
                    "role": "assistant",
                    "text": text,
                    "format": "markdown",
                }
            )
            continue
        if item_type == "userMessage":
            if snapshot.get("threadRole") in {"execution", "audit"}:
                continue
            text = _extract_user_text(raw)
            if not text.strip():
                continue
            visible.append(
                {
                    "id": item_id,
                    "kind": "message",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "status": item_status,
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": metadata,
                    "role": "user",
                    "text": text,
                    "format": "markdown",
                }
            )
            continue
        if item_type == "plan":
            text = str(raw.get("text") or "").strip()
            if not text:
                continue
            visible.append(
                {
                    "id": item_id,
                    "kind": "plan",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "status": item_status,
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": metadata,
                    "title": None,
                    "text": text,
                    "steps": [],
                }
            )
            continue
        if item_type == "commandExecution":
            output_text = _extract_command_output(raw)
            visible.append(
                {
                    "id": item_id,
                    "kind": "tool",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "status": item_status,
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": metadata,
                    "toolType": "commandExecution",
                    "title": str(raw.get("command") or raw.get("title") or "commandExecution"),
                    "toolName": str(raw.get("toolName") or raw.get("tool_name") or raw.get("command") or "").strip() or None,
                    "callId": str(raw.get("callId") or raw.get("call_id") or "").strip() or None,
                    "argumentsText": str(raw.get("argumentsText") or raw.get("command") or "").strip() or None,
                    "outputText": output_text,
                    "outputFiles": [],
                    "exitCode": raw.get("exitCode") if isinstance(raw.get("exitCode"), int) else None,
                }
            )
            continue
        if item_type == "fileChange":
            files = _extract_output_files(raw.get("changes") or raw.get("files"))
            summary_text = _extract_command_output(raw)
            visible.append(
                {
                    "id": item_id,
                    "kind": "tool",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "status": item_status,
                    "source": "upstream",
                    "tone": "neutral",
                    "metadata": metadata,
                    "toolType": "fileChange",
                    "title": str(raw.get("title") or "fileChange"),
                    "toolName": str(raw.get("toolName") or raw.get("tool_name") or "").strip() or None,
                    "callId": str(raw.get("callId") or raw.get("call_id") or "").strip() or None,
                    "argumentsText": str(raw.get("argumentsText") or "").strip() or None,
                    "outputText": summary_text,
                    "outputFiles": files,
                    "exitCode": raw.get("exitCode") if isinstance(raw.get("exitCode"), int) else None,
                }
            )
    return visible


def _is_bootstrap_turn(turn: dict[str, Any]) -> bool:
    items = turn.get("items")
    if not isinstance(items, list):
        return False
    saw_bootstrap_prompt = False
    assistant_texts: list[str] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_type = str(raw.get("type") or "").strip()
        if item_type == "userMessage":
            text = _extract_user_text(raw)
            if _BOOTSTRAP_PROMPT_SNIPPET in text:
                saw_bootstrap_prompt = True
        elif item_type == "agentMessage":
            text = _extract_agent_text(raw).strip()
            if text:
                assistant_texts.append(text)
    return saw_bootstrap_prompt and assistant_texts == [_BOOTSTRAP_READY]


def _extract_user_text(raw: dict[str, Any]) -> str:
    content = raw.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts).strip()


def _extract_agent_text(raw: dict[str, Any]) -> str:
    text = raw.get("text")
    if isinstance(text, str) and text.strip():
        return text
    content = raw.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text_value = item.get("text")
        if isinstance(text_value, str) and text_value:
            parts.append(text_value)
    return "\n".join(parts).strip()


def _extract_command_output(raw: dict[str, Any]) -> str:
    for key in ("aggregatedOutput", "output", "text"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _extract_output_files(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    files: list[dict[str, Any]] = []
    for item in raw:
        normalized = normalize_tool_output_file(item)
        if normalized is not None:
            files.append(normalized)
    return files


def _item_status_from_turn_status(turn_status: str) -> str:
    normalized = str(turn_status or "").strip().lower()
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"interrupted", "cancelled"}:
        return "cancelled"
    return "completed"


def _thread_created_ms(thread: dict[str, Any], thread_id: str) -> int | None:
    created_at = thread.get("createdAt")
    if isinstance(created_at, (int, float)):
        return int(created_at) * 1000
    return _uuidv7_ms(thread_id)


def _thread_updated_ms(thread: dict[str, Any]) -> int | None:
    updated_at = thread.get("updatedAt")
    if isinstance(updated_at, (int, float)):
        return int(updated_at) * 1000
    return None


def _uuidv7_ms(value: str | None) -> int | None:
    if not isinstance(value, str):
        return None
    compact = value.replace("-", "").strip()
    if len(compact) < 12:
        return None
    try:
        return int(compact[:12], 16)
    except ValueError:
        return None


def _parse_iso_ms(value: Any) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except ValueError:
        return None


def _import_base_datetime(thread_created_ms: int | None, snapshot_created_at: Any) -> datetime:
    if thread_created_ms is not None:
        return datetime.fromtimestamp(thread_created_ms / 1000, tz=timezone.utc)
    parsed_ms = _parse_iso_ms(snapshot_created_at)
    if parsed_ms is not None:
        return datetime.fromtimestamp(parsed_ms / 1000, tz=timezone.utc)
    return datetime.fromisoformat(iso_now().replace("Z", "+00:00"))


def _synthetic_item_timestamp(base: datetime, sequence: int) -> str:
    return (base + timedelta(seconds=max(sequence, 1))).replace(microsecond=0).isoformat().replace("+00:00", "Z")
