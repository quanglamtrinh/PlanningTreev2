from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.services import planningtree_workspace
from backend.services.execution_gating import (
    AUDIT_FRAME_RECORD_MESSAGE_ID,
    AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
    AUDIT_SPEC_RECORD_MESSAGE_ID,
)
from backend.storage.file_utils import iso_now, load_json
from backend.storage.storage import Storage

SYSTEM_MESSAGE_ROLE = "system"

ASK_PLANNING_SEED_SPLIT_ITEM_MESSAGE_ID = "seed:ask_planning:split-item"
ASK_PLANNING_SEED_CHECKPOINT_MESSAGE_ID = "seed:ask_planning:checkpoint"

AUDIT_SEED_SPLIT_ITEM_MESSAGE_ID = "seed:audit:split-item"
AUDIT_SEED_CHECKPOINT_MESSAGE_ID = "seed:audit:checkpoint"
AUDIT_SEED_PARENT_CONTEXT_MESSAGE_ID = "seed:audit:parent-context"

ASK_PLANNING_IMMUTABLE_MESSAGE_IDS = frozenset(
    {
        ASK_PLANNING_SEED_SPLIT_ITEM_MESSAGE_ID,
        ASK_PLANNING_SEED_CHECKPOINT_MESSAGE_ID,
    }
)

AUDIT_IMMUTABLE_MESSAGE_IDS = frozenset(
    {
        AUDIT_SEED_SPLIT_ITEM_MESSAGE_ID,
        AUDIT_SEED_CHECKPOINT_MESSAGE_ID,
        AUDIT_SEED_PARENT_CONTEXT_MESSAGE_ID,
        AUDIT_FRAME_RECORD_MESSAGE_ID,
        AUDIT_SPEC_RECORD_MESSAGE_ID,
        AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
    }
)

_DEFAULT_FRAME_META = {
    "confirmed_revision": 0,
    "confirmed_at": None,
    "confirmed_content": "",
}


