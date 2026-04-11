from __future__ import annotations

import copy
from typing import Any, cast

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import (
    ConversationItem,
    ItemPatch,
    PendingUserInputRequest,
    ThreadSnapshotV2,
)
from backend.conversation.domain.types_v3 import (
    ConversationItemV3,
    DiffChangeV3,
    DiffItemV3,
    ErrorItemV3,
    ExploreItemV3,
    ItemPatchV3,
    MessageItemV3,
    PendingUserInputRequestV3,
    ReasoningItemV3,
    ReviewItemV3,
    StatusItemV3,
    ThreadSnapshotV3,
    ToolItemV3,
    UiSignalsV3,
    UserInputAnswerV3,
    UserInputItemV3,
    copy_snapshot_v3,
    default_plan_ready_signal_v3,
    normalize_thread_role_v3,
)
from backend.storage.file_utils import iso_now


def _normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value.strip() else None


def _normalize_item_status(value: Any, *, default: str = "pending") -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in {
            "pending",
            "in_progress",
            "completed",
            "failed",
            "cancelled",
            "requested",
            "answer_submitted",
            "answered",
            "stale",
        }:
            return normalized
    return default


def _normalize_item_source(value: Any, *, default: str = "backend") -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in {"upstream", "backend", "local"}:
            return normalized
    return default


def _normalize_item_tone(value: Any, *, default: str = "neutral") -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in {"neutral", "info", "success", "warning", "danger", "muted"}:
            return normalized
    return default


_HIDDEN_AUDIT_SYSTEM_MESSAGE_IDS = {
    "audit-record:frame",
    "audit-record:spec",
    "review-context:instructions",
}


def _is_hidden_audit_system_item(raw_item: dict[str, Any]) -> bool:
    if str(raw_item.get("kind") or "").strip() != "message":
        return False
    if str(raw_item.get("role") or "").strip() != "system":
        return False
    item_id = str(raw_item.get("id") or "").strip()
    if item_id in _HIDDEN_AUDIT_SYSTEM_MESSAGE_IDS:
        return True
    metadata = raw_item.get("metadata")
    if isinstance(metadata, dict) and _is_truthy_flag(metadata.get("workflowReviewGuidance")):
        return True
    return False


def _render_plan_text(item: dict[str, Any]) -> str:
    base_text = str(item.get("text") or "").strip()
    steps = item.get("steps")
    if not isinstance(steps, list) or not steps:
        return base_text
    rendered_steps: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_text = str(step.get("text") or "").strip()
        if not step_text:
            continue
        step_status = str(step.get("status") or "pending").strip()
        rendered_steps.append(f"- [{step_status}] {step_text}")
    if not rendered_steps:
        return base_text
    if base_text:
        return f"{base_text}\n\n{chr(10).join(rendered_steps)}"
    return "\n".join(rendered_steps)


def _is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "on"}
    return False


def _normalize_diff_change_kind(
    value: Any,
    *,
    fallback: str = "modify",
) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"add", "create", "created", "new"}:
            return "add"
        if normalized in {"delete", "deleted", "remove", "removed"}:
            return "delete"
        if normalized in {"modify", "modified", "update", "updated", "change", "changed"}:
            return "modify"
    return fallback


def _diff_change_kind_to_change_type(kind: str) -> str:
    if kind == "add":
        return "created"
    if kind == "delete":
        return "deleted"
    return "updated"


def _diff_change_type_to_kind(value: Any, *, fallback: str = "modify") -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"created", "create", "add"}:
            return "add"
        if normalized in {"deleted", "delete", "remove", "removed"}:
            return "delete"
        if normalized in {"updated", "update", "modify", "modified", "change", "changed"}:
            return "modify"
    return fallback


def _normalize_diff_change(raw: Any) -> DiffChangeV3 | None:
    if not isinstance(raw, dict):
        return None
    path = _normalize_optional_string(raw.get("path"))
    if not path:
        return None
    kind = _normalize_diff_change_kind(
        raw.get("kind")
        or raw.get("changeKind")
        or raw.get("change_kind")
        or raw.get("changeType")
        or raw.get("change_type"),
        fallback="modify",
    )
    diff_text = _normalize_optional_text(raw.get("diff") if "diff" in raw else raw.get("patchText") or raw.get("patch_text"))
    return cast(
        DiffChangeV3,
        {
            "path": path,
            "kind": kind,
            "diff": diff_text,
            "summary": _normalize_optional_string(raw.get("summary")),
        },
    )


def _diff_changes_from_raw(raw_changes: Any) -> list[DiffChangeV3]:
    if not isinstance(raw_changes, list):
        return []
    changes: list[DiffChangeV3] = []
    for raw_change in raw_changes:
        normalized = _normalize_diff_change(raw_change)
        if normalized is not None:
            changes.append(normalized)
    return changes


