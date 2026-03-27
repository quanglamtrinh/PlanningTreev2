from __future__ import annotations

from typing import Any

from backend.errors.app_errors import ShapingFrozen
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage

AUDIT_FRAME_RECORD_MESSAGE_ID = "audit-record:frame"
AUDIT_SPEC_RECORD_MESSAGE_ID = "audit-record:spec"
AUDIT_ROLLUP_PACKAGE_MESSAGE_ID = "audit-package:rollup"
SYSTEM_MESSAGE_ROLE = "system"

_LOCAL_REVIEW_EXECUTION_STATUSES = {"completed", "review_pending", "review_accepted"}


def execution_status(exec_state: dict[str, Any] | None) -> str | None:
    if not isinstance(exec_state, dict):
        return None
    status = exec_state.get("status")
    return str(status) if isinstance(status, str) and status else None


def execution_started(exec_state: dict[str, Any] | None) -> bool:
    status = execution_status(exec_state)
    return status is not None and status != "idle"


def execution_completed(exec_state: dict[str, Any] | None) -> bool:
    status = execution_status(exec_state)
    return status in _LOCAL_REVIEW_EXECUTION_STATUSES


_FROZEN_STATUSES = {"executing", "completed", "review_pending", "review_accepted"}


def is_shaping_frozen(storage: Storage, project_id: str, node_id: str) -> bool:
    exec_state = storage.execution_state_store.read_state(project_id, node_id)
    if exec_state is None:
        return False
    status = exec_state.get("status")
    return isinstance(status, str) and status in _FROZEN_STATUSES


def require_shaping_not_frozen(
    storage: Storage,
    project_id: str,
    node_id: str,
    action: str,
) -> None:
    if is_shaping_frozen(storage, project_id, node_id):
        raise ShapingFrozen(action)


def audit_message_exists(
    storage: Storage,
    project_id: str,
    node_id: str,
    *,
    message_id: str,
) -> bool:
    session = storage.chat_state_store.read_session(project_id, node_id, thread_role="audit")
    return any(message.get("message_id") == message_id for message in session.get("messages", []))


def package_audit_ready(
    storage: Storage,
    project_id: str,
    node: dict[str, Any] | None,
    review_state: dict[str, Any] | None,
) -> bool:
    if not isinstance(node, dict) or not isinstance(review_state, dict):
        return False
    review_node_id = str(node.get("review_node_id") or "").strip()
    if not review_node_id:
        return False
    rollup = review_state.get("rollup", {})
    if not isinstance(rollup, dict) or rollup.get("status") != "accepted":
        return False
    return audit_message_exists(
        storage,
        project_id,
        str(node.get("node_id") or ""),
        message_id=AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
    )


def audit_writable(
    storage: Storage,
    project_id: str,
    node: dict[str, Any] | None,
    exec_state: dict[str, Any] | None,
    review_state: dict[str, Any] | None,
) -> bool:
    if execution_completed(exec_state):
        return True
    return package_audit_ready(storage, project_id, node, review_state)


def derive_execution_workflow_fields(
    storage: Storage,
    project_id: str,
    node_id: str,
    *,
    workflow: dict[str, Any],
    node: dict[str, Any] | None,
    exec_state: dict[str, Any] | None,
    review_state: dict[str, Any] | None,
    git_ready: bool | None = None,
) -> dict[str, Any]:
    shaping_frozen = is_shaping_frozen(storage, project_id, node_id)
    exec_status = execution_status(exec_state)
    started = execution_started(exec_state)
    completed = execution_completed(exec_state)

    node_kind = str((node or {}).get("node_kind") or "")
    node_status = str((node or {}).get("status") or "")
    child_ids = (node or {}).get("child_ids") or []
    is_leaf = isinstance(child_ids, list) and len(child_ids) == 0

    can_finish_task = (
        node_kind != "review"
        and bool(workflow.get("spec_confirmed"))
        and is_leaf
        and node_status in {"ready", "in_progress"}
        and not shaping_frozen
        and git_ready is not False
    )

    package_ready = package_audit_ready(storage, project_id, node, review_state)
    writable = False if node_kind == "review" else (completed or package_ready)

    review_status: str | None = None
    if node_kind == "review" and isinstance(review_state, dict):
        rollup = review_state.get("rollup", {})
        if isinstance(rollup, dict):
            status = rollup.get("status")
            review_status = str(status) if isinstance(status, str) and status else None

    can_accept_local = exec_status == "review_pending"

    auto_review = exec_state.get("auto_review") if isinstance(exec_state, dict) else None

    return {
        "execution_started": started,
        "execution_completed": completed,
        "shaping_frozen": shaping_frozen,
        "can_finish_task": can_finish_task,
        "can_accept_local_review": can_accept_local,
        "execution_status": exec_status,
        "audit_writable": writable,
        "package_audit_ready": package_ready,
        "review_status": review_status,
        "auto_review_status": auto_review.get("status") if isinstance(auto_review, dict) else None,
        "auto_review_summary": auto_review.get("summary") if isinstance(auto_review, dict) else None,
        "auto_review_overall_severity": auto_review.get("overall_severity") if isinstance(auto_review, dict) else None,
        "auto_review_overall_score": auto_review.get("overall_score") if isinstance(auto_review, dict) else None,
    }


def append_immutable_audit_record(
    storage: Storage,
    project_id: str,
    node_id: str,
    *,
    message_id: str,
    content: str,
) -> dict[str, Any]:
    with storage.project_lock(project_id):
        session = storage.chat_state_store.read_session(project_id, node_id, thread_role="audit")
        for message in session.get("messages", []):
            if message.get("message_id") == message_id:
                changed = False
                if message.get("role") != SYSTEM_MESSAGE_ROLE:
                    message["role"] = SYSTEM_MESSAGE_ROLE
                    changed = True
                if message.get("status") != "completed":
                    message["status"] = "completed"
                    changed = True
                if message.get("error") is not None:
                    message["error"] = None
                    changed = True
                if message.get("turn_id") is not None:
                    message["turn_id"] = None
                    changed = True
                if changed:
                    message["updated_at"] = iso_now()
                    return storage.chat_state_store.write_session(
                        project_id,
                        node_id,
                        session,
                        thread_role="audit",
                    )
                return session

        now = iso_now()
        session["messages"].append(
            {
                "message_id": message_id,
                "role": SYSTEM_MESSAGE_ROLE,
                "content": content,
                "status": "completed",
                "error": None,
                "turn_id": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        return storage.chat_state_store.write_session(
            project_id,
            node_id,
            session,
            thread_role="audit",
        )
