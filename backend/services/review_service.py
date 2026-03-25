from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.integration_rollup_prompt_builder import (
    build_integration_rollup_base_instructions,
    build_integration_rollup_prompt,
    extract_integration_rollup_summary,
    render_integration_rollup_message,
)
from backend.ai.part_accumulator import PartAccumulator
from backend.errors.app_errors import (
    NodeNotFound,
    ReviewNotAllowed,
)
from backend.services import planningtree_workspace
from backend.services.review_sibling_manifest import derive_review_sibling_manifest
from backend.services.thread_seed_service import ensure_thread_seeded_session
from backend.services.tree_service import TreeService
from backend.services.workspace_sha import compute_workspace_sha
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

if TYPE_CHECKING:
    from backend.services.chat_service import ChatService

logger = logging.getLogger(__name__)

_DRAFT_FLUSH_INTERVAL_SEC = 0.5
_ZERO_SHA = "sha256:" + "0" * 64


class ReviewService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient | None = None,
        chat_event_broker: ChatEventBroker | None = None,
        chat_timeout: int = 30,
        chat_service: ChatService | None = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client
        self._chat_event_broker = chat_event_broker
        self._chat_timeout = int(chat_timeout)
        self._chat_service = chat_service

    # -- Local Review -------------------------------------------------

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
            exec_state["local_review_started_at"] = iso_now()
            exec_state["local_review_prompt_consumed_at"] = None
            return self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

    def get_review_state(self, project_id: str, review_node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            review_node = node_by_id.get(review_node_id)
            if review_node is None:
                raise NodeNotFound(review_node_id)
            if str(review_node.get("node_kind") or "").strip() != "review":
                raise ReviewNotAllowed("Review state is only valid for review nodes.")

            review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
            if review_state is None:
                review_state = self._storage.review_state_store.default_state()

            parent_id = str(review_node.get("parent_id") or "").strip()
            parent_node = node_by_id.get(parent_id) if parent_id else None
            sibling_manifest = (
                derive_review_sibling_manifest(snapshot, parent_node, review_node, review_state)
                if isinstance(parent_node, dict)
                else []
            )
            public_state = dict(review_state)
            public_state["sibling_manifest"] = sibling_manifest
            return public_state

    def accept_local_review(
        self, project_id: str, node_id: str, summary: str
    ) -> dict[str, Any]:
        summary = (summary or "").strip()
        if not summary:
            raise ReviewNotAllowed("Accepted local review requires a non-empty summary.")

        activated_sibling_id: str | None = None
        rollup_ready_review_node_id: str | None = None

        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                raise ReviewNotAllowed("No execution state found for this node.")
            if exec_state["status"] != "review_pending":
                raise ReviewNotAllowed(
                    f"Cannot accept local review: execution status is '{exec_state['status']}', expected 'review_pending'."
                )

            head_sha = exec_state.get("head_sha")

            exec_state["status"] = "review_accepted"
            if not str(exec_state.get("local_review_prompt_consumed_at") or "").strip():
                exec_state["local_review_prompt_consumed_at"] = iso_now()
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            node["status"] = "done"

            parent_id = node.get("parent_id")
            parent = node_by_id.get(parent_id) if isinstance(parent_id, str) else None
            review_node_id = str(parent.get("review_node_id") or "").strip() if parent else ""

            if review_node_id:
                self._storage.review_state_store.add_checkpoint(
                    project_id,
                    review_node_id,
                    sha=head_sha or "",
                    summary=summary,
                    source_node_id=node_id,
                )

                (
                    activated_sibling_id,
                    rollup_ready_review_node_id,
                ) = self._try_activate_next_sibling(
                    project_id, parent, review_node_id, snapshot, node_by_id
                )
            elif parent:
                unlocked_id = self._tree_service.unlock_next_sibling(node, node_by_id)
                if unlocked_id:
                    snapshot["tree_state"]["active_node_id"] = unlocked_id
                    activated_sibling_id = unlocked_id

            now = iso_now()
            snapshot["updated_at"] = now
            self._storage.project_store.save_snapshot(project_id, snapshot)
            self._storage.project_store.touch_meta(project_id, now)

        if rollup_ready_review_node_id:
            try:
                self.start_integration_rollup(project_id, rollup_ready_review_node_id)
            except Exception:
                logger.debug(
                    "Failed to auto-start integration rollup for %s/%s",
                    project_id,
                    rollup_ready_review_node_id,
                    exc_info=True,
                )

        return {
            "node_id": node_id,
            "status": "review_accepted",
            "activated_sibling_id": activated_sibling_id,
        }

    # -- Integration Rollup ------------------------------------------

    def start_integration_rollup(self, project_id: str, review_node_id: str) -> bool:
        if self._codex_client is None or self._chat_event_broker is None:
            logger.debug(
                "Skipping integration rollup auto-start for %s/%s because backend dependencies are unavailable.",
                project_id,
                review_node_id,
            )
            return False

        turn_id = new_id("rollup")
        assistant_message_id = new_id("msg")
        now = iso_now()
        assistant_message = {
            "message_id": assistant_message_id,
            "role": "assistant",
            "content": "",
            "status": "pending",
            "error": None,
            "turn_id": turn_id,
            "created_at": now,
            "updated_at": now,
        }

        workspace_root: str | None
        prompt: str
        existing_thread_id: str | None

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            review_node = node_by_id.get(review_node_id)
            if review_node is None:
                raise NodeNotFound(review_node_id)
            if str(review_node.get("node_kind") or "").strip() != "review":
                raise ReviewNotAllowed("Integration rollup is only valid for review nodes.")

            review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
            if review_state is None:
                raise ReviewNotAllowed("No review state found for this review node.")

            rollup = review_state.get("rollup", {})
            if not isinstance(rollup, dict) or rollup.get("status") != "ready":
                raise ReviewNotAllowed("Integration rollup can only start when rollup status is 'ready'.")

            draft = rollup.get("draft", {})
            if isinstance(draft, dict) and draft.get("summary") and draft.get("sha"):
                return False

            session = self._storage.chat_state_store.read_session(
                project_id,
                review_node_id,
                thread_role="integration",
            )
            session, _ = ensure_thread_seeded_session(
                self._storage,
                project_id=project_id,
                node_id=review_node_id,
                thread_role="integration",
                snapshot=snapshot,
                node=review_node,
                session=session,
            )
            if session.get("active_turn_id"):
                return False

            system_messages = [
                message
                for message in session.get("messages", [])
                if isinstance(message, dict) and message.get("role") == "system"
            ]
            prompt = build_integration_rollup_prompt(system_messages)
            existing_thread_id = str(session.get("thread_id") or "").strip() or None
            workspace_root = self._workspace_root_from_snapshot(snapshot)

            session["active_turn_id"] = turn_id
            session["messages"].append(assistant_message)
            self._storage.chat_state_store.write_session(
                project_id,
                review_node_id,
                session,
                thread_role="integration",
            )

        self._register_live_turn(project_id, review_node_id, turn_id)
        self._chat_event_broker.publish(
            project_id,
            review_node_id,
            {
                "type": "message_created",
                "assistant_message": assistant_message,
                "active_turn_id": turn_id,
            },
            thread_role="integration",
        )

        threading.Thread(
            target=self._run_background_integration_rollup,
            kwargs={
                "project_id": project_id,
                "review_node_id": review_node_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message_id,
                "existing_thread_id": existing_thread_id,
                "prompt": prompt,
                "workspace_root": workspace_root,
            },
            daemon=True,
        ).start()
        return True

    def accept_rollup_review(self, project_id: str, review_node_id: str) -> dict[str, Any]:
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

            session = self._storage.chat_state_store.read_session(
                project_id,
                review_node_id,
                thread_role="integration",
            )
            if session.get("active_turn_id"):
                raise ReviewNotAllowed(
                    "Cannot accept rollup while integration analysis is still running."
                )

            draft = rollup.get("draft", {})
            draft_summary = str(draft.get("summary") or "").strip() if isinstance(draft, dict) else ""
            draft_sha = str(draft.get("sha") or "").strip() if isinstance(draft, dict) else ""
            if not draft_summary or not draft_sha:
                raise ReviewNotAllowed(
                    "Cannot accept rollup before integration analysis has produced a draft summary and sha."
                )

            self._storage.review_state_store.set_rollup(
                project_id,
                review_node_id,
                "accepted",
                summary=draft_summary,
                sha=draft_sha,
            )

            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            review_node = node_by_id.get(review_node_id)
            parent_id = str(review_node.get("parent_id") or "") if review_node else ""

            if parent_id:
                from backend.services.execution_gating import (
                    AUDIT_ROLLUP_PACKAGE_MESSAGE_ID,
                    append_immutable_audit_record,
                )

                package_content = (
                    "## Rollup Package\n\n"
                    f"**Summary:** {draft_summary}\n\n"
                    f"**SHA:** {draft_sha}\n\n"
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
                "summary": draft_summary,
                "sha": draft_sha,
            }

    # -- Sibling Activation ------------------------------------------

    def _try_activate_next_sibling(
        self,
        project_id: str,
        parent: dict[str, Any],
        review_node_id: str,
        snapshot: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> tuple[str | None, str | None]:
        next_sib = self._storage.review_state_store.get_next_pending_sibling(
            project_id, review_node_id
        )
        if next_sib is None:
            if self._try_mark_rollup_ready(project_id, parent, review_node_id, node_by_id):
                return None, review_node_id
            return None, None

        return (
            self._materialize_sibling(
                project_id, parent, review_node_id, next_sib, snapshot, node_by_id
            ),
            None,
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

        parent.setdefault("child_ids", []).append(new_node_id)
        snapshot["tree_state"]["node_index"][new_node_id] = new_node
        node_by_id[new_node_id] = new_node
        snapshot["tree_state"]["active_node_id"] = new_node_id

        self._storage.review_state_store.mark_sibling_materialized(
            project_id, review_node_id, sib_index, new_node_id
        )

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
    ) -> bool:
        review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
        if review_state is None:
            return False

        rollup = review_state.get("rollup", {})
        if rollup.get("status") != "pending":
            return False

        for sib in review_state.get("pending_siblings", []):
            if sib.get("materialized_node_id") is None:
                return False

        child_ids = parent.get("child_ids", [])
        for child_id in child_ids:
            child = node_by_id.get(child_id)
            if child is None:
                return False
            exec_state = self._storage.execution_state_store.read_state(project_id, child_id)
            if exec_state is None or exec_state.get("status") != "review_accepted":
                return False

        self._storage.review_state_store.set_rollup(project_id, review_node_id, "ready")
        return True

    # -- Background Integration Runner -------------------------------

    def _run_background_integration_rollup(
        self,
        *,
        project_id: str,
        review_node_id: str,
        turn_id: str,
        assistant_message_id: str,
        existing_thread_id: str | None,
        prompt: str,
        workspace_root: str | None,
    ) -> None:
        thread_id = existing_thread_id
        draft_lock = threading.Lock()
        accumulator = PartAccumulator()
        last_checkpoint_at = time.monotonic()

        def capture_delta(delta: str) -> None:
            nonlocal last_checkpoint_at
            checkpoint_content: str | None = None
            with draft_lock:
                accumulator.on_delta(delta)
                now = time.monotonic()
                if now - last_checkpoint_at >= _DRAFT_FLUSH_INTERVAL_SEC:
                    checkpoint_content = accumulator.content_projection()
                    last_checkpoint_at = now

            self._publish_event(
                project_id,
                review_node_id,
                {
                    "type": "assistant_delta",
                    "message_id": assistant_message_id,
                    "delta": delta,
                    "item_id": "assistant_text",
                    "item_type": "assistant_text",
                    "phase": "delta",
                },
            )

            if checkpoint_content is not None:
                self._persist_assistant_message(
                    project_id=project_id,
                    node_id=review_node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=checkpoint_content,
                    status="streaming",
                    error=None,
                    thread_id=thread_id,
                    clear_active_turn=False,
                    parts=accumulator.snapshot_parts(),
                    items=accumulator.snapshot_items(),
                )

        def capture_tool_call(tool_name: str, arguments: dict[str, Any]) -> None:
            with draft_lock:
                item_id = accumulator.on_tool_call(tool_name, arguments)
                part_index = len(accumulator.parts) - 1
            self._publish_event(
                project_id,
                review_node_id,
                {
                    "type": "assistant_tool_call",
                    "message_id": assistant_message_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "part_index": part_index,
                    "item_id": item_id,
                    "item_type": "tool_call",
                    "phase": "started",
                },
            )

        def capture_thread_status(payload: dict[str, Any]) -> None:
            with draft_lock:
                accumulator.on_thread_status(payload)
            status = payload.get("status", {})
            status_type = status.get("type", "unknown") if isinstance(status, dict) else "unknown"
            from backend.ai.part_accumulator import _status_label

            self._publish_event(
                project_id,
                review_node_id,
                {
                    "type": "assistant_status",
                    "message_id": assistant_message_id,
                    "status_type": status_type,
                    "label": _status_label(status_type),
                    "item_id": "thread_status",
                    "item_type": "thread_status",
                    "phase": "delta",
                },
            )

        try:
            thread_id = self._ensure_integration_thread(existing_thread_id, workspace_root)
            self._persist_thread_id(
                project_id=project_id,
                node_id=review_node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                thread_id=thread_id,
            )

            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                on_delta=capture_delta,
                on_tool_call=capture_tool_call,
                on_thread_status=capture_thread_status,
            )

            with draft_lock:
                accumulator.finalize()
                streamed_content = accumulator.content_projection()
                final_parts = accumulator.snapshot_parts()
                final_items = accumulator.snapshot_items()

            stdout = str(result.get("stdout", "") or "")
            summary = extract_integration_rollup_summary(stdout) or extract_integration_rollup_summary(
                streamed_content
            )
            if not summary:
                raise ReviewNotAllowed(
                    "Integration backend did not return a valid JSON rollup summary."
                )

            final_sha = self._compute_workspace_sha(workspace_root)
            self._storage.review_state_store.set_rollup_draft(
                project_id,
                review_node_id,
                summary=summary,
                sha=final_sha,
            )

            final_content = render_integration_rollup_message(summary, final_sha)
            persisted = self._persist_assistant_message(
                project_id=project_id,
                node_id=review_node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=final_content,
                status="completed",
                error=None,
                thread_id=str(result.get("thread_id") or thread_id or ""),
                clear_active_turn=True,
                parts=self._finalize_parts(final_parts, final_content),
                items=final_items,
            )

            if persisted:
                self._publish_event(
                    project_id,
                    review_node_id,
                    {
                        "type": "assistant_completed",
                        "message_id": assistant_message_id,
                        "content": final_content,
                        "thread_id": str(result.get("thread_id") or thread_id or ""),
                    },
                )
        except Exception as exc:
            logger.debug(
                "Integration rollup failed for %s/%s: %s",
                project_id,
                review_node_id,
                exc,
                exc_info=True,
            )
            try:
                with draft_lock:
                    accumulator.finalize()
                    error_parts = accumulator.snapshot_parts()
                    streamed_content = accumulator.content_projection()
                persisted = self._persist_assistant_message(
                    project_id=project_id,
                    node_id=review_node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=streamed_content,
                    status="error",
                    error=str(exc),
                    thread_id=thread_id,
                    clear_active_turn=True,
                    parts=error_parts,
                    items=accumulator.snapshot_items(),
                )
            except Exception:
                persisted = False
                logger.debug("Failed to persist integration rollup error", exc_info=True)

            if persisted:
                self._publish_event(
                    project_id,
                    review_node_id,
                    {
                        "type": "assistant_error",
                        "message_id": assistant_message_id,
                        "error": str(exc),
                    },
                )
        finally:
            self._clear_live_turn(project_id, review_node_id, turn_id)

    # -- Persistence Helpers -----------------------------------------

    def _ensure_integration_thread(
        self, existing_thread_id: str | None, workspace_root: str | None
    ) -> str:
        if isinstance(existing_thread_id, str) and existing_thread_id.strip():
            try:
                self._codex_client.resume_thread(
                    existing_thread_id,
                    cwd=workspace_root,
                    timeout_sec=15,
                )
                return existing_thread_id.strip()
            except CodexTransportError as exc:
                if not self._is_missing_thread_error(exc):
                    raise ReviewNotAllowed(f"Integration backend unavailable: {exc}") from exc

        try:
            response = self._codex_client.start_thread(
                base_instructions=build_integration_rollup_base_instructions(),
                dynamic_tools=[],
                cwd=workspace_root,
                timeout_sec=30,
            )
        except CodexTransportError as exc:
            raise ReviewNotAllowed(f"Integration backend unavailable: {exc}") from exc

        thread_id = str(response.get("thread_id") or "").strip()
        if not thread_id:
            raise ReviewNotAllowed(
                "Integration thread start did not return a thread id."
            )
        return thread_id

    def _persist_thread_id(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        thread_id: str,
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role="integration"
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            if self._find_message(session, assistant_message_id) is None:
                return False
            session["thread_id"] = thread_id
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="integration"
            )
            return True

    def _persist_assistant_message(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        content: str,
        status: str,
        error: str | None,
        thread_id: str | None,
        clear_active_turn: bool,
        parts: list[dict[str, Any]] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role="integration"
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return False

            message["content"] = content
            message["status"] = status
            message["error"] = error
            message["updated_at"] = iso_now()
            if parts is not None:
                message["parts"] = parts
            if items is not None:
                message["items"] = items

            if thread_id is not None:
                session["thread_id"] = thread_id
            if clear_active_turn:
                session["active_turn_id"] = None

            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="integration"
            )
            return True

    @staticmethod
    def _find_message(
        session: dict[str, Any],
        assistant_message_id: str,
    ) -> dict[str, Any] | None:
        for message in reversed(session.get("messages", [])):
            if message.get("message_id") == assistant_message_id:
                return message
        return None

    @staticmethod
    def _finalize_parts(parts: list[dict[str, Any]], final_content: str) -> list[dict[str, Any]]:
        retained = [dict(part) for part in parts if part.get("type") != "assistant_text"]
        retained.append(
            {
                "type": "assistant_text",
                "content": final_content,
                "is_streaming": False,
            }
        )
        return retained

    def _publish_event(self, project_id: str, node_id: str, event: dict[str, Any]) -> None:
        if self._chat_event_broker is None:
            return
        self._chat_event_broker.publish(
            project_id,
            node_id,
            event,
            thread_role="integration",
        )

    def _register_live_turn(self, project_id: str, node_id: str, turn_id: str) -> None:
        if self._chat_service is None:
            return
        self._chat_service.register_external_live_turn(
            project_id, node_id, "integration", turn_id
        )

    def _clear_live_turn(self, project_id: str, node_id: str, turn_id: str) -> None:
        if self._chat_service is None:
            return
        self._chat_service.clear_external_live_turn(
            project_id, node_id, "integration", turn_id
        )

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_path")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _compute_workspace_sha(self, workspace_root: str | None) -> str:
        if workspace_root:
            return compute_workspace_sha(Path(workspace_root))
        return _ZERO_SHA

    @staticmethod
    def _is_missing_thread_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message