def _diff_changes_from_tool_output_files(raw_files: Any) -> list[DiffChangeV3]:
    if not isinstance(raw_files, list):
        return []
    changes: list[DiffChangeV3] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        path = _normalize_optional_string(raw_file.get("path"))
        if not path:
            continue
        kind = _normalize_diff_change_kind(
            raw_file.get("kind")
            or raw_file.get("changeKind")
            or raw_file.get("change_kind")
            or raw_file.get("changeType")
            or raw_file.get("change_type"),
            fallback=_diff_change_type_to_kind(raw_file.get("changeType"), fallback="modify"),
        )
        diff_text = _normalize_optional_text(raw_file.get("diff") if "diff" in raw_file else raw_file.get("patchText") or raw_file.get("patch_text"))
        changes.append(
            cast(
                DiffChangeV3,
                {
                    "path": path,
                    "kind": kind,
                    "diff": diff_text,
                    "summary": _normalize_optional_string(raw_file.get("summary")),
                },
            )
        )
    return changes


def _diff_files_from_changes(changes: list[DiffChangeV3]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for change in changes:
        path = _normalize_optional_string(change.get("path"))
        if not path:
            continue
        kind = _normalize_diff_change_kind(change.get("kind"), fallback="modify")
        files.append(
            {
                "path": path,
                "changeType": _diff_change_kind_to_change_type(kind),
                "summary": _normalize_optional_string(change.get("summary")),
                "patchText": _normalize_optional_text(change.get("diff")),
            }
        )
    return files


def _diff_files_from_tool_output_files(raw_files: Any) -> list[dict[str, Any]]:
    return _diff_files_from_changes(_diff_changes_from_tool_output_files(raw_files))


def _diff_changes_from_v2_file_change_tool(source: dict[str, Any]) -> list[DiffChangeV3]:
    if isinstance(source.get("changes"), list):
        return _diff_changes_from_raw(source.get("changes"))
    if isinstance(source.get("files"), list):
        return _diff_changes_from_raw(source.get("files"))
    return _diff_changes_from_tool_output_files(source.get("outputFiles"))


def convert_item_v2_to_v3(item: ConversationItem | dict[str, Any]) -> ConversationItemV3:
    source = cast(dict[str, Any], item)
    kind = str(source.get("kind") or "").strip()
    now = iso_now()
    base: dict[str, Any] = {
        "id": str(source.get("id") or ""),
        "threadId": _normalize_optional_string(source.get("threadId")) or "",
        "turnId": _normalize_optional_string(source.get("turnId")),
        "sequence": int(source.get("sequence") or 0),
        "createdAt": source.get("createdAt") if isinstance(source.get("createdAt"), str) else now,
        "updatedAt": source.get("updatedAt") if isinstance(source.get("updatedAt"), str) else now,
        "status": _normalize_item_status(source.get("status"), default="pending"),
        "source": _normalize_item_source(source.get("source"), default="backend"),
        "tone": _normalize_item_tone(source.get("tone"), default="neutral"),
        "metadata": copy.deepcopy(source.get("metadata")) if isinstance(source.get("metadata"), dict) else {},
    }
    if kind == "message":
        role = str(source.get("role") or "assistant").strip()
        if role not in {"user", "assistant", "system"}:
            role = "assistant"
        metadata = cast(dict[str, Any], base.get("metadata") if isinstance(base.get("metadata"), dict) else {})
        if _is_truthy_flag(metadata.get("workflowReviewSummary")):
            review_metadata = copy.deepcopy(metadata)
            review_metadata["v2Kind"] = "message"
            review_metadata["semanticKind"] = "workflowReviewSummary"
            return cast(
                ReviewItemV3,
                {
                    **base,
                    "kind": "review",
                    "metadata": review_metadata,
                    "title": "Review summary",
                    "text": str(source.get("text") or ""),
                    "disposition": None,
                },
            )
        if role == "system" and _is_truthy_flag(metadata.get("workflowReviewGuidance")):
            explore_metadata = copy.deepcopy(metadata)
            explore_metadata["v2Kind"] = "message"
            explore_metadata["semanticKind"] = "workflowReviewGuidance"
            return cast(
                ExploreItemV3,
                {
                    **base,
                    "kind": "explore",
                    "metadata": explore_metadata,
                    "title": "Review guidance",
                    "text": str(source.get("text") or ""),
                },
            )
        return cast(
            MessageItemV3,
            {
                **base,
                "kind": "message",
                "role": role,
                "text": str(source.get("text") or ""),
                "format": "markdown",
            },
        )
    if kind == "reasoning":
        return cast(
            ReasoningItemV3,
            {
                **base,
                "kind": "reasoning",
                "summaryText": str(source.get("summaryText") or ""),
                "detailText": _normalize_optional_string(source.get("detailText")),
            },
        )
    if kind == "tool":
        tool_type = str(source.get("toolType") or "generic").strip()
        if tool_type not in {"commandExecution", "fileChange", "generic"}:
            tool_type = "generic"
        if tool_type == "fileChange":
            metadata = cast(dict[str, Any], base.get("metadata") if isinstance(base.get("metadata"), dict) else {})
            metadata = copy.deepcopy(metadata)
            metadata["v2Kind"] = "tool"
            metadata["semanticKind"] = "fileChange"
            changes = _diff_changes_from_v2_file_change_tool(source)
            return cast(
                DiffItemV3,
                {
                    **base,
                    "kind": "diff",
                    "metadata": metadata,
                    "title": _normalize_optional_string(source.get("title")) or "File changes",
                    "summaryText": _normalize_optional_string(source.get("outputText")),
                    "changes": changes,
                    "files": _diff_files_from_changes(changes),
                },
            )
        output_files: list[dict[str, Any]] = []
        for raw_file in source.get("outputFiles") if isinstance(source.get("outputFiles"), list) else []:
            if not isinstance(raw_file, dict):
                continue
            path = _normalize_optional_string(raw_file.get("path"))
            if not path:
                continue
            change_type = str(raw_file.get("changeType") or "updated").strip()
            if change_type not in {"created", "updated", "deleted"}:
                change_type = "updated"
            output_file: dict[str, Any] = {
                "path": path,
                "changeType": change_type,
                "summary": _normalize_optional_string(raw_file.get("summary")),
            }
            if any(key in raw_file for key in ("kind", "changeKind", "change_kind")):
                output_file["kind"] = _normalize_diff_change_kind(
                    raw_file.get("kind") or raw_file.get("changeKind") or raw_file.get("change_kind"),
                    fallback=_diff_change_type_to_kind(change_type, fallback="modify"),
                )
            diff_text = _normalize_optional_text(raw_file.get("diff") if "diff" in raw_file else raw_file.get("patchText") or raw_file.get("patch_text"))
            if diff_text is not None:
                output_file["diff"] = diff_text
            output_files.append(output_file)
        return cast(
            ToolItemV3,
            {
                **base,
                "kind": "tool",
                "toolType": tool_type,
                "title": str(source.get("title") or ""),
                "toolName": _normalize_optional_string(source.get("toolName")),
                "callId": _normalize_optional_string(source.get("callId")),
                "argumentsText": _normalize_optional_string(source.get("argumentsText")),
                "outputText": str(source.get("outputText") or ""),
                "outputFiles": output_files,
                "exitCode": source.get("exitCode") if isinstance(source.get("exitCode"), int) else None,
            },
        )
    if kind == "plan":
        metadata = copy.deepcopy(base["metadata"])
        metadata["v2Kind"] = "plan"
        metadata["semanticKind"] = "plan"
        return cast(
            ReviewItemV3,
            {
                **base,
                "kind": "review",
                "metadata": metadata,
                "title": _normalize_optional_string(source.get("title")) or "Plan",
                "text": _render_plan_text(source),
                "disposition": None,
            },
        )
    if kind == "userInput":
        questions = source.get("questions") if isinstance(source.get("questions"), list) else []
        answers = source.get("answers") if isinstance(source.get("answers"), list) else []
        return cast(
            UserInputItemV3,
            {
                **base,
                "kind": "userInput",
                "requestId": str(source.get("requestId") or ""),
                "title": _normalize_optional_string(source.get("title")),
                "questions": copy.deepcopy(questions),
                "answers": copy.deepcopy(answers),
                "requestedAt": source.get("requestedAt") if isinstance(source.get("requestedAt"), str) else str(base["createdAt"]),
                "resolvedAt": _normalize_optional_string(source.get("resolvedAt")),
            },
        )
    if kind == "status":
        return cast(
            StatusItemV3,
            {
                **base,
                "kind": "status",
                "code": str(source.get("code") or ""),
                "label": str(source.get("label") or ""),
                "detail": _normalize_optional_string(source.get("detail")),
            },
        )
    if kind == "error":
        return cast(
            ErrorItemV3,
            {
                **base,
                "kind": "error",
                "code": str(source.get("code") or ""),
                "title": str(source.get("title") or ""),
                "message": str(source.get("message") or ""),
                "recoverable": bool(source.get("recoverable")),
                "relatedItemId": _normalize_optional_string(source.get("relatedItemId")),
            },
        )
    metadata = copy.deepcopy(base["metadata"])
    metadata["sourceKind"] = kind or "unknown"
    return cast(
        ExploreItemV3,
        {
            **base,
            "kind": "explore",
            "metadata": metadata,
            "title": kind or "Unknown item",
            "text": str(source),
        },
    )


def convert_pending_request_v2_to_v3(raw: PendingUserInputRequest | dict[str, Any]) -> PendingUserInputRequestV3 | None:
    source = cast(dict[str, Any], raw)
    request_id = _normalize_optional_string(source.get("requestId"))
    item_id = _normalize_optional_string(source.get("itemId"))
    thread_id = _normalize_optional_string(source.get("threadId"))
    if not request_id or not item_id or not thread_id:
        return None
    status = str(source.get("status") or "requested").strip()
    if status not in {"requested", "answer_submitted", "answered", "stale"}:
        status = "requested"
    answers = source.get("answers") if isinstance(source.get("answers"), list) else []
    return {
        "requestId": request_id,
        "itemId": item_id,
        "threadId": thread_id,
        "turnId": _normalize_optional_string(source.get("turnId")),
        "status": cast(Any, status),
        "createdAt": source.get("createdAt") if isinstance(source.get("createdAt"), str) else iso_now(),
        "submittedAt": _normalize_optional_string(source.get("submittedAt")),
        "resolvedAt": _normalize_optional_string(source.get("resolvedAt")),
        "answers": copy.deepcopy(answers),
    }


def _derive_plan_ready(snapshot: ThreadSnapshotV3) -> dict[str, Any]:
    latest_plan_like: ReviewItemV3 | None = None
    for item in snapshot.get("items", []):
        if item.get("kind") != "review":
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("v2Kind") or "") != "plan":
            continue
        if latest_plan_like is None or int(item.get("sequence") or 0) >= int(latest_plan_like.get("sequence") or 0):
            latest_plan_like = cast(ReviewItemV3, item)
    if latest_plan_like is None:
        return default_plan_ready_signal_v3()
    status = str(latest_plan_like.get("status") or "").strip()
    text = str(latest_plan_like.get("text") or "").strip()
    failed = status == "failed"
    ready = status == "completed" and bool(text)
    return {
        "planItemId": str(latest_plan_like.get("id") or "") or None,
        "revision": int(latest_plan_like.get("sequence") or 0) or None,
        "ready": ready,
        "failed": failed,
    }


