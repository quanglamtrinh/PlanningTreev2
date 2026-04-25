from __future__ import annotations

from typing import Any

from backend.session_core_v2.thread_store.metadata_store import ThreadMetadataStore
from backend.session_core_v2.thread_store.rollout_recorder import ThreadRolloutRecorder
from backend.session_core_v2.thread_store.turn_builder import build_turns_from_rollout_items


def read_native_thread(
    *,
    metadata_store: ThreadMetadataStore,
    rollout_recorder: ThreadRolloutRecorder,
    thread_id: str,
    include_history: bool = False,
) -> dict[str, Any]:
    metadata = metadata_store.get(thread_id)
    if metadata is None:
        raise FileNotFoundError(f"no rollout found for thread id {thread_id}")
    status = _thread_status_for_api(metadata.status)
    thread: dict[str, Any] = {
        "id": metadata.thread_id,
        "name": metadata.title,
        "preview": None,
        "modelProvider": "unknown",
        "cwd": "",
        "path": metadata.rollout_path,
        "ephemeral": False,
        "archived": metadata.archived_at_ms is not None,
        "status": status,
        "createdAt": metadata.created_at_ms,
        "updatedAt": metadata.updated_at_ms,
        "metadata": {
            "rolloutPath": metadata.rollout_path,
            "nativeSessionId": metadata.native_session_id,
            "forkedFromId": metadata.forked_from_id,
            "projectId": metadata.project_id,
        },
        "turns": [],
    }
    if include_history:
        items = rollout_recorder.load_items(thread_id)
        thread["turns"] = _turns_for_api(
            thread_id=metadata.thread_id,
            turns=build_turns_from_rollout_items(items),
        )
    return {"thread": thread}


def _thread_status_for_api(status: str) -> dict[str, Any]:
    if status == "running":
        return {"type": "active", "activeFlags": []}
    if status == "failed":
        return {"type": "systemError"}
    if status == "notLoaded":
        return {"type": "notLoaded"}
    return {"type": "idle"}


def _turns_for_api(*, thread_id: str, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for turn in turns:
        payload = dict(turn)
        payload["threadId"] = str(payload.get("threadId") or thread_id)
        payload.setdefault("status", "inProgress")
        payload.setdefault("lastCodexStatus", payload["status"] if payload["status"] in {"inProgress", "completed", "failed", "interrupted"} else None)
        payload.setdefault("startedAtMs", 0)
        payload.setdefault("completedAtMs", None)
        payload.setdefault("error", None)
        items = payload.get("items")
        payload["items"] = items if isinstance(items, list) else []
        normalized.append(payload)
    return normalized
