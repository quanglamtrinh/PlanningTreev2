from __future__ import annotations

import copy
from typing import Any

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import (
    ConversationItem,
    ItemPatch,
    PendingUserInputRequest,
    ThreadSnapshotV2,
    ToolOutputFile,
    UserInputAnswer,
    copy_snapshot,
    normalize_item,
    normalize_item_status,
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
        updated["items"][existing_index] = normalized
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
    if method == "item/fileChange/outputDelta":
        patch: dict[str, Any] = {
            "kind": "tool",
            "outputTextAppend": str(raw_event.get("params", {}).get("delta") or ""),
            "status": "in_progress",
            "updatedAt": str(raw_event.get("received_at") or iso_now()),
        }
        preview_files = _extract_output_files(raw_event.get("params", {}).get("files"))
        if preview_files:
            patch["outputFilesAppend"] = preview_files
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
        output_files = _extract_output_files(item.get("changes") or item.get("files"))
        if output_files:
            patch["outputFilesReplace"] = output_files
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
    status_type = str(status.get("type") or status.get("state") or "").strip() if isinstance(status, dict) else ""
    processing_state = snapshot.get("processingState") or "idle"
    if status_type in {"waiting_for_user_input", "waiting_user_input"}:
        processing_state = "waiting_user_input"
    elif status_type in {"running", "in_progress"}:
        processing_state = "running"
    elif status_type in {"failed", "error"}:
        processing_state = "failed"
    else:
        processing_state = "idle"
    return apply_lifecycle(
        snapshot,
        state=status_type or event_types.TURN_STARTED,
        processing_state=str(processing_state),
        active_turn_id=snapshot.get("activeTurnId"),
    )


def _apply_turn_completed(snapshot: ThreadSnapshotV2, raw_event: dict[str, Any]) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
    params = raw_event.get("params", {})
    turn_payload = params.get("turn") if isinstance(params, dict) else {}
    turn_status = str(turn_payload.get("status") or params.get("status") or "").strip() if isinstance(turn_payload, dict) else str(params.get("status") or "").strip()
    if turn_status in {"waiting_user_input", "waitingForUserInput"}:
        return apply_lifecycle(
            snapshot,
            state=event_types.WAITING_USER_INPUT,
            processing_state="waiting_user_input",
            active_turn_id=snapshot.get("activeTurnId"),
        )
    if turn_status in {"failed", "error", "interrupted", "cancelled"}:
        updated, events = apply_lifecycle(
            snapshot,
            state=event_types.TURN_FAILED,
            processing_state="idle",
            active_turn_id=None,
        )
        return updated, events
    return apply_lifecycle(
        snapshot,
        state=event_types.TURN_COMPLETED,
        processing_state="idle",
        active_turn_id=None,
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
        if patch.get("outputFilesAppend"):
            updated["outputFiles"] = list(updated.get("outputFiles") or []) + list(patch["outputFilesAppend"])
        if "outputFilesReplace" in patch:
            updated["outputFiles"] = list(patch.get("outputFilesReplace") or [])
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


def _next_sequence(snapshot: ThreadSnapshotV2) -> int:
    return max((int(item.get("sequence") or 0) for item in snapshot.get("items", [])), default=0) + 1


def _extract_output_files(raw: Any) -> list[ToolOutputFile]:
    files: list[ToolOutputFile] = []
    if not isinstance(raw, list):
        return files
    for item in raw:
        normalized = normalize_tool_output_file(item)
        if normalized is not None:
            files.append(normalized)
    return files