def build_snapshot_v3_from_v2(snapshot: ThreadSnapshotV2 | dict[str, Any]) -> ThreadSnapshotV3:
    source = cast(dict[str, Any], snapshot)
    thread_role = normalize_thread_role_v3(source.get("threadRole"), default="execution")
    items: list[ConversationItemV3] = []
    for raw_item in source.get("items") if isinstance(source.get("items"), list) else []:
        if not isinstance(raw_item, dict):
            continue
        if thread_role == "audit" and _is_hidden_audit_system_item(raw_item):
            continue
        items.append(convert_item_v2_to_v3(raw_item))
    items.sort(key=lambda current: (int(current.get("sequence") or 0), str(current.get("id") or "")))

    requests: list[PendingUserInputRequestV3] = []
    for raw_request in source.get("pendingRequests") if isinstance(source.get("pendingRequests"), list) else []:
        if not isinstance(raw_request, dict):
            continue
        normalized_request = convert_pending_request_v2_to_v3(raw_request)
        if normalized_request is not None:
            requests.append(normalized_request)

    now = iso_now()
    snapshot_v3: ThreadSnapshotV3 = {
        "projectId": str(source.get("projectId") or ""),
        "nodeId": str(source.get("nodeId") or ""),
        "threadRole": thread_role,
        "threadId": _normalize_optional_string(source.get("threadId")),
        "activeTurnId": _normalize_optional_string(source.get("activeTurnId")),
        "processingState": cast(
            Any,
            source.get("processingState")
            if source.get("processingState") in {"idle", "running", "waiting_user_input", "failed"}
            else "idle",
        ),
        "snapshotVersion": int(source.get("snapshotVersion") or 0),
        "createdAt": source.get("createdAt") if isinstance(source.get("createdAt"), str) else now,
        "updatedAt": source.get("updatedAt") if isinstance(source.get("updatedAt"), str) else now,
        "items": items,
        "uiSignals": {
            "planReady": default_plan_ready_signal_v3(),
            "activeUserInputRequests": requests,
        },
    }
    snapshot_v3["uiSignals"]["planReady"] = _derive_plan_ready(snapshot_v3)
    return snapshot_v3


