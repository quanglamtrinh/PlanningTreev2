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

INTEGRATION_SEED_PARENT_FRAME_MESSAGE_ID = "seed:integration:parent-frame"
INTEGRATION_SEED_SPLIT_PACKAGE_MESSAGE_ID = "seed:integration:split-package"
INTEGRATION_SEED_CHECKPOINTS_MESSAGE_ID = "seed:integration:checkpoints"
INTEGRATION_SEED_CHILD_REVIEWS_MESSAGE_ID = "seed:integration:child-reviews"
INTEGRATION_SEED_GOAL_MESSAGE_ID = "seed:integration:goal"

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

INTEGRATION_IMMUTABLE_MESSAGE_IDS = frozenset(
    {
        INTEGRATION_SEED_PARENT_FRAME_MESSAGE_ID,
        INTEGRATION_SEED_SPLIT_PACKAGE_MESSAGE_ID,
        INTEGRATION_SEED_CHECKPOINTS_MESSAGE_ID,
        INTEGRATION_SEED_CHILD_REVIEWS_MESSAGE_ID,
        INTEGRATION_SEED_GOAL_MESSAGE_ID,
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

    if thread_role == "ask_planning":
        return _build_ask_planning_seed_messages(storage, project_id, node_index, node)
    if thread_role == "audit":
        return _build_audit_seed_messages(storage, project_id, snapshot, node_index, node)
    if thread_role == "integration":
        return _build_integration_seed_messages(storage, project_id, snapshot, node_index, node_id, node)
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
    if thread_role == "ask_planning":
        return ASK_PLANNING_IMMUTABLE_MESSAGE_IDS
    if thread_role == "audit":
        return AUDIT_IMMUTABLE_MESSAGE_IDS
    if thread_role == "integration":
        return INTEGRATION_IMMUTABLE_MESSAGE_IDS
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


def _build_integration_seed_messages(
    storage: Storage,
    project_id: str,
    snapshot: dict[str, Any],
    node_index: dict[str, Any],
    review_node_id: str,
    review_node: dict[str, Any],
) -> list[dict[str, Any]]:
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    if not isinstance(review_state, dict):
        return []

    rollup = review_state.get("rollup", {})
    if not isinstance(rollup, dict):
        return []
    rollup_status = str(rollup.get("status") or "").strip()
    if rollup_status not in {"ready", "accepted"}:
        return []

    parent_id = str(review_node.get("parent_id") or "").strip()
    parent = node_index.get(parent_id) if parent_id else None
    if not isinstance(parent, dict):
        return []

    messages: list[dict[str, Any]] = []

    parent_frame = _build_integration_parent_frame_content(snapshot, parent)
    if parent_frame:
        messages.append(
            build_system_message(INTEGRATION_SEED_PARENT_FRAME_MESSAGE_ID, parent_frame)
        )

    split_package = _build_integration_split_package_content(node_index, parent)
    if split_package:
        messages.append(
            build_system_message(INTEGRATION_SEED_SPLIT_PACKAGE_MESSAGE_ID, split_package)
        )

    checkpoints = _build_integration_checkpoint_content(review_state)
    if checkpoints:
        messages.append(
            build_system_message(INTEGRATION_SEED_CHECKPOINTS_MESSAGE_ID, checkpoints)
        )

    child_reviews = _build_integration_child_reviews_content(node_index, review_state)
    if child_reviews:
        messages.append(
            build_system_message(INTEGRATION_SEED_CHILD_REVIEWS_MESSAGE_ID, child_reviews)
        )

    messages.append(
        build_system_message(
            INTEGRATION_SEED_GOAL_MESSAGE_ID,
            (
                "Integration rollup goal:\n"
                "- Detect conflicts between child outputs.\n"
                "- Identify overlap, missing glue, or cross-child mismatches.\n"
                "- Produce a rollup summary and final subtree SHA."
            ),
        )
    )

    return messages


def _build_integration_parent_frame_content(
    snapshot: dict[str, Any],
    parent: dict[str, Any],
) -> str | None:
    frame_content = _load_confirmed_frame_content(snapshot, str(parent.get("node_id") or ""))
    if not frame_content:
        return None

    title = str(parent.get("title") or "").strip()
    prefix = "Parent confirmed frame:"
    if title:
        prefix = f"Parent confirmed frame for '{title}':"
    return prefix + "\n\n```markdown\n" + frame_content.strip() + "\n```"


def _build_integration_split_package_content(
    node_index: dict[str, Any],
    parent: dict[str, Any],
) -> str | None:
    child_ids = parent.get("child_ids", [])
    if not isinstance(child_ids, list):
        return None

    lines = ["Split package overview:"]
    found = False
    for child_id in child_ids:
        if not isinstance(child_id, str):
            continue
        child = node_index.get(child_id)
        if not isinstance(child, dict):
            continue
        title = str(child.get("title") or "").strip() or child_id
        objective, why_now = _parse_split_item_from_node(child)
        lines.append(f"- {title}")
        if objective:
            lines.append(f"  Objective: {objective}")
        if why_now:
            lines.append(f"  Why now: {why_now}")
        found = True
    if not found:
        return None
    return "\n".join(lines)


def _build_integration_checkpoint_content(review_state: dict[str, Any]) -> str | None:
    checkpoints = review_state.get("checkpoints", [])
    if not isinstance(checkpoints, list) or not checkpoints:
        return None

    lines = ["Checkpoint records:"]
    found = False
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            continue
        label = str(checkpoint.get("label") or "").strip()
        sha = str(checkpoint.get("sha") or "").strip()
        if not label or not sha:
            continue
        summary = str(checkpoint.get("summary") or "").strip() or "(split baseline)"
        source_node_id = str(checkpoint.get("source_node_id") or "").strip() or "baseline"
        lines.append(f"- {label}: {sha}")
        lines.append(f"  Source: {source_node_id}")
        lines.append(f"  Summary: {summary}")
        found = True
    if not found:
        return None
    return "\n".join(lines)


def _build_integration_child_reviews_content(
    node_index: dict[str, Any],
    review_state: dict[str, Any],
) -> str | None:
    checkpoints = review_state.get("checkpoints", [])
    if not isinstance(checkpoints, list):
        return None

    lines = ["Accepted local review summaries:"]
    found = False
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            continue
        summary = str(checkpoint.get("summary") or "").strip()
        source_node_id = str(checkpoint.get("source_node_id") or "").strip()
        sha = str(checkpoint.get("sha") or "").strip()
        if not summary or not source_node_id:
            continue
        source_node = node_index.get(source_node_id)
        source_title = (
            str(source_node.get("title") or "").strip()
            if isinstance(source_node, dict)
            else source_node_id
        ) or source_node_id
        lines.append(f"- {source_title} ({source_node_id})")
        lines.append(f"  Accepted SHA: {sha}")
        lines.append(f"  Summary: {summary}")
        found = True
    if not found:
        return None
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
