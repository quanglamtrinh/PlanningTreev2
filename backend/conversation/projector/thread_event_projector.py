from __future__ import annotations

import copy
from typing import Any

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import (
    ConversationItem,
    ItemPatch,
    PendingUserInputRequest,
    ThreadSnapshotV2,
    ToolChange,
    ToolOutputFile,
    UserInputAnswer,
    copy_snapshot,
    normalize_item,
    normalize_item_status,
    normalize_tool_change,
    normalize_tool_output_file,
    normalize_user_input_answer,
)
from backend.errors.app_errors import ConversationStreamMismatch
from backend.storage.file_utils import iso_now

IMMUTABLE_PATCH_FIELDS = {
    "id",
    "threadId",
    "turnId",
    "sequence",
    "createdAt",
    "source",
    "role",
    "toolType",
    "requestId",
}

IMMUTABLE_UPSERT_FIELDS = {
    "threadId",
    "turnId",
    "source",
    "role",
    "toolType",
    "requestId",
}


def build_snapshot_event(snapshot: ThreadSnapshotV2) -> dict[str, Any]:
    return {"type": event_types.THREAD_SNAPSHOT, "payload": {"snapshot": snapshot}}


def upsert_item(snapshot: ThreadSnapshotV2, item: ConversationItem) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated = copy_snapshot(snapshot)
    normalized = normalize_item(item, thread_id=snapshot.get("threadId"))
    existing_index = _find_item_index(updated, str(normalized["id"]))
    if existing_index is None:
        updated["items"].append(normalized)
    else:
        existing = updated["items"][existing_index]
        if str(existing.get("kind") or "") != str(normalized.get("kind") or ""):
            raise ConversationStreamMismatch()
        _validate_upsert_immutable_fields(existing, normalized)
        merged = copy.deepcopy(normalized)
        merged["sequence"] = existing["sequence"]
        merged["createdAt"] = existing["createdAt"]
        updated["items"][existing_index] = merged
        normalized = merged
    updated["items"].sort(key=lambda current: (int(current.get("sequence") or 0), str(current.get("id") or "")))
    return updated, [{"type": event_types.CONVERSATION_ITEM_UPSERT, "payload": {"item": normalized}}]