def _find_item_index(snapshot: ThreadSnapshotV3, item_id: str) -> int | None:
    for index, item in enumerate(snapshot.get("items", [])):
        if str(item.get("id") or "") == item_id:
            return index
    return None


def _upsert_item(snapshot: ThreadSnapshotV3, item: ConversationItemV3) -> ThreadSnapshotV3:
    updated = copy_snapshot_v3(snapshot)
    index = _find_item_index(updated, str(item.get("id") or ""))
    if index is None:
        updated["items"].append(copy.deepcopy(item))
    else:
        updated["items"][index] = copy.deepcopy(item)
    updated["items"].sort(key=lambda current: (int(current.get("sequence") or 0), str(current.get("id") or "")))
    return updated


def _apply_patch_to_item(item: ConversationItemV3, patch: ItemPatchV3) -> ConversationItemV3:
    updated = cast(ConversationItemV3, copy.deepcopy(item))
    kind = str(updated.get("kind") or "")
    if kind == "message":
        if patch.get("textAppend"):
            updated["text"] = str(updated.get("text") or "") + str(patch.get("textAppend") or "")
    elif kind == "reasoning":
        if patch.get("summaryTextAppend"):
            updated["summaryText"] = str(updated.get("summaryText") or "") + str(patch.get("summaryTextAppend") or "")
        if patch.get("detailTextAppend"):
            updated["detailText"] = str(updated.get("detailText") or "") + str(patch.get("detailTextAppend") or "")
    elif kind == "tool":
        if "title" in patch:
            updated["title"] = str(patch.get("title") or "")
        if "argumentsText" in patch:
            updated["argumentsText"] = cast(Any, patch.get("argumentsText"))
        if patch.get("outputTextAppend"):
            updated["outputText"] = str(updated.get("outputText") or "") + str(patch.get("outputTextAppend") or "")
        if patch.get("outputFilesAppend"):
            updated["outputFiles"] = list(updated.get("outputFiles") or []) + list(cast(Any, patch.get("outputFilesAppend") or []))
        if "outputFilesReplace" in patch:
            updated["outputFiles"] = list(cast(Any, patch.get("outputFilesReplace") or []))
        if "exitCode" in patch:
            updated["exitCode"] = cast(Any, patch.get("exitCode"))
    elif kind == "explore":
        if "title" in patch:
            updated["title"] = cast(Any, patch.get("title"))
        if patch.get("textAppend"):
            updated["text"] = str(updated.get("text") or "") + str(patch.get("textAppend") or "")
    elif kind == "userInput":
        if "answersReplace" in patch:
            updated["answers"] = list(cast(Any, patch.get("answersReplace") or []))
        if "resolvedAt" in patch:
            updated["resolvedAt"] = cast(Any, patch.get("resolvedAt"))
    elif kind == "review":
        if "title" in patch:
            updated["title"] = cast(Any, patch.get("title"))
        if patch.get("textAppend"):
            updated["text"] = str(updated.get("text") or "") + str(patch.get("textAppend") or "")
        if "disposition" in patch:
            updated["disposition"] = cast(Any, patch.get("disposition"))
    elif kind == "diff":
        if "title" in patch:
            updated["title"] = cast(Any, patch.get("title"))
        if "summaryText" in patch:
            updated["summaryText"] = cast(Any, patch.get("summaryText"))
        has_current_changes = isinstance(updated.get("changes"), list)
        current_changes = _diff_changes_from_raw(updated.get("changes")) if has_current_changes else []
        if not has_current_changes:
            current_changes = _diff_changes_from_tool_output_files(updated.get("files"))

        next_changes = current_changes
        if "changesReplace" in patch:
            next_changes = _diff_changes_from_raw(patch.get("changesReplace"))
        elif patch.get("changesAppend"):
            next_changes = current_changes + _diff_changes_from_raw(patch.get("changesAppend"))
        elif "filesReplace" in patch:
            next_changes = _diff_changes_from_tool_output_files(patch.get("filesReplace"))
        elif patch.get("filesAppend"):
            next_changes = current_changes + _diff_changes_from_tool_output_files(patch.get("filesAppend"))

        updated["changes"] = next_changes
        updated["files"] = _diff_files_from_changes(next_changes)
    elif kind == "status":
        if "label" in patch:
            updated["label"] = str(patch.get("label") or "")
        if "detail" in patch:
            updated["detail"] = cast(Any, patch.get("detail"))
    elif kind == "error":
        if "message" in patch:
            updated["message"] = str(patch.get("message") or "")
        if "relatedItemId" in patch:
            updated["relatedItemId"] = cast(Any, patch.get("relatedItemId"))

    if "status" in patch:
        updated["status"] = cast(Any, _normalize_item_status(patch.get("status"), default=str(updated.get("status") or "pending")))
    updated["updatedAt"] = str(patch.get("updatedAt") or iso_now())
    return updated


