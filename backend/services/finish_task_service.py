from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.execution_prompt_builder import (
    build_execution_base_instructions,
    build_execution_prompt,
)
from backend.ai.part_accumulator import PartAccumulator
from backend.ai.split_context_builder import build_split_context
from backend.errors.app_errors import FinishTaskNotAllowed, NodeNotFound
from backend.services import planningtree_workspace
from backend.services.node_detail_service import (
    NodeDetailService,
    _DEFAULT_FRAME_META,
    _load_spec_meta_from_node_dir,
)
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, load_json, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)

_DRAFT_FLUSH_INTERVAL_SEC = 0.5


class FinishTaskService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        node_detail_service: NodeDetailService,
        codex_client: CodexAppClient,
        chat_event_broker: ChatEventBroker,
        chat_timeout: int,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._node_detail_service = node_detail_service
        self._codex_client = codex_client
        self._chat_event_broker = chat_event_broker
        self._chat_timeout = int(chat_timeout)
        self._live_jobs_lock = threading.Lock()
        self._live_jobs: dict[str, str] = {}

    def finish_task(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)

            node_dir = self._resolve_node_dir(snapshot, node_id)
            spec_content = self._validate_finish_task_locked(project_id, node_id, snapshot, node, node_dir)
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            frame_content = self._load_confirmed_frame_content(node_dir)
            task_context = build_split_context(snapshot, node, node_index)
            execution_session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role="execution",
            )
            existing_thread_id = execution_session.get("thread_id")

        thread_id = self._ensure_execution_thread(existing_thread_id, workspace_root)

        turn_id = new_id("exec")
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
        prompt = build_execution_prompt(
            spec_content=spec_content,
            frame_content=frame_content,
            task_context=task_context,
        )
        initial_sha: str

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            self._validate_finish_task_locked(project_id, node_id, snapshot, node, node_dir)
            initial_sha = self._compute_initial_sha(project_id, node_id, snapshot)

            exec_state = {
                "status": "executing",
                "initial_sha": initial_sha,
                "head_sha": None,
                "started_at": now,
                "completed_at": None,
            }
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            if node.get("status") != "in_progress":
                node["status"] = "in_progress"
                snapshot["updated_at"] = now
                self._storage.project_store.save_snapshot(project_id, snapshot)

            session = self._storage.chat_state_store.clear_session(
                project_id,
                node_id,
                thread_role="execution",
            )
            session["thread_id"] = thread_id
            session["active_turn_id"] = turn_id
            session["messages"] = [assistant_message]
            self._storage.chat_state_store.write_session(
                project_id,
                node_id,
                session,
                thread_role="execution",
            )
            self._mark_live_job(project_id, node_id, turn_id)

        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "message_created",
                "assistant_message": assistant_message,
                "active_turn_id": turn_id,
            },
            thread_role="execution",
        )

        threading.Thread(
            target=self._run_background_execution,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message_id,
                "thread_id": thread_id,
                "prompt": prompt,
                "workspace_root": workspace_root,
            },
            daemon=True,
        ).start()

        return self._node_detail_service.get_detail_state(project_id, node_id)

    def complete_execution(
        self,
        project_id: str,
        node_id: str,
        head_sha: str | None = None,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                raise FinishTaskNotAllowed("No execution state exists for this node.")
            if exec_state.get("status") != "executing":
                raise FinishTaskNotAllowed(
                    f"Cannot complete execution: status is '{exec_state.get('status')}', expected 'executing'."
                )

            exec_state["status"] = "completed"
            exec_state["head_sha"] = head_sha
            exec_state["completed_at"] = iso_now()
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

        detail_state = self._node_detail_service.get_detail_state(project_id, node_id)
        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "execution_completed",
                "node_id": node_id,
                "head_sha": head_sha,
                "execution_status": "completed",
            },
            thread_role="execution",
        )
        return detail_state

    def _run_background_execution(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        thread_id: str,
        prompt: str,
        workspace_root: str | None,
    ) -> None:
        draft_lock = threading.Lock()
        accumulator = PartAccumulator()
        last_checkpoint_at = time.monotonic()

        def persist_activity_snapshot() -> None:
            self._persist_execution_message(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=accumulator.content_projection(),
                status="streaming",
                error=None,
                thread_id=thread_id,
                clear_active_turn=False,
                parts=accumulator.snapshot_parts(),
            )

        def capture_delta(delta: str) -> None:
            nonlocal last_checkpoint_at
            checkpoint_content: str | None = None
            with draft_lock:
                accumulator.on_delta(delta)
                now = time.monotonic()
                if now - last_checkpoint_at >= _DRAFT_FLUSH_INTERVAL_SEC:
                    checkpoint_content = accumulator.content_projection()
                    last_checkpoint_at = now

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_delta",
                    "message_id": assistant_message_id,
                    "delta": delta,
                },
                thread_role="execution",
            )

            if checkpoint_content is not None:
                self._persist_execution_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=checkpoint_content,
                    status="streaming",
                    error=None,
                    thread_id=thread_id,
                    clear_active_turn=False,
                    parts=accumulator.snapshot_parts(),
                )

        def capture_tool_call(tool_name: str, arguments: dict[str, Any]) -> None:
            with draft_lock:
                accumulator.on_tool_call(tool_name, arguments)
                part_index = len(accumulator.parts) - 1
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_tool_call",
                    "message_id": assistant_message_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "part_index": part_index,
                },
                thread_role="execution",
            )

            with draft_lock:
                persist_activity_snapshot()

        def capture_thread_status(payload: dict[str, Any]) -> None:
            with draft_lock:
                accumulator.on_thread_status(payload)
            status = payload.get("status", {})
            status_type = status.get("type", "unknown") if isinstance(status, dict) else "unknown"
            from backend.ai.part_accumulator import _status_label

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_status",
                    "message_id": assistant_message_id,
                    "status_type": status_type,
                    "label": _status_label(status_type),
                },
                thread_role="execution",
            )

            with draft_lock:
                persist_activity_snapshot()

        def capture_plan_delta(delta: str, item: dict[str, Any]) -> None:
            item_id = str(item.get("id") or "").strip()
            if not item_id or not isinstance(delta, str) or not delta:
                return

            with draft_lock:
                accumulator.on_plan_delta(delta, item)
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_plan_delta",
                    "message_id": assistant_message_id,
                    "item_id": item_id,
                    "delta": delta,
                },
                thread_role="execution",
            )

            with draft_lock:
                persist_activity_snapshot()

        try:
            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                writable_roots=[workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None,
                on_delta=capture_delta,
                on_tool_call=capture_tool_call,
                on_plan_delta=capture_plan_delta,
                on_thread_status=capture_thread_status,
            )

            with draft_lock:
                final_plan_item = result.get("final_plan_item")
                if isinstance(final_plan_item, dict):
                    text = str(final_plan_item.get("text") or "")
                    item_id = str(final_plan_item.get("id") or "")
                    if text.strip() and item_id.strip():
                        existing_plan_item = next(
                            (
                                part
                                for part in accumulator.parts
                                if part.get("type") == "plan_item" and part.get("item_id") == item_id
                            ),
                            None,
                        )
                        if existing_plan_item is None:
                            accumulator.on_plan_delta(text, final_plan_item)
                accumulator.finalize(keep_status_blocks=True)
                final_parts = accumulator.snapshot_parts()
                streamed_content = accumulator.content_projection()
            stdout = str(result.get("stdout", "") or "")
            final_content = stdout or streamed_content
            persisted = self._persist_execution_message(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=final_content,
                status="completed",
                error=None,
                thread_id=thread_id,
                clear_active_turn=True,
                parts=final_parts,
            )

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_completed",
                        "message_id": assistant_message_id,
                        "content": final_content,
                        "thread_id": thread_id,
                    },
                    thread_role="execution",
                )

            from backend.services.workspace_sha import compute_workspace_sha
            head_sha = compute_workspace_sha(Path(workspace_root)) if workspace_root else None
            self.complete_execution(project_id, node_id, head_sha=head_sha)
        except Exception as exc:
            logger.debug(
                "Execution turn failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            try:
                with draft_lock:
                    accumulator.finalize()
                    error_parts = accumulator.snapshot_parts()
                    streamed_content = accumulator.content_projection()
                persisted = self._persist_execution_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=streamed_content,
                    status="error",
                    error=str(exc),
                    thread_id=thread_id,
                    clear_active_turn=True,
                    parts=error_parts,
                )
            except Exception:
                persisted = False
                logger.debug("Failed to persist execution error state", exc_info=True)

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_error",
                        "message_id": assistant_message_id,
                        "error": str(exc),
                    },
                    thread_role="execution",
                )

            try:
                self.complete_execution(project_id, node_id, head_sha=None)
            except Exception:
                logger.debug("Failed to complete errored execution", exc_info=True)
        finally:
            self._clear_live_job(project_id, node_id, turn_id)

    def _validate_finish_task_locked(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_dir: Path,
    ) -> str:
        if node.get("node_kind") == "review":
            raise FinishTaskNotAllowed("Finish Task is only available for task nodes.")

        spec_meta = _load_spec_meta_from_node_dir(node_dir)
        if not spec_meta.get("confirmed_at"):
            raise FinishTaskNotAllowed("Spec must be confirmed before Finish Task.")

        child_ids = node.get("child_ids") or []
        if len(child_ids) > 0:
            raise FinishTaskNotAllowed("Finish Task is only available for leaf nodes (no children).")

        node_status = node.get("status", "")
        if node_status not in ("ready", "in_progress"):
            raise FinishTaskNotAllowed(
                f"Node status must be 'ready' or 'in_progress', got '{node_status}'."
            )

        if self._storage.execution_state_store.exists(project_id, node_id):
            raise FinishTaskNotAllowed("Execution has already been started for this node.")

        spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
        spec_content = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        if not spec_content.strip():
            raise FinishTaskNotAllowed("Spec must be non-empty before Finish Task.")

        del snapshot
        return spec_content

    def _ensure_execution_thread(self, existing_thread_id: Any, workspace_root: str | None) -> str:
        writable_roots = [workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None
        if isinstance(existing_thread_id, str) and existing_thread_id.strip():
            try:
                self._codex_client.resume_thread(
                    existing_thread_id,
                    cwd=workspace_root,
                    timeout_sec=15,
                    writable_roots=writable_roots,
                )
                return existing_thread_id.strip()
            except CodexTransportError as exc:
                if not self._is_missing_thread_error(exc):
                    raise FinishTaskNotAllowed(f"Execution backend unavailable: {exc}") from exc

        try:
            response = self._codex_client.start_thread(
                base_instructions=build_execution_base_instructions(),
                dynamic_tools=[],
                cwd=workspace_root,
                timeout_sec=30,
                writable_roots=writable_roots,
            )
        except CodexTransportError as exc:
            raise FinishTaskNotAllowed(f"Execution backend unavailable: {exc}") from exc

        thread_id = str(response.get("thread_id") or "").strip()
        if not thread_id:
            raise FinishTaskNotAllowed("Execution thread start did not return a thread id.")
        return thread_id

    def _persist_execution_message(
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
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role="execution",
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False

            message = None
            for candidate in reversed(session.get("messages", [])):
                if candidate.get("message_id") == assistant_message_id:
                    message = candidate
                    break
            if message is None:
                return False

            message["content"] = content
            message["status"] = status
            message["error"] = error
            message["updated_at"] = iso_now()
            if parts is not None:
                message["parts"] = parts

            if thread_id is not None:
                session["thread_id"] = thread_id
            if clear_active_turn:
                session["active_turn_id"] = None

            self._storage.chat_state_store.write_session(
                project_id,
                node_id,
                session,
                thread_role="execution",
            )
            return True

    def _compute_initial_sha(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
    ) -> str:
        node_index = snapshot.get("tree_state", {}).get("node_index", {})
        node = node_index.get(node_id, {})
        parent_id = node.get("parent_id")

        if parent_id:
            parent = node_index.get(parent_id, {})
            review_node_id = parent.get("review_node_id")
            if review_node_id:
                review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
                if review_state:
                    checkpoints = review_state.get("checkpoints", [])
                    if checkpoints:
                        return checkpoints[-1]["sha"]

        workspace_root = self._workspace_root_from_snapshot(snapshot)
        if workspace_root is None:
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        from backend.services.workspace_sha import compute_workspace_sha
        return compute_workspace_sha(Path(workspace_root))

    def _load_confirmed_frame_content(self, node_dir: Path) -> str:
        meta_path = node_dir / "frame.meta.json"
        frame_meta = load_json(meta_path, default=None)
        if not isinstance(frame_meta, dict):
            frame_meta = dict(_DEFAULT_FRAME_META)
        frame_content = str(frame_meta.get("confirmed_content") or "")
        if frame_content:
            return frame_content
        frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
        if frame_path.exists():
            return frame_path.read_text(encoding="utf-8")
        return ""

    def _resolve_node_dir(self, snapshot: dict[str, Any], node_id: str) -> Path:
        project = snapshot.get("project", {})
        raw_path = str(project.get("project_path") or "").strip()
        if not raw_path:
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        project_path = Path(raw_path)
        node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
        if node_dir is None:
            raise NodeNotFound(node_id)
        return node_dir

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_path")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _is_missing_thread_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message

    def _job_key(self, project_id: str, node_id: str) -> str:
        return f"{project_id}::{node_id}"

    def _mark_live_job(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_jobs_lock:
            self._live_jobs[self._job_key(project_id, node_id)] = turn_id

    def _clear_live_job(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_jobs_lock:
            key = self._job_key(project_id, node_id)
            if self._live_jobs.get(key) == turn_id:
                self._live_jobs.pop(key, None)
