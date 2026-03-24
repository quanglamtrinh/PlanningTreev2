from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.errors.app_errors import (
    NodeNotFound,
    ReviewNotAllowed,
    SiblingActivationNotAllowed,
)
from backend.services import planningtree_workspace
from backend.services.tree_service import TreeService
from backend.services.workspace_sha import compute_workspace_sha
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, storage: Storage, tree_service: TreeService) -> None:
        self._storage = storage
        self._tree_service = tree_service

    # ── Local Review ─────────────────────────────────────────────

    def start_local_review(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                raise ReviewNotAllowed("No execution state found for this node.")
            if exec_state["status"] != "completed":
                raise ReviewNotAllowed(
                    f"Cannot start local review: execution status is '{exec_state['status']}', expected 'completed'."
                )
            exec_state["status"] = "review_pending"
            return self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

    def accept_local_review(
        self, project_id: str, node_id: str, summary: str
    ) -> dict[str, Any]:
        summary = (summary or "").strip()
        if not summary:
            raise ReviewNotAllowed("Accepted local review requires a non-empty summary.")

        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                raise ReviewNotAllowed("No execution state found for this node.")
            if exec_state["status"] != "review_pending":
                raise ReviewNotAllowed(
                    f"Cannot accept local review: execution status is '{exec_state['status']}', expected 'review_pending'."
                )

            head_sha = exec_state.get("head_sha")

            # Transition to review_accepted
            exec_state["status"] = "review_accepted"
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            # Mark node as done
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            node["status"] = "done"

            # Find parent and its review node
            parent_id = node.get("parent_id")
            parent = node_by_id.get(parent_id) if isinstance(parent_id, str) else None
            review_node_id = str(parent.get("review_node_id") or "").strip() if parent else ""

            activated_sibling_id: str | None = None

            if review_node_id:
                # Lazy path: append checkpoint to review node
                self._storage.review_state_store.add_checkpoint(
                    project_id,
                    review_node_id,
                    sha=head_sha or "",
                    summary=summary,
                    source_node_id=node_id,
                )

                # Try to activate next sibling or mark rollup ready
                activated_sibling_id = self._try_activate_next_sibling(
                    project_id, parent, review_node_id, snapshot, node_by_id
                )
            elif parent:
                # Legacy eager path: unlock next locked sibling
                unlocked_id = self._tree_service.unlock_next_sibling(node, node_by_id)
                if unlocked_id:
                    snapshot["tree_state"]["active_node_id"] = unlocked_id
                    activated_sibling_id = unlocked_id

            now = iso_now()
            snapshot["updated_at"] = now
            self._storage.project_store.save_snapshot(project_id, snapshot)
            self._storage.project_store.touch_meta(project_id, now)

            return {
                "node_id": node_id,
                "status": "review_accepted",
                "activated_sibling_id": activated_sibling_id,
            }

    # ── Sibling Activation ───────────────────────────────────────

    def _try_activate_next_sibling(
        self,
        project_id: str,
        parent: dict[str, Any],
        review_node_id: str,
        snapshot: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> str | None:
        next_sib = self._storage.review_state_store.get_next_pending_sibling(
            project_id, review_node_id
        )
        if next_sib is None:
            # All siblings done — check if rollup can transition to ready
            self._try_mark_rollup_ready(project_id, parent, review_node_id, node_by_id)
            return None

        return self._materialize_sibling(
            project_id, parent, review_node_id, next_sib, snapshot, node_by_id
        )

    def _materialize_sibling(
        self,
        project_id: str,
        parent: dict[str, Any],
        review_node_id: str,
        manifest_entry: dict[str, Any],
        snapshot: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> str:
        now = iso_now()
        parent_id = str(parent.get("node_id") or "")
        parent_hnum = str(parent.get("hierarchical_number") or "1")
        parent_depth = int(parent.get("depth", 0) or 0)
        sib_index = int(manifest_entry["index"])

        new_node_id = uuid4().hex
        new_node = {
            "node_id": new_node_id,
            "parent_id": parent_id,
            "child_ids": [],
            "title": manifest_entry["title"],
            "description": manifest_entry["objective"],
            "status": "ready",
            "node_kind": "original",
            "depth": parent_depth + 1,
            "display_order": sib_index - 1,
            "hierarchical_number": f"{parent_hnum}.{sib_index}",
            "created_at": now,
        }

        # Add to tree
        parent.setdefault("child_ids", []).append(new_node_id)
        snapshot["tree_state"]["node_index"][new_node_id] = new_node
        node_by_id[new_node_id] = new_node

        # Set as active node
        snapshot["tree_state"]["active_node_id"] = new_node_id

        # Mark in manifest
        self._storage.review_state_store.mark_sibling_materialized(
            project_id, review_node_id, sib_index, new_node_id
        )

        # Sync workspace directories
        workspace_root = self._workspace_root_from_snapshot(snapshot)
        if workspace_root:
            planningtree_workspace.sync_snapshot_tree(Path(workspace_root), snapshot)

        return new_node_id

    def _try_mark_rollup_ready(
        self,
        project_id: str,
        parent: dict[str, Any],
        review_node_id: str,
        node_by_id: dict[str, dict[str, Any]],
    ) -> None:
        review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
        if review_state is None:
            return

        rollup = review_state.get("rollup", {})
        if rollup.get("status") != "pending":
            return

        # Check: all pending siblings must be materialized
        for sib in review_state.get("pending_siblings", []):
            if sib.get("materialized_node_id") is None:
                return

        # Check: all materialized children must be review_accepted
        child_ids = parent.get("child_ids", [])
        for child_id in child_ids:
            child = node_by_id.get(child_id)
            if child is None:
                return
            exec_state = self._storage.execution_state_store.read_state(project_id, child_id)
            if exec_state is None or exec_state.get("status") != "review_accepted":
                return

        # All conditions met — transition rollup to ready
        self._storage.review_state_store.set_rollup(project_id, review_node_id, "ready")

    # ── Rollup Review ────────────────────────────────────────────

    def accept_rollup_review(
        self, project_id: str, review_node_id: str, summary: str
    ) -> dict[str, Any]:
        summary = (summary or "").strip()
        if not summary:
            raise ReviewNotAllowed("Accepted rollup review requires a non-empty summary.")

        with self._storage.project_lock(project_id):
            review_state = self._storage.review_state_store.read_state(
                project_id, review_node_id
            )
            if review_state is None:
                raise ReviewNotAllowed("No review state found for this review node.")

            rollup = review_state.get("rollup", {})
            if rollup.get("status") != "ready":
                raise ReviewNotAllowed(
                    f"Cannot accept rollup: rollup status is '{rollup.get('status')}', expected 'ready'."
                )

            # Compute final workspace SHA
            snapshot = self._storage.project_store.load_snapshot(project_id)
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if workspace_root:
                final_sha = compute_workspace_sha(Path(workspace_root))
            else:
                final_sha = "sha256:" + "0" * 64

            # Transition rollup to accepted
            self._storage.review_state_store.set_rollup(
                project_id, review_node_id, "accepted", summary=summary, sha=final_sha
            )

            # Append rollup package to parent audit
            node_by_id = self._tree_service.node_index(snapshot)
            review_node = node_by_id.get(review_node_id)
            parent_id = str(review_node.get("parent_id") or "") if review_node else ""

            if parent_id:
                from backend.services.execution_gating import (
                    AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
                    append_immutable_audit_record,
                )

                package_content = (
                    f"## Rollup Package\n\n"
                    f"**Summary:** {summary}\n\n"
                    f"**SHA:** {final_sha}\n\n"
                    f"**Review Node:** {review_node_id}\n\n"
                    f"**Accepted At:** {iso_now()}\n"
                )
                append_immutable_audit_record(
                    self._storage,
                    project_id,
                    parent_id,
                    message_id=AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
                    content=package_content,
                )

            return {
                "review_node_id": review_node_id,
                "rollup_status": "accepted",
                "summary": summary,
                "sha": final_sha,
            }

    # ── Helpers ──────────────────────────────────────────────────

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_path")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None