def _patch_item(snapshot: ThreadSnapshotV3, item_id: str, patch: ItemPatchV3) -> ThreadSnapshotV3:
    updated = copy_snapshot_v3(snapshot)
    index = _find_item_index(updated, item_id)
    if index is None:
        return updated
    current = updated["items"][index]
    if str(current.get("kind") or "") != str(patch.get("kind") or ""):
        return updated
    updated["items"][index] = _apply_patch_to_item(current, patch)
    updated["items"].sort(key=lambda current_item: (int(current_item.get("sequence") or 0), str(current_item.get("id") or "")))
    return updated


def _upsert_pending_request(
    requests: list[PendingUserInputRequestV3],
    request: PendingUserInputRequestV3,
) -> list[PendingUserInputRequestV3]:
    next_requests = [copy.deepcopy(current) for current in requests]
    for index, current in enumerate(next_requests):
        if str(current.get("requestId") or "") == str(request.get("requestId") or ""):
            next_requests[index] = copy.deepcopy(request)
            return next_requests
    next_requests.append(copy.deepcopy(request))
    return next_requests


def _resolve_pending_request(
    requests: list[PendingUserInputRequestV3],
    *,
    request_id: str,
    status: str,
    answers: list[UserInputAnswerV3],
    resolved_at: str | None,
) -> list[PendingUserInputRequestV3]:
    next_requests = [copy.deepcopy(current) for current in requests]
    for current in next_requests:
        if str(current.get("requestId") or "") != request_id:
            continue
        current["status"] = cast(Any, status if status in {"requested", "answer_submitted", "answered", "stale"} else "requested")
        current["answers"] = copy.deepcopy(answers)
        current["resolvedAt"] = resolved_at
    return next_requests