def patch_item(snapshot: ThreadSnapshotV2, item_id: str, patch: ItemPatch | dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated = copy_snapshot(snapshot)
    index = _find_item_index(updated, item_id)
    if index is None:
        raise ConversationStreamMismatch()
    current = updated["items"][index]
    patch_kind = str(patch.get("kind") or "").strip()
    if not patch_kind or patch_kind != str(current.get("kind") or ""):
        raise ConversationStreamMismatch()
    merged = _apply_patch_to_item(current, patch)
    updated["items"][index] = merged
    return updated, [{"type": event_types.CONVERSATION_ITEM_PATCH, "payload": {"itemId": item_id, "patch": patch}}]


def apply_lifecycle(
    snapshot: ThreadSnapshotV2,
    *,
    state: str,
    processing_state: str,
    active_turn_id: str | None,
    detail: str | None = None,
) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated = copy_snapshot(snapshot)
    updated["processingState"] = processing_state  # type: ignore[typeddict-item]
    updated["activeTurnId"] = active_turn_id
    return updated, [
        {
            "type": event_types.THREAD_LIFECYCLE,
            "payload": {
                "activeTurnId": active_turn_id,
                "processingState": processing_state,
                "state": state,
                "detail": detail,
            },
        }
    ]


def finalize_turn(
    snapshot: ThreadSnapshotV2,
    *,
    turn_id: str | None,
    outcome: str,
    error_item: ConversationItem | None = None,
) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    resolved_turn_id = str(turn_id or snapshot.get("activeTurnId") or "").strip() or None
    updated = copy_snapshot(snapshot)
    events: list[dict[str, Any]] = []

    if outcome == "waiting_user_input":
        updated, lifecycle_events = apply_lifecycle(
            updated,
            state=event_types.WAITING_USER_INPUT,
            processing_state="waiting_user_input",
            active_turn_id=resolved_turn_id,
        )
        events.extend(lifecycle_events)
        return updated, events

    terminal_status = "failed" if outcome == "failed" else "completed"
    if resolved_turn_id:
        updated, terminal_events = _finalize_open_items(
            updated,
            turn_id=resolved_turn_id,
            status=terminal_status,
        )
        events.extend(terminal_events)

    if outcome == "failed" and error_item is not None:
        normalized_error = copy.deepcopy(error_item)
        if resolved_turn_id and not normalized_error.get("turnId"):
            normalized_error["turnId"] = resolved_turn_id
        if int(normalized_error.get("sequence") or 0) <= 0:
            normalized_error["sequence"] = _next_sequence(updated)
        updated, error_events = apply_error(updated, normalized_error)
        events.extend(error_events)

    lifecycle_state = event_types.TURN_FAILED if outcome == "failed" else event_types.TURN_COMPLETED
    updated, lifecycle_events = apply_lifecycle(
        updated,
        state=lifecycle_state,
        processing_state="idle",
        active_turn_id=None,
    )
    events.extend(lifecycle_events)
    return updated, events


def apply_requested_user_input(
    snapshot: ThreadSnapshotV2,
    *,
    item: ConversationItem,
    pending_request: PendingUserInputRequest,
) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated, events = upsert_item(snapshot, item)
    updated = copy_snapshot(updated)
    replaced = False
    for index, current in enumerate(updated["pendingRequests"]):
        if current.get("requestId") == pending_request.get("requestId"):
            updated["pendingRequests"][index] = pending_request
            replaced = True
            break
    if not replaced:
        updated["pendingRequests"].append(pending_request)
    events.append(
        {
            "type": event_types.CONVERSATION_REQUEST_USER_INPUT_REQUESTED,
            "payload": {
                "requestId": pending_request["requestId"],
                "itemId": pending_request["itemId"],
                "item": item,
                "pendingRequest": pending_request,
            },
        }
    )
    return updated, events


def apply_resolved_user_input(
    snapshot: ThreadSnapshotV2,
    *,
    request_id: str,
    item_id: str,
    answers: list[UserInputAnswer],
    resolved_at: str,
    status: str = "answered",
) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated, events = patch_item(
        snapshot,
        item_id,
        {
            "kind": "userInput",
            "answersReplace": answers,
            "resolvedAt": resolved_at,
            "status": status,
            "updatedAt": resolved_at,
        },
    )
    updated = copy_snapshot(updated)
    for pending in updated.get("pendingRequests", []):
        if pending.get("requestId") != request_id:
            continue
        pending["answers"] = answers
        pending["resolvedAt"] = resolved_at
        pending["status"] = "answered"
    events.append(
        {
            "type": event_types.CONVERSATION_REQUEST_USER_INPUT_RESOLVED,
            "payload": {
                "requestId": request_id,
                "itemId": item_id,
                "status": status,
                "answers": answers,
                "resolvedAt": resolved_at,
            },
        }
    )
    return updated, events


def apply_error(snapshot: ThreadSnapshotV2, error_item: ConversationItem) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated, events = upsert_item(snapshot, error_item)
    events.append({"type": event_types.THREAD_ERROR, "payload": {"errorItem": error_item}})
    return updated, events


def apply_reset(snapshot: ThreadSnapshotV2) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated = copy_snapshot(snapshot)
    updated["activeTurnId"] = None
    updated["processingState"] = "idle"
    updated["items"] = []
    updated["pendingRequests"] = []
    return updated, [
        {"type": event_types.THREAD_RESET, "payload": {"threadId": snapshot.get("threadId")}},
        build_snapshot_event(updated),
    ]


def apply_raw_event(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    method = str(raw_event.get("method") or "").strip()
    if not method:
        return snapshot, []
    if method == "item/agentMessage/delta" and not raw_event.get("item_id"):
        raise ConversationStreamMismatch()
    if method in {
        "item/plan/delta",
        "item/reasoning/summaryDelta",
        "item/reasoning/detailDelta",
        "item/commandExecution/outputDelta",
        "item/fileChange/outputDelta",
    } and not raw_event.get("item_id"):
        raise ConversationStreamMismatch()
    if method == "item/started":
        return _apply_item_started(snapshot, raw_event)
    if method == "item/completed":
        return _apply_item_completed(snapshot, raw_event)
    if method == "item/agentMessage/delta":
        return patch_item(
            snapshot,
            str(raw_event["item_id"]),
            {
                "kind": "message",
                "textAppend": str(raw_event.get("params", {}).get("delta") or ""),
                "status": "in_progress",
                "updatedAt": str(raw_event.get("received_at") or iso_now()),
            },
        )
    if method == "item/plan/delta":
        return patch_item(
            snapshot,
            str(raw_event["item_id"]),
            {
                "kind": "plan",
                "textAppend": str(raw_event.get("params", {}).get("delta") or ""),
                "updatedAt": str(raw_event.get("received_at") or iso_now()),
            },
        )
    if method == "item/reasoning/summaryDelta":
        return _patch_or_upsert_reasoning(snapshot, raw_event, summary=True)
    if method == "item/reasoning/detailDelta":
        return _patch_or_upsert_reasoning(snapshot, raw_event, summary=False)
    if method == "item/commandExecution/outputDelta":
        return patch_item(
            snapshot,
            str(raw_event["item_id"]),
            {
                "kind": "tool",
                "outputTextAppend": str(raw_event.get("params", {}).get("delta") or ""),
                "status": "in_progress",
                "updatedAt": str(raw_event.get("received_at") or iso_now()),
            },
        )
    if method == "item/commandExecution/terminalInteraction":
        item_id = str(raw_event["item_id"])
        index = _find_item_index(snapshot, item_id)
        if index is None:
            raise ConversationStreamMismatch()
        current_item = snapshot["items"][index]
        return patch_item(
            snapshot,
            item_id,
            {
                "kind": "tool",
                "outputTextAppend": _format_terminal_interaction_block(
                    current_output=str(current_item.get("outputText") or ""),
                    payload=raw_event.get("params", {}),
                ),
                "status": "in_progress",
                "updatedAt": str(raw_event.get("received_at") or iso_now()),
            },
        )
    if method == "item/fileChange/outputDelta":
        patch: dict[str, Any] = {
            "kind": "tool",
            "outputTextAppend": str(raw_event.get("params", {}).get("delta") or ""),
            "status": "in_progress",
            "updatedAt": str(raw_event.get("received_at") or iso_now()),
        }
        preview_changes = _extract_tool_changes(raw_event.get("params", {}).get("files"))
        if preview_changes:
            patch["changesAppend"] = preview_changes
            patch["outputFilesAppend"] = _output_files_from_tool_changes(preview_changes)
        return patch_item(snapshot, str(raw_event["item_id"]), patch)
    if method == "item/tool/requestUserInput":
        return _apply_request_user_input(snapshot, raw_event)
    if method == "serverRequest/resolved":
        return _apply_request_resolved(snapshot, raw_event)
    if method == "thread/status/changed":
        return _apply_thread_status_changed(snapshot, raw_event)
    if method == "turn/completed":
        return _apply_turn_completed(snapshot, raw_event)
    return snapshot, []


def _apply_item_started(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    params = raw_event.get("params", {})
    item = params.get("item", {}) if isinstance(params, dict) else {}
    if not isinstance(item, dict):
        return snapshot, []
    item_type = str(item.get("type") or "").strip()
    item_id = str(item.get("id") or raw_event.get("item_id") or "").strip()
    if not item_id:
        raise ConversationStreamMismatch()
    thread_id = str(raw_event.get("thread_id") or snapshot.get("threadId") or "")
    turn_id = str(raw_event.get("turn_id") or snapshot.get("activeTurnId") or "") or None
    now = str(raw_event.get("received_at") or iso_now())
    sequence = _next_sequence(snapshot)
    if item_type == "agentMessage":
        return upsert_item(
            snapshot,
            {
                "id": item_id,
                "kind": "message",
                "threadId": thread_id,
                "turnId": turn_id,
                "sequence": sequence,
                "createdAt": now,
                "updatedAt": now,
                "status": "in_progress",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "role": "assistant",
                "text": "",
                "format": "markdown",
            },
        )
    if item_type == "plan":
        return upsert_item(
            snapshot,
            {
                "id": item_id,
                "kind": "plan",
                "threadId": thread_id,
                "turnId": turn_id,
                "sequence": sequence,
                "createdAt": now,
                "updatedAt": now,
                "status": "in_progress",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "title": None,
                "text": "",
                "steps": [],
            },
        )
    if item_type in {"commandExecution", "fileChange"}:
        return upsert_item(
            snapshot,
            {
                "id": item_id,
                "kind": "tool",
                "threadId": thread_id,
                "turnId": turn_id,
                "sequence": sequence,
                "createdAt": now,
                "updatedAt": now,
                "status": "in_progress",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {},
                "toolType": "commandExecution" if item_type == "commandExecution" else "fileChange",
                "title": str(item.get("title") or item.get("command") or item.get("type") or ""),
                "toolName": str(item.get("toolName") or item.get("tool_name") or item.get("command") or "") or None,
                "callId": str(item.get("callId") or item.get("call_id") or "") or None,
                "argumentsText": str(item.get("argumentsText") or item.get("command") or "") or None,
                "outputText": "",
                "outputFiles": [],
                "changes": [],
                "exitCode": None,
            },
        )
    return snapshot, []


def _apply_item_completed(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    params = raw_event.get("params", {})
    item = params.get("item", {}) if isinstance(params, dict) else {}
    if not isinstance(item, dict):
        return snapshot, []
    item_type = str(item.get("type") or "").strip()
    item_id = str(item.get("id") or raw_event.get("item_id") or "").strip()
    if not item_id:
        raise ConversationStreamMismatch()
    now = str(raw_event.get("received_at") or iso_now())
    if item_type == "agentMessage":
        return patch_item(snapshot, item_id, {"kind": "message", "status": "completed", "updatedAt": now})
    if item_type == "plan":
        return patch_item(snapshot, item_id, {"kind": "plan", "status": "completed", "updatedAt": now})
    if item_type == "commandExecution":
        patch: dict[str, Any] = {"kind": "tool", "status": "completed", "updatedAt": now}
        if isinstance(item.get("exitCode"), int):
            patch["exitCode"] = item["exitCode"]
        return patch_item(snapshot, item_id, patch)
    if item_type == "fileChange":
        patch = {"kind": "tool", "status": "completed", "updatedAt": now}
        has_changes_key = "changes" in item
        has_files_key = "files" in item
        if has_changes_key or has_files_key:
            raw_changes = item.get("changes") if has_changes_key else item.get("files")
            normalized_changes = _extract_tool_changes(raw_changes)
            patch["changesReplace"] = normalized_changes
            patch["outputFilesReplace"] = _output_files_from_tool_changes(normalized_changes)
        return patch_item(snapshot, item_id, patch)
    return snapshot, []


def _patch_or_upsert_reasoning(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any], *, summary: bool) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    item_id = str(raw_event.get("item_id") or "").strip()
    now = str(raw_event.get("received_at") or iso_now())
    if _find_item_index(snapshot, item_id) is None:
        snapshot, _ = upsert_item(
            snapshot,
            {
                "id": item_id,
                "kind": "reasoning",
                "threadId": str(raw_event.get("thread_id") or snapshot.get("threadId") or ""),
                "turnId": str(raw_event.get("turn_id") or snapshot.get("activeTurnId") or "") or None,
                "sequence": _next_sequence(snapshot),
                "createdAt": now,
                "updatedAt": now,
                "status": "in_progress",
                "source": "upstream",
                "tone": "muted",
                "metadata": {},
                "summaryText": "",
                "detailText": None,
            },
        )
    return patch_item(
        snapshot,
        item_id,
        {
            "kind": "reasoning",
            "summaryTextAppend" if summary else "detailTextAppend": str(raw_event.get("params", {}).get("delta") or ""),
            "status": "in_progress",
            "updatedAt": now,
        },
    )


def _apply_request_user_input(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    item_id = str(raw_event.get("item_id") or "").strip()
    request_id = str(raw_event.get("request_id") or "").strip()
    if not item_id or not request_id:
        raise ConversationStreamMismatch()
    params = raw_event.get("params", {})
    questions = params.get("questions") if isinstance(params, dict) else []
    now = str(raw_event.get("received_at") or iso_now())
    item: ConversationItem = normalize_item(
        {
            "id": item_id,
            "kind": "userInput",
            "threadId": str(raw_event.get("thread_id") or snapshot.get("threadId") or ""),
            "turnId": str(raw_event.get("turn_id") or snapshot.get("activeTurnId") or "") or None,
            "sequence": _next_sequence(snapshot),
            "createdAt": now,
            "updatedAt": now,
            "status": "requested",
            "source": "upstream",
            "tone": "info",
            "metadata": {},
            "requestId": request_id,
            "title": None,
            "questions": questions if isinstance(questions, list) else [],
            "answers": [],
            "requestedAt": now,
            "resolvedAt": None,
        }
    )
    pending: PendingUserInputRequest = {
        "requestId": request_id,
        "itemId": item_id,
        "threadId": str(raw_event.get("thread_id") or snapshot.get("threadId") or ""),
        "turnId": str(raw_event.get("turn_id") or snapshot.get("activeTurnId") or "") or None,
        "status": "requested",
        "createdAt": now,
        "submittedAt": None,
        "resolvedAt": None,
        "answers": [],
    }
    return apply_requested_user_input(snapshot, item=item, pending_request=pending)


def _apply_request_resolved(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    item_id = str(raw_event.get("item_id") or "").strip()
    request_id = str(raw_event.get("request_id") or "").strip()
    if not item_id or not request_id:
        raise ConversationStreamMismatch()
    params = raw_event.get("params", {})
    answers: list[UserInputAnswer] = []
    raw_answers = params.get("answers") if isinstance(params, dict) else []
    if isinstance(raw_answers, dict):
        raw_answers = [{"questionId": key, "value": value, "label": None} for key, value in raw_answers.items()]
    if isinstance(raw_answers, list):
        for answer in raw_answers:
            normalized = normalize_user_input_answer(answer)
            if normalized is not None:
                answers.append(normalized)
    resolved_at = str(params.get("resolved_at") or params.get("resolvedAt") or raw_event.get("received_at") or iso_now()) if isinstance(params, dict) else str(raw_event.get("received_at") or iso_now())
    return apply_resolved_user_input(snapshot, request_id=request_id, item_id=item_id, answers=answers, resolved_at=resolved_at)


def _apply_thread_status_changed(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    params = raw_event.get("params", {})
    status = params.get("status") if isinstance(params, dict) else {}
    raw_status = str(status.get("type") or status.get("state") or "").strip() if isinstance(status, dict) else ""
    normalized_status = raw_status.lower()
    if normalized_status in {"waiting_for_user_input", "waiting_user_input", "waitingforuserinput"}:
        lifecycle_state = event_types.WAITING_USER_INPUT
        processing_state = "waiting_user_input"
    elif normalized_status in {"running", "in_progress"}:
        lifecycle_state = event_types.TURN_STARTED
        processing_state = "running"
    elif normalized_status in {"failed", "error"}:
        lifecycle_state = event_types.TURN_FAILED
        processing_state = "failed"
    else:
        return snapshot, []
    return apply_lifecycle(
        snapshot,
        state=lifecycle_state,
        processing_state=str(processing_state),
        active_turn_id=snapshot.get("activeTurnId"),
        detail=raw_status or None,
    )


def _apply_turn_completed(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    params = raw_event.get("params", {})
    turn_payload = params.get("turn") if isinstance(params, dict) else {}
    raw_turn_status = (
        str(turn_payload.get("status") or params.get("status") or "").strip()
        if isinstance(turn_payload, dict)
        else str(params.get("status") or "").strip()
    )
    normalized_status = raw_turn_status.lower()
    turn_id = (
        str(turn_payload.get("id") or raw_event.get("turn_id") or snapshot.get("activeTurnId") or "").strip()
        if isinstance(turn_payload, dict)
        else str(raw_event.get("turn_id") or snapshot.get("activeTurnId") or "").strip()
    ) or None
    if normalized_status in {"waiting_user_input", "waiting_for_user_input", "waitingforuserinput"}:
        return finalize_turn(snapshot, turn_id=turn_id, outcome="waiting_user_input")
    if normalized_status in {"failed", "error", "interrupted", "cancelled"}:
        return finalize_turn(snapshot, turn_id=turn_id, outcome="failed")
    return finalize_turn(
        snapshot,
        turn_id=turn_id,
        outcome="completed",
    )


def _apply_patch_to_item(item: ConversationItem, patch: dict[str, Any]) -> ConversationItem:
    updated: ConversationItem = copy.deepcopy(item)
    for key in patch:
        if key in IMMUTABLE_PATCH_FIELDS:
            raise ConversationStreamMismatch()
    kind = str(item.get("kind") or "")
    if kind == "message":
        if patch.get("textAppend"):
            updated["text"] = str(updated.get("text") or "") + str(patch["textAppend"])
    elif kind == "reasoning":
        if patch.get("summaryTextAppend"):
            updated["summaryText"] = str(updated.get("summaryText") or "") + str(patch["summaryTextAppend"])
        if patch.get("detailTextAppend"):
            current = str(updated.get("detailText") or "")
            updated["detailText"] = current + str(patch["detailTextAppend"])
    elif kind == "plan":
        if patch.get("textAppend"):
            updated["text"] = str(updated.get("text") or "") + str(patch["textAppend"])
        if "stepsReplace" in patch:
            updated["steps"] = list(patch.get("stepsReplace") or [])
    elif kind == "tool":
        if "title" in patch:
            updated["title"] = str(patch.get("title") or "")
        if "argumentsText" in patch:
            updated["argumentsText"] = patch.get("argumentsText")
        if patch.get("outputTextAppend"):
            updated["outputText"] = str(updated.get("outputText") or "") + str(patch["outputTextAppend"])
        has_current_changes = isinstance(updated.get("changes"), list)
        current_changes = _extract_tool_changes(updated.get("changes")) if has_current_changes else []
        if not has_current_changes:
            current_changes = _tool_changes_from_output_files(_extract_output_files(updated.get("outputFiles")))

        next_changes = current_changes
        if "changesReplace" in patch:
            next_changes = _extract_tool_changes(patch.get("changesReplace"))
        elif patch.get("changesAppend"):
            next_changes = current_changes + _extract_tool_changes(patch.get("changesAppend"))
        elif "outputFilesReplace" in patch:
            next_changes = _tool_changes_from_output_files(_extract_output_files(patch.get("outputFilesReplace")))
        elif patch.get("outputFilesAppend"):
            next_changes = current_changes + _tool_changes_from_output_files(_extract_output_files(patch.get("outputFilesAppend")))

        updated["changes"] = next_changes
        updated["outputFiles"] = _output_files_from_tool_changes(next_changes)
        if "exitCode" in patch:
            updated["exitCode"] = patch.get("exitCode")
    elif kind == "userInput":
        if "answersReplace" in patch:
            updated["answers"] = list(patch.get("answersReplace") or [])
        if "resolvedAt" in patch:
            updated["resolvedAt"] = patch.get("resolvedAt")
    elif kind == "status":
        if "label" in patch:
            updated["label"] = str(patch.get("label") or "")
        if "detail" in patch:
            updated["detail"] = patch.get("detail")
    elif kind == "error":
        if "message" in patch:
            updated["message"] = str(patch.get("message") or "")
        if "relatedItemId" in patch:
            updated["relatedItemId"] = patch.get("relatedItemId")
    if "status" in patch:
        updated["status"] = normalize_item_status(patch.get("status"), default=item["status"])
    updated["updatedAt"] = str(patch.get("updatedAt") or iso_now())
    return updated


def _find_item_index(snapshot: ThreadSnapshotV2, item_id: str) -> int | None:
    for index, item in enumerate(snapshot.get("items", [])):
        if str(item.get("id") or "") == item_id:
            return index
    return None


def _validate_upsert_immutable_fields(existing: ConversationItem, incoming: ConversationItem) -> None:
    for key in IMMUTABLE_UPSERT_FIELDS:
        if key not in existing and key not in incoming:
            continue
        if existing.get(key) != incoming.get(key):
            raise ConversationStreamMismatch()


def _next_sequence(snapshot: ThreadSnapshotV2) -> int:
    return max((int(item.get("sequence") or 0) for item in snapshot.get("items", [])), default=0) + 1


def _finalize_open_items(
    snapshot: ThreadSnapshotV2,
    *,
    turn_id: str,
    status: str,
) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    updated = copy_snapshot(snapshot)
    events: list[dict[str, Any]] = []
    for item in list(updated.get("items", [])):
        if str(item.get("turnId") or "") != turn_id:
            continue
        current_status = str(item.get("status") or "").strip()
        if current_status not in {"pending", "in_progress"}:
            continue
        updated, patch_events = patch_item(
            updated,
            str(item.get("id") or ""),
            {
                "kind": str(item.get("kind") or ""),
                "status": status,
                "updatedAt": iso_now(),
            },
        )
        events.extend(patch_events)
    return updated, events


def _extract_output_files(raw: Any) -> list[ToolOutputFile]:
    files: list[ToolOutputFile] = []
    if not isinstance(raw, list):
        return files
    for item in raw:
        normalized = normalize_tool_output_file(item)
        if normalized is not None:
            files.append(normalized)
    return files


def _tool_change_kind_to_change_type(kind: str) -> str:
    if kind == "add":
        return "created"
    if kind == "delete":
        return "deleted"
    return "updated"


def _tool_changes_from_output_files(files: list[ToolOutputFile]) -> list[ToolChange]:
    changes: list[ToolChange] = []
    for file in files:
        kind = str(file.get("kind") or "").strip().lower()
        if kind not in {"add", "modify", "delete"}:
            change_type = str(file.get("changeType") or "updated").strip().lower()
            if change_type in {"created", "create", "add"}:
                kind = "add"
            elif change_type in {"deleted", "delete", "remove", "removed"}:
                kind = "delete"
            else:
                kind = "modify"
        changes.append(
            {
                "path": str(file.get("path") or ""),
                "kind": kind,  # type: ignore[typeddict-item]
                "diff": file.get("diff") if isinstance(file.get("diff"), str) else None,
                "summary": file.get("summary") if isinstance(file.get("summary"), str) else None,
            }
        )
    return [change for change in changes if str(change.get("path") or "").strip()]


def _output_files_from_tool_changes(changes: list[ToolChange]) -> list[ToolOutputFile]:
    files: list[ToolOutputFile] = []
    for change in changes:
        path = str(change.get("path") or "").strip()
        if not path:
            continue
        kind = str(change.get("kind") or "modify").strip().lower()
        if kind not in {"add", "modify", "delete"}:
            kind = "modify"
        file_entry: ToolOutputFile = {
            "path": path,
            "changeType": _tool_change_kind_to_change_type(kind),  # type: ignore[typeddict-item]
            "summary": change.get("summary") if isinstance(change.get("summary"), str) else None,
        }
        if isinstance(change.get("diff"), str) and str(change.get("diff") or "").strip():
            file_entry["diff"] = str(change.get("diff"))
        files.append(file_entry)
    return files


def _extract_tool_changes(raw: Any) -> list[ToolChange]:
    changes: list[ToolChange] = []
    if not isinstance(raw, list):
        return changes
    for item in raw:
        normalized = normalize_tool_change(item)
        if normalized is not None:
            changes.append(normalized)
    return changes


def _extract_terminal_interaction_text(payload: Any) -> str:
    if isinstance(payload, dict):
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


def _format_terminal_interaction_block(*, current_output: str, payload: Any) -> str:
    raw_text = _extract_terminal_interaction_text(payload)
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    prefix = "" if not current_output or current_output.endswith("\n") else "\n"
    if not normalized:
        return f"{prefix}[stdin]\n"
    return f"{prefix}[stdin]\n{normalized}\n"