def ensure_thread_seeded_session(
    storage: Storage,
    *,
    project_id: str,
    node_id: str,
    thread_role: str,
    snapshot: dict[str, Any],
    node: dict[str, Any],
    session: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Insert immutable system seed messages for seeded thread roles.

    Seeds are write-once and ordered ahead of later chat discussion. Missing seeds are
    inserted without disturbing existing user/assistant messages.
    """

    if thread_role == "audit" and str(node.get("node_kind") or "").strip() == "review":
        return session, False

    immutable_ids = _immutable_ids_for_role(thread_role)
    seed_messages = build_thread_seed_messages(
        storage,
        project_id=project_id,
        node_id=node_id,
        thread_role=thread_role,
        snapshot=snapshot,
        node=node,
    )

    changed = False
    normalized_existing: list[dict[str, Any]] = []
    for raw in session.get("messages", []):
        if not isinstance(raw, dict):
            continue
        message = copy.deepcopy(raw)
        if str(message.get("message_id") or "") in immutable_ids:
            changed = _normalize_immutable_system_message(message) or changed
        normalized_existing.append(message)

    merged = _merge_seed_messages(
        seed_messages,
        normalized_existing,
        immutable_ids=immutable_ids,
    )
    if merged != session.get("messages", []):
        changed = True

    if not changed:
        return session, False

    updated = copy.deepcopy(session)
    updated["messages"] = merged
    return updated, True


def build_thread_seed_messages(
    storage: Storage,
    *,
    project_id: str,
    node_id: str,
    thread_role: str,
    snapshot: dict[str, Any],
    node: dict[str, Any],
) -> list[dict[str, Any]]:
    node_index = snapshot.get("tree_state", {}).get("node_index", {})
    if not isinstance(node_index, dict):
        node_index = {}

    if thread_role == "audit":
        return _build_audit_seed_messages(storage, project_id, snapshot, node_index, node)
    return []


def build_system_message(message_id: str, content: str) -> dict[str, Any]:
    now = iso_now()
    return {
        "message_id": message_id,
        "role": SYSTEM_MESSAGE_ROLE,
        "content": content,
        "status": "completed",
        "error": None,
        "turn_id": None,
        "created_at": now,
        "updated_at": now,
    }


def _immutable_ids_for_role(thread_role: str) -> frozenset[str]:
    if thread_role == "audit":
        return AUDIT_IMMUTABLE_MESSAGE_IDS
    return frozenset()


def _merge_seed_messages(
    seed_messages: list[dict[str, Any]],
    existing_messages: list[dict[str, Any]],
    *,
    immutable_ids: frozenset[str],
) -> list[dict[str, Any]]:
    if not seed_messages and not any(
        str(message.get("message_id") or "") in immutable_ids for message in existing_messages
    ):
        return existing_messages

    existing_by_id = {
        str(message.get("message_id") or ""): message
        for message in existing_messages
        if isinstance(message, dict)
    }
    merged: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for seed in seed_messages:
        message_id = str(seed.get("message_id") or "")
        if not message_id:
            continue
        merged.append(copy.deepcopy(existing_by_id.get(message_id, seed)))
        used_ids.add(message_id)

    for message in existing_messages:
        message_id = str(message.get("message_id") or "")
        if message_id in used_ids:
            continue
        if message_id in immutable_ids:
            merged.append(copy.deepcopy(message))
            used_ids.add(message_id)

    for message in existing_messages:
        message_id = str(message.get("message_id") or "")
        if message_id in used_ids:
            continue
        merged.append(copy.deepcopy(message))

    return merged


def _normalize_immutable_system_message(message: dict[str, Any]) -> bool:
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
    return changed


def _build_audit_seed_messages(
    storage: Storage,
    project_id: str,
    snapshot: dict[str, Any],
    node_index: dict[str, Any],
    node: dict[str, Any],
) -> list[dict[str, Any]]:
    if str(node.get("status") or "") == "locked":
        return []

    messages: list[dict[str, Any]] = []

    split_item = _build_audit_split_item_content(node)
    if split_item:
        messages.append(build_system_message(AUDIT_SEED_SPLIT_ITEM_MESSAGE_ID, split_item))

    checkpoint_context = _build_audit_checkpoint_content(storage, project_id, node_index, node)
    if checkpoint_context:
        messages.append(build_system_message(AUDIT_SEED_CHECKPOINT_MESSAGE_ID, checkpoint_context))

    parent_context = _build_audit_parent_context_content(node_index, node)
    if parent_context:
        messages.append(build_system_message(AUDIT_SEED_PARENT_CONTEXT_MESSAGE_ID, parent_context))

    return messages


def _build_ask_planning_seed_messages(
    storage: Storage,
    project_id: str,
    node_index: dict[str, Any],
    node: dict[str, Any],
) -> list[dict[str, Any]]:
    if str(node.get("status") or "") == "locked":
        return []

    messages: list[dict[str, Any]] = []

    split_item = _build_audit_split_item_content(node)
    if split_item:
        messages.append(
            build_system_message(ASK_PLANNING_SEED_SPLIT_ITEM_MESSAGE_ID, split_item)
        )

    checkpoint_context = _build_audit_checkpoint_content(storage, project_id, node_index, node)
    if checkpoint_context:
        messages.append(
            build_system_message(
                ASK_PLANNING_SEED_CHECKPOINT_MESSAGE_ID,
                checkpoint_context,
            )
        )

    return messages


def _build_audit_split_item_content(node: dict[str, Any]) -> str | None:
    parent_id = str(node.get("parent_id") or "").strip()
    if not parent_id:
        return None

    title = str(node.get("title") or "").strip()
    objective, why_now = _parse_split_item_from_node(node)
    if not title and not objective and not why_now:
        return None

    lines = ["Split item for this node:"]
    if title:
        lines.append(f"- Title: {title}")
    if objective:
        lines.append(f"- Objective: {objective}")
    if why_now:
        lines.append(f"- Why now: {why_now}")
    return "\n".join(lines)


def _build_audit_checkpoint_content(
    storage: Storage,
    project_id: str,
    node_index: dict[str, Any],
    node: dict[str, Any],
) -> str | None:
    parent_id = str(node.get("parent_id") or "").strip()
    if not parent_id:
        return None
    parent = node_index.get(parent_id)
    if not isinstance(parent, dict):
        return None
    review_node_id = str(parent.get("review_node_id") or "").strip()
    if not review_node_id:
        return None
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    if not isinstance(review_state, dict):
        return None
    checkpoints = review_state.get("checkpoints", [])
    if not isinstance(checkpoints, list) or not checkpoints:
        return None
    latest = checkpoints[-1]
    if not isinstance(latest, dict):
        return None

    label = str(latest.get("label") or "").strip() or "checkpoint"
    sha = str(latest.get("sha") or "").strip()
    if not sha:
        return None
    summary = str(latest.get("summary") or "").strip() or "(baseline checkpoint)"

    return "\n".join(
        [
            "Checkpoint context from the parent review chain:",
            f"- Latest checkpoint: {label}",
            f"- SHA: {sha}",
            f"- Summary: {summary}",
        ]
    )


def _build_audit_parent_context_content(
    node_index: dict[str, Any],
    node: dict[str, Any],
) -> str | None:
    ancestors = _ancestor_chain(node_index, node)
    if not ancestors:
        return None

    lines = ["Parent chain context:"]
    for ancestor in ancestors:
        lines.append(f"- {ancestor}")
    return "\n".join(lines)


def _ancestor_chain(
    node_index: dict[str, Any],
    node: dict[str, Any],
) -> list[str]:
    prompts: list[str] = []
    parent_id = node.get("parent_id")
    visited: set[str] = set()
    while isinstance(parent_id, str) and parent_id and parent_id not in visited:
        visited.add(parent_id)
        parent = node_index.get(parent_id)
        if not isinstance(parent, dict):
            break
        title = str(parent.get("title") or "").strip()
        description = str(parent.get("description") or "").strip()
        if title and description:
            prompts.append(f"{title}: {description}")
        elif title or description:
            prompts.append(title or description)
        parent_id = parent.get("parent_id")
    prompts.reverse()
    return prompts


def _parse_split_item_from_node(node: dict[str, Any]) -> tuple[str, str | None]:
    description = str(node.get("description") or "").strip()
    if not description:
        return "", None

    objective_lines: list[str] = []
    why_now: str | None = None
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("why now:"):
            value = line.split(":", 1)[1].strip()
            why_now = value or None
            continue
        if why_now is None:
            objective_lines.append(line)

    objective = " ".join(objective_lines).strip()
    if not objective:
        objective = description
    return objective, why_now


def _load_confirmed_frame_content(snapshot: dict[str, Any], node_id: str) -> str:
    project = snapshot.get("project", {})
    if not isinstance(project, dict):
        return ""
    raw_path = str(project.get("project_path") or "").strip()
    if not raw_path:
        return ""
    node_dir = planningtree_workspace.resolve_node_dir(Path(raw_path), snapshot, node_id)
    if node_dir is None:
        return ""
    frame_meta = load_json(node_dir / "frame.meta.json", default=None)
    if not isinstance(frame_meta, dict):
        frame_meta = dict(_DEFAULT_FRAME_META)
    frame_content = str(frame_meta.get("confirmed_content") or "").strip()
    if frame_content:
        return frame_content
    frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
    if frame_path.exists():
        return frame_path.read_text(encoding="utf-8").strip()
    return ""