def _build_plan_ready_event(snapshot: ThreadSnapshotV3) -> dict[str, Any]:
    return {
        "type": event_types.CONVERSATION_UI_PLAN_READY_V3,
        "payload": {"planReady": copy.deepcopy(snapshot["uiSignals"]["planReady"])},
    }


def _build_user_input_signal_event(snapshot: ThreadSnapshotV3) -> dict[str, Any]:
    return {
        "type": event_types.CONVERSATION_UI_USER_INPUT_V3,
        "payload": {"activeUserInputRequests": copy.deepcopy(snapshot["uiSignals"]["activeUserInputRequests"])},
    }


def _map_patch_from_v2(
    patch_v2: ItemPatch | dict[str, Any],
    *,
    current_item: ConversationItemV3,
) -> ItemPatchV3:
    source = cast(dict[str, Any], patch_v2)
    v2_kind = str(source.get("kind") or "").strip()
    current_kind = str(current_item.get("kind") or "")

    if v2_kind == "plan":
        mapped = {
            "kind": "review",
            "title": source.get("title"),
            "textAppend": str(source.get("textAppend") or ""),
            "status": source.get("status"),
            "updatedAt": str(source.get("updatedAt") or iso_now()),
        }
        return cast(ItemPatchV3, mapped)

    if v2_kind == "message":
        if current_kind == "review":
            return cast(
                ItemPatchV3,
                {
                    "kind": "review",
                    "textAppend": str(source.get("textAppend") or ""),
                    "status": source.get("status"),
                    "updatedAt": str(source.get("updatedAt") or iso_now()),
                },
            )
        if current_kind == "explore":
            return cast(
                ItemPatchV3,
                {
                    "kind": "explore",
                    "textAppend": str(source.get("textAppend") or ""),
                    "status": source.get("status"),
                    "updatedAt": str(source.get("updatedAt") or iso_now()),
                },
            )
        return cast(
            ItemPatchV3,
            {
                "kind": "message",
                "textAppend": str(source.get("textAppend") or ""),
                "status": source.get("status"),
                "updatedAt": str(source.get("updatedAt") or iso_now()),
            },
        )
    if v2_kind == "reasoning":
        return cast(
            ItemPatchV3,
            {
                "kind": "reasoning",
                "summaryTextAppend": str(source.get("summaryTextAppend") or ""),
                "detailTextAppend": str(source.get("detailTextAppend") or ""),
                "status": source.get("status"),
                "updatedAt": str(source.get("updatedAt") or iso_now()),
            },
        )
    if v2_kind == "tool":
        if current_kind == "diff":
            mapped_patch: dict[str, Any] = {
                "kind": "diff",
                "status": source.get("status"),
                "updatedAt": str(source.get("updatedAt") or iso_now()),
            }
            if "title" in source:
                mapped_patch["title"] = source.get("title")
            append_changes: list[DiffChangeV3] | None = None
            if "changesAppend" in source:
                append_changes = _diff_changes_from_raw(source.get("changesAppend"))
            elif "outputFilesAppend" in source:
                append_changes = _diff_changes_from_tool_output_files(source.get("outputFilesAppend"))
            if append_changes is not None:
                mapped_patch["changesAppend"] = append_changes
                mapped_patch["filesAppend"] = _diff_files_from_changes(append_changes)

            replace_changes: list[DiffChangeV3] | None = None
            if "changesReplace" in source:
                replace_changes = _diff_changes_from_raw(source.get("changesReplace"))
            elif "outputFilesReplace" in source:
                replace_changes = _diff_changes_from_tool_output_files(source.get("outputFilesReplace"))
            if replace_changes is not None:
                mapped_patch["changesReplace"] = replace_changes
                mapped_patch["filesReplace"] = _diff_files_from_changes(replace_changes)
            if "outputTextAppend" in source:
                current_summary = _normalize_optional_string(cast(dict[str, Any], current_item).get("summaryText"))
                mapped_patch["summaryText"] = f"{current_summary or ''}{str(source.get('outputTextAppend') or '')}" or None
            return cast(ItemPatchV3, mapped_patch)
        mapped_patch = cast(
            dict[str, Any],
            {
                "kind": "tool",
                "status": source.get("status"),
                "updatedAt": str(source.get("updatedAt") or iso_now()),
            },
        )
        if "title" in source:
            mapped_patch["title"] = source.get("title")
        if "argumentsText" in source:
            mapped_patch["argumentsText"] = source.get("argumentsText")
        if "outputTextAppend" in source:
            mapped_patch["outputTextAppend"] = str(source.get("outputTextAppend") or "")
        if "outputFilesAppend" in source:
            mapped_patch["outputFilesAppend"] = copy.deepcopy(source.get("outputFilesAppend") or [])
        if "outputFilesReplace" in source:
            mapped_patch["outputFilesReplace"] = copy.deepcopy(source.get("outputFilesReplace") or [])
        if "exitCode" in source:
            mapped_patch["exitCode"] = source.get("exitCode")
        return cast(ItemPatchV3, mapped_patch)
    if v2_kind == "userInput":
        return cast(
            ItemPatchV3,
            {
                "kind": "userInput",
                "answersReplace": copy.deepcopy(source.get("answersReplace") or []),
                "resolvedAt": source.get("resolvedAt"),
                "status": source.get("status"),
                "updatedAt": str(source.get("updatedAt") or iso_now()),
            },
        )
    if v2_kind == "status":
        return cast(
            ItemPatchV3,
            {
                "kind": "status",
                "label": source.get("label"),
                "detail": source.get("detail"),
                "status": source.get("status"),
                "updatedAt": str(source.get("updatedAt") or iso_now()),
            },
        )
    if v2_kind == "error":
        return cast(
            ItemPatchV3,
            {
                "kind": "error",
                "message": source.get("message"),
                "relatedItemId": source.get("relatedItemId"),
                "status": source.get("status"),
                "updatedAt": str(source.get("updatedAt") or iso_now()),
            },
        )

    fallback_patch = {
        "kind": current_kind,
        "status": source.get("status"),
        "updatedAt": str(source.get("updatedAt") or iso_now()),
    }
    return cast(ItemPatchV3, fallback_patch)


def _next_sequence(snapshot: ThreadSnapshotV3) -> int:
    return max((int(item.get("sequence") or 0) for item in snapshot.get("items", [])), default=0) + 1


def _synthesize_item_for_patch_v2(
    snapshot: ThreadSnapshotV3,
    *,
    item_id: str,
    patch_v2: ItemPatch | dict[str, Any],
) -> ConversationItemV3 | None:
    source = cast(dict[str, Any], patch_v2)
    v2_kind = str(source.get("kind") or "").strip()
    now = str(source.get("updatedAt") or snapshot.get("updatedAt") or iso_now())
    base: dict[str, Any] = {
        "id": item_id,
        "threadId": str(snapshot.get("threadId") or ""),
        "turnId": snapshot.get("activeTurnId"),
        "sequence": _next_sequence(snapshot),
        "createdAt": now,
        "updatedAt": now,
        "status": _normalize_item_status(source.get("status"), default="in_progress"),
        "source": "upstream",
        "tone": "neutral",
        "metadata": {},
    }
    if v2_kind == "reasoning":
        return cast(
            ReasoningItemV3,
            {
                **base,
                "kind": "reasoning",
                "summaryText": "",
                "detailText": None,
            },
        )
    if v2_kind == "message":
        return cast(
            MessageItemV3,
            {
                **base,
                "kind": "message",
                "role": "assistant",
                "text": "",
                "format": "markdown",
            },
        )
    if v2_kind == "tool":
        return cast(
            ToolItemV3,
            {
                **base,
                "kind": "tool",
                "toolType": "generic",
                "title": "",
                "toolName": None,
                "callId": None,
                "argumentsText": None,
                "outputText": "",
                "outputFiles": [],
                "exitCode": None,
            },
        )
    if v2_kind == "plan":
        return cast(
            ReviewItemV3,
            {
                **base,
                "kind": "review",
                "metadata": {"v2Kind": "plan"},
                "title": "Plan",
                "text": "",
                "disposition": None,
            },
        )
    return None


def project_v2_envelope_to_v3(
    snapshot: ThreadSnapshotV3,
    envelope_v2: dict[str, Any],
) -> tuple[ThreadSnapshotV3, list[dict[str, Any]]]:
    previous_snapshot = copy_snapshot_v3(snapshot)
    updated = copy_snapshot_v3(snapshot)
    events: list[dict[str, Any]] = []
    event_type = str(envelope_v2.get("type") or "").strip()
    payload = envelope_v2.get("payload")
    payload_dict = payload if isinstance(payload, dict) else {}

    if event_type == event_types.THREAD_SNAPSHOT:
        raw_snapshot = payload_dict.get("snapshot")
        if isinstance(raw_snapshot, dict):
            updated = build_snapshot_v3_from_v2(raw_snapshot)
        events.append(
            {
                "type": event_types.THREAD_SNAPSHOT_V3,
                "payload": {"snapshot": copy.deepcopy(updated)},
            }
        )
        events.append(_build_plan_ready_event(updated))
        events.append(_build_user_input_signal_event(updated))
        return updated, events

    if event_type == event_types.CONVERSATION_ITEM_UPSERT:
        raw_item = payload_dict.get("item")
        if isinstance(raw_item, dict):
            if normalize_thread_role_v3(updated.get("threadRole"), default="execution") == "audit" and _is_hidden_audit_system_item(raw_item):
                updated["uiSignals"]["planReady"] = _derive_plan_ready(updated)
                return updated, events
            item_v3 = convert_item_v2_to_v3(raw_item)
            updated = _upsert_item(updated, item_v3)
            events.append(
                {
                    "type": event_types.CONVERSATION_ITEM_UPSERT_V3,
                    "payload": {"item": copy.deepcopy(item_v3)},
                }
            )
    elif event_type == event_types.CONVERSATION_ITEM_PATCH:
        item_id = str(payload_dict.get("itemId") or "").strip()
        raw_patch = payload_dict.get("patch")
        if item_id and isinstance(raw_patch, dict):
            if normalize_thread_role_v3(updated.get("threadRole"), default="execution") == "audit" and item_id in _HIDDEN_AUDIT_SYSTEM_MESSAGE_IDS:
                updated["uiSignals"]["planReady"] = _derive_plan_ready(updated)
                return updated, events
            current_index = _find_item_index(updated, item_id)
            if current_index is None:
                synthesized_item = _synthesize_item_for_patch_v2(
                    updated,
                    item_id=item_id,
                    patch_v2=raw_patch,
                )
                if synthesized_item is not None:
                    updated = _upsert_item(updated, synthesized_item)
                    events.append(
                        {
                            "type": event_types.CONVERSATION_ITEM_UPSERT_V3,
                            "payload": {"item": copy.deepcopy(synthesized_item)},
                        }
                    )
                    current_index = _find_item_index(updated, item_id)
            if current_index is not None:
                current_item = updated["items"][current_index]
                mapped_patch = _map_patch_from_v2(raw_patch, current_item=current_item)
                if str(mapped_patch.get("kind") or "") == str(current_item.get("kind") or ""):
                    updated = _patch_item(updated, item_id, mapped_patch)
                    events.append(
                        {
                            "type": event_types.CONVERSATION_ITEM_PATCH_V3,
                            "payload": {"itemId": item_id, "patch": copy.deepcopy(mapped_patch)},
                        }
                    )
    elif event_type == event_types.THREAD_LIFECYCLE:
        processing_state = str(payload_dict.get("processingState") or "idle")
        if processing_state not in {"idle", "running", "waiting_user_input", "failed"}:
            processing_state = "idle"
        updated["processingState"] = cast(Any, processing_state)
        updated["activeTurnId"] = _normalize_optional_string(payload_dict.get("activeTurnId"))
        events.append(
            {
                "type": event_types.THREAD_LIFECYCLE_V3,
                "payload": {
                    "activeTurnId": updated.get("activeTurnId"),
                    "processingState": updated.get("processingState"),
                    "state": payload_dict.get("state"),
                    "detail": payload_dict.get("detail"),
                },
            }
        )
    elif event_type == event_types.CONVERSATION_REQUEST_USER_INPUT_REQUESTED:
        raw_pending = payload_dict.get("pendingRequest")
        pending = convert_pending_request_v2_to_v3(raw_pending) if isinstance(raw_pending, dict) else None
        if pending is not None:
            updated["uiSignals"]["activeUserInputRequests"] = _upsert_pending_request(
                updated["uiSignals"]["activeUserInputRequests"],
                pending,
            )
    elif event_type == event_types.CONVERSATION_REQUEST_USER_INPUT_RESOLVED:
        request_id = str(payload_dict.get("requestId") or "").strip()
        if request_id:
            raw_answers = payload_dict.get("answers")
            answers = cast(list[UserInputAnswerV3], copy.deepcopy(raw_answers) if isinstance(raw_answers, list) else [])
            status = str(payload_dict.get("status") or "answered")
            resolved_at = _normalize_optional_string(payload_dict.get("resolvedAt"))
            updated["uiSignals"]["activeUserInputRequests"] = _resolve_pending_request(
                updated["uiSignals"]["activeUserInputRequests"],
                request_id=request_id,
                status=status,
                answers=answers,
                resolved_at=resolved_at,
            )
    elif event_type == event_types.THREAD_ERROR:
        raw_error = payload_dict.get("errorItem")
        if isinstance(raw_error, dict):
            mapped_error = convert_item_v2_to_v3(raw_error)
            if mapped_error.get("kind") == "error":
                events.append(
                    {
                        "type": event_types.THREAD_ERROR_V3,
                        "payload": {"errorItem": copy.deepcopy(mapped_error)},
                    }
                )
    elif event_type == event_types.THREAD_RESET:
        updated["items"] = []
        updated["activeTurnId"] = None
        updated["processingState"] = cast(Any, "idle")
        updated["uiSignals"]["activeUserInputRequests"] = []
        updated["uiSignals"]["planReady"] = default_plan_ready_signal_v3()
        events.append(
            {
                "type": event_types.THREAD_SNAPSHOT_V3,
                "payload": {"snapshot": copy.deepcopy(updated)},
            }
        )
        events.append(_build_plan_ready_event(updated))
        events.append(_build_user_input_signal_event(updated))
        return updated, events

    updated["uiSignals"]["planReady"] = _derive_plan_ready(updated)
    previous_plan = previous_snapshot["uiSignals"]["planReady"]
    current_plan = updated["uiSignals"]["planReady"]
    if previous_plan != current_plan:
        events.append(_build_plan_ready_event(updated))

    previous_requests = previous_snapshot["uiSignals"]["activeUserInputRequests"]
    current_requests = updated["uiSignals"]["activeUserInputRequests"]
    if previous_requests != current_requests:
        events.append(_build_user_input_signal_event(updated))

    return updated, events


def project_v2_snapshot_to_v3(snapshot_v2: ThreadSnapshotV2 | dict[str, Any]) -> ThreadSnapshotV3:
    return build_snapshot_v3_from_v2(snapshot_v2)
