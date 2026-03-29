from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.ai.auto_review_prompt_builder import (
    build_auto_review_base_instructions,
    build_auto_review_output_schema,
    build_auto_review_prompt,
    extract_auto_review_result,
)
from backend.ai.codex_client import CodexAppClient
from backend.conversation.services.thread_runtime_service import ThreadRuntimeService
from backend.conversation.services.workflow_event_publisher import WorkflowEventPublisher
from backend.ai.execution_prompt_builder import (
    build_execution_base_instructions,
    build_execution_prompt,
)
from backend.ai.part_accumulator import PartAccumulator
from backend.ai.split_context_builder import build_split_context
from backend.errors.app_errors import (
    ExecutionAuditRehearsalWorkspaceUnsafe,
    FinishTaskNotAllowed,
    NodeNotFound,
)
from backend.services import planningtree_workspace
from backend.services.node_detail_service import (
    NodeDetailService,
    _DEFAULT_FRAME_META,
    _load_spec_meta_from_node_dir,
)
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, load_json, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)

_DRAFT_FLUSH_INTERVAL_SEC = 0.5

if TYPE_CHECKING:
    from backend.services.chat_service import ChatService
    from backend.services.review_service import ReviewService


class FinishTaskService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        node_detail_service: NodeDetailService,
        codex_client: CodexAppClient,
        thread_lineage_service: ThreadLineageService,
        chat_event_broker: ChatEventBroker,
        chat_timeout: int,
        chat_service: ChatService | None = None,
        git_checkpoint_service: Any = None,
        review_service: ReviewService | None = None,
        thread_runtime_service_v2: ThreadRuntimeService | None = None,
        workflow_event_publisher_v2: WorkflowEventPublisher | None = None,
        execution_audit_v2_rehearsal_enabled: bool = False,
        rehearsal_workspace_root: Path | None = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._node_detail_service = node_detail_service
        self._codex_client = codex_client
        self._thread_lineage_service = thread_lineage_service
        self._chat_event_broker = chat_event_broker
        self._chat_timeout = int(chat_timeout)
        self._chat_service = chat_service
        self._git_checkpoint_service = git_checkpoint_service
        self._review_service = review_service
        self._thread_runtime_service_v2 = thread_runtime_service_v2
        self._workflow_event_publisher_v2 = workflow_event_publisher_v2
        self._execution_audit_v2_rehearsal_enabled = bool(execution_audit_v2_rehearsal_enabled)
        self._rehearsal_workspace_root = (
            Path(rehearsal_workspace_root).expanduser().resolve()
            if rehearsal_workspace_root is not None
            else None
        )
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
        if self._execution_audit_v2_rehearsal_enabled:
            return self._finish_task_v2_rehearsal(
                project_id=project_id,
                node_id=node_id,
                spec_content=spec_content,
                frame_content=frame_content,
                task_context=task_context,
                workspace_root=workspace_root,
                node=node,
            )
        execution_session = self._ensure_execution_thread(project_id, node_id, workspace_root)
        thread_id = str(execution_session.get("thread_id") or "").strip()
        if not thread_id:
            raise FinishTaskNotAllowed("Execution bootstrap did not return a thread id.")

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
                "local_review_started_at": None,
                "local_review_prompt_consumed_at": None,
            }
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            if node.get("status") != "in_progress":
                node["status"] = "in_progress"
                snapshot["updated_at"] = now
                self._storage.project_store.save_snapshot(project_id, snapshot)

            session = self._storage.chat_state_store.read_session(
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

        # Resolve hierarchical_number and title for commit message
        h_number = str(node.get("hierarchical_number") or "")
        title = str(node.get("title") or "")

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
                "initial_sha": initial_sha,
                "hierarchical_number": h_number,
                "title": title,
            },
            daemon=True,
        ).start()

        return self._node_detail_service.get_detail_state(project_id, node_id)

    def _finish_task_v2_rehearsal(
        self,
        *,
        project_id: str,
        node_id: str,
        spec_content: str,
        frame_content: str,
        task_context: str,
        workspace_root: str | None,
        node: dict[str, Any],
    ) -> dict[str, Any]:
        if self._thread_runtime_service_v2 is None:
            raise FinishTaskNotAllowed("Execution rehearsal runtime is unavailable.")
        self._assert_rehearsal_workspace_allowed(workspace_root)
        execution_session = self._ensure_execution_thread(project_id, node_id, workspace_root)
        thread_id = str(execution_session.get("thread_id") or "").strip()
        if not thread_id:
            raise FinishTaskNotAllowed("Execution bootstrap did not return a thread id.")

        turn_id = new_id("exec")
        prompt = build_execution_prompt(
            spec_content=spec_content,
            frame_content=frame_content,
            task_context=task_context,
        )
        now = iso_now()
        initial_sha: str

        self._thread_runtime_service_v2.begin_turn(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            origin="execution",
            created_items=[],
            turn_id=turn_id,
        )

        try:
            with self._storage.project_lock(project_id):
                snapshot = self._storage.project_store.load_snapshot(project_id)
                node_index = snapshot.get("tree_state", {}).get("node_index", {})
                current_node = node_index.get(node_id)
                if current_node is None:
                    raise NodeNotFound(node_id)
                node_dir = self._resolve_node_dir(snapshot, node_id)
                self._validate_finish_task_locked(project_id, node_id, snapshot, current_node, node_dir)
                initial_sha = self._compute_initial_sha(project_id, node_id, snapshot)

                exec_state = {
                    "status": "executing",
                    "initial_sha": initial_sha,
                    "head_sha": None,
                    "started_at": now,
                    "completed_at": None,
                    "local_review_started_at": None,
                    "local_review_prompt_consumed_at": None,
                }
                self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

                if current_node.get("status") != "in_progress":
                    current_node["status"] = "in_progress"
                    snapshot["updated_at"] = now
                    self._storage.project_store.save_snapshot(project_id, snapshot)

                self._mark_live_job(project_id, node_id, turn_id)
        except Exception as exc:
            error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                turn_id=turn_id,
                thread_id=thread_id,
                message=str(exc),
            )
            self._thread_runtime_service_v2.complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                turn_id=turn_id,
                outcome="failed",
                error_item=error_item,
            )
            raise

        self._publish_workflow_refresh(
            project_id=project_id,
            node_id=node_id,
            reason="execution_started",
        )

        threading.Thread(
            target=self._run_background_execution_v2_rehearsal,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "thread_id": thread_id,
                "prompt": prompt,
                "workspace_root": workspace_root,
                "initial_sha": initial_sha,
                "hierarchical_number": str(node.get("hierarchical_number") or ""),
                "title": str(node.get("title") or ""),
            },
            daemon=True,
        ).start()

        return self._node_detail_service.get_detail_state(project_id, node_id)

    def complete_execution(
        self,
        project_id: str,
        node_id: str,
        head_sha: str | None = None,
        commit_message: str | None = None,
        changed_files: list[dict[str, Any]] | None = None,
        *,
        publish_legacy_event: bool = True,
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
            if commit_message is not None:
                exec_state["commit_message"] = commit_message
            if changed_files is not None:
                exec_state["changed_files"] = changed_files
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

        detail_state = self._node_detail_service.get_detail_state(project_id, node_id)
        if publish_legacy_event:
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

    def fail_execution(
        self,
        project_id: str,
        node_id: str,
        error_message: str,
    ) -> None:
        """Persist execution as failed. Allows retry."""
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                return
            exec_state["status"] = "failed"
            exec_state["completed_at"] = iso_now()
            exec_state["error_message"] = error_message
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

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
        initial_sha: str = "",
        hierarchical_number: str = "",
        title: str = "",
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
                items=accumulator.snapshot_items(),
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
                    "item_id": "assistant_text",
                    "item_type": "assistant_text",
                    "phase": "delta",
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
                item_id = accumulator.on_tool_call(tool_name, arguments)
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
                    "item_id": item_id,
                    "item_type": "tool_call",
                    "phase": "started",
                },
                thread_role="execution",
            )

            with draft_lock:
                persist_activity_snapshot()

        def capture_item_event(phase: str, item: dict[str, Any]) -> None:
            with draft_lock:
                lifecycle_item_id = accumulator.on_item_event(phase, item)
            item_type = str(item.get("type") or "").strip()
            if item_type != "commandExecution":
                return

            call_id = str(item.get("id") or "").strip() or None
            tool_name = "shell_command"
            arguments = {
                "command": item.get("command"),
                "cwd": item.get("cwd"),
                "source": item.get("source"),
            }

            if phase == "started":
                with draft_lock:
                    tool_item_id = accumulator.on_tool_call(tool_name, arguments, call_id=call_id)
                    part_index = len(accumulator.parts) - 1
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_tool_call",
                        "message_id": assistant_message_id,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "call_id": call_id,
                        "part_index": part_index,
                        "item_id": tool_item_id,
                        "item_type": "tool_call",
                        "phase": "started",
                    },
                    thread_role="execution",
                )
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_item_lifecycle",
                        "message_id": assistant_message_id,
                        "item_id": lifecycle_item_id,
                        "item_type": item_type,
                        "phase": "started",
                        "payload": item,
                    },
                    thread_role="execution",
                )
                with draft_lock:
                    persist_activity_snapshot()
                return

            raw_status = str(item.get("status") or "").strip().lower()
            status = "error" if raw_status in {"failed", "incomplete", "error"} else "completed"
            output = item.get("aggregatedOutput")
            exit_code = item.get("exitCode")
            parsed_output = output if isinstance(output, str) and output else None
            parsed_exit_code = int(exit_code) if isinstance(exit_code, int) else None

            with draft_lock:
                tool_item_id = accumulator.on_tool_result(
                    call_id,
                    status=status,
                    output=parsed_output,
                    exit_code=parsed_exit_code,
                )
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_tool_result",
                    "message_id": assistant_message_id,
                    "call_id": call_id,
                    "status": status,
                    "output": parsed_output,
                    "exit_code": parsed_exit_code,
                    "item_id": tool_item_id,
                    "item_type": "tool_call",
                    "phase": "error" if status == "error" else "completed",
                },
                thread_role="execution",
            )
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_item_lifecycle",
                    "message_id": assistant_message_id,
                    "item_id": lifecycle_item_id,
                    "item_type": item_type,
                    "phase": "completed",
                    "payload": item,
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
                    "item_id": "thread_status",
                    "item_type": "thread_status",
                    "phase": "delta",
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
                    "item_type": "plan_item",
                    "phase": "delta",
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
                on_item_event=capture_item_event,
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
                final_items = accumulator.snapshot_items()
                streamed_content = accumulator.content_projection()
            stdout = str(result.get("stdout", "") or "")
            final_content = stdout or streamed_content

            # 1. CRITICAL: git commit. Failure → fail_execution()
            head_sha: str | None = None
            commit_msg: str | None = None
            changed: list[dict[str, Any]] = []
            if self._git_checkpoint_service is not None and workspace_root:
                commit_msg = self._git_checkpoint_service.build_commit_message(
                    hierarchical_number, title
                )
                new_sha = self._git_checkpoint_service.commit_if_changed(
                    Path(workspace_root), commit_msg
                )
                head_sha = new_sha if new_sha else initial_sha

                # 2. BEST-EFFORT: changed files metadata
                if new_sha:
                    try:
                        from backend.errors.app_errors import GitCheckpointError
                        changed = self._git_checkpoint_service.get_changed_files(
                            Path(workspace_root), initial_sha, head_sha
                        )
                    except Exception:
                        logger.warning(
                            "Failed to collect changed files for %s/%s",
                            project_id, node_id,
                        )
                        changed = []
                else:
                    commit_msg = None  # No diff → no commit message
            else:
                from backend.services.workspace_sha import compute_workspace_sha
                head_sha = compute_workspace_sha(Path(workspace_root)) if workspace_root else None

            # 3. CRITICAL: execution state → completed
            self.complete_execution(
                project_id, node_id,
                head_sha=head_sha,
                commit_message=commit_msg,
                changed_files=changed,
            )

            # === POINT OF NO RETURN: execution state is "completed" ===
            # Errors below are best-effort only — do NOT call fail_execution()

            # 4. BEST-EFFORT: finalize execution chat message first (clears active_turn_id)
            try:
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
                    items=final_items,
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
            except Exception:
                logger.warning("Failed to persist/publish completed message for %s/%s", project_id, node_id)

            # 5. BEST-EFFORT: start automated local review (after execution session is finalized)
            try:
                self._start_auto_review(
                    project_id=project_id,
                    node_id=node_id,
                    workspace_root=workspace_root,
                )
            except Exception:
                logger.warning(
                    "Failed to start auto-review for %s/%s",
                    project_id,
                    node_id,
                    exc_info=True,
                )
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
                    items=accumulator.snapshot_items(),
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
                self.fail_execution(project_id, node_id, error_message=str(exc))
            except Exception:
                logger.debug("Failed to persist failed execution state", exc_info=True)
        finally:
            self._clear_live_job(project_id, node_id, turn_id)

    def _run_background_execution_v2_rehearsal(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        thread_id: str,
        prompt: str,
        workspace_root: str | None,
        initial_sha: str = "",
        hierarchical_number: str = "",
        title: str = "",
    ) -> None:
        if self._thread_runtime_service_v2 is None:
            logger.warning(
                "Skipping V2 rehearsal execution for %s/%s: runtime unavailable.",
                project_id,
                node_id,
            )
            self._clear_live_job(project_id, node_id, turn_id)
            return

        turn_finalized = False
        try:
            stream_result = self._thread_runtime_service_v2.stream_agent_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                thread_id=thread_id,
                turn_id=turn_id,
                prompt=prompt,
                cwd=workspace_root,
                writable_roots=[workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None,
                timeout_sec=self._chat_timeout,
            )
            result = stream_result["result"]
            turn_status = str(stream_result.get("turnStatus") or "").strip().lower()
            outcome = self._thread_runtime_service_v2.outcome_from_turn_status(turn_status)
            if outcome != "completed":
                error_message = f"Execution rehearsal returned terminal status '{turn_status or 'unknown'}'."
                error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role="execution",
                    turn_id=turn_id,
                    thread_id=thread_id,
                    message=error_message,
                )
                self._thread_runtime_service_v2.complete_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role="execution",
                    turn_id=turn_id,
                    outcome="failed",
                    error_item=error_item,
                )
                turn_finalized = True
                raise FinishTaskNotAllowed(error_message)

            head_sha: str | None = None
            commit_msg: str | None = None
            changed: list[dict[str, Any]] = []
            if self._git_checkpoint_service is not None and workspace_root:
                commit_msg = self._git_checkpoint_service.build_commit_message(
                    hierarchical_number, title
                )
                new_sha = self._git_checkpoint_service.commit_if_changed(
                    Path(workspace_root), commit_msg
                )
                head_sha = new_sha if new_sha else initial_sha
                if new_sha:
                    try:
                        changed = self._git_checkpoint_service.get_changed_files(
                            Path(workspace_root), initial_sha, head_sha
                        )
                    except Exception:
                        logger.warning(
                            "Failed to collect changed files for %s/%s",
                            project_id,
                            node_id,
                        )
                        changed = []
                else:
                    commit_msg = None
            else:
                from backend.services.workspace_sha import compute_workspace_sha

                head_sha = compute_workspace_sha(Path(workspace_root)) if workspace_root else None

            self.complete_execution(
                project_id,
                node_id,
                head_sha=head_sha,
                commit_message=commit_msg,
                changed_files=changed,
                publish_legacy_event=False,
            )
            self._thread_runtime_service_v2.complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                turn_id=turn_id,
                outcome="completed",
            )
            turn_finalized = True

            if self._review_service is not None:
                try:
                    self._review_service.start_local_review(project_id, node_id)
                except Exception:
                    logger.debug(
                        "Failed to auto-open local review after rehearsal execution for %s/%s",
                        project_id,
                        node_id,
                        exc_info=True,
                    )

            self._publish_workflow_refresh(
                project_id=project_id,
                node_id=node_id,
                reason="execution_completed",
            )
        except Exception as exc:
            logger.debug(
                "V2 rehearsal execution failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            if not turn_finalized:
                try:
                    error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="execution",
                        turn_id=turn_id,
                        thread_id=thread_id,
                        message=str(exc),
                    )
                    self._thread_runtime_service_v2.complete_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="execution",
                        turn_id=turn_id,
                        outcome="failed",
                        error_item=error_item,
                    )
                    turn_finalized = True
                except Exception:
                    logger.debug(
                        "Failed to finalize V2 rehearsal execution turn for %s/%s",
                        project_id,
                        node_id,
                        exc_info=True,
                    )

            try:
                self.fail_execution(project_id, node_id, error_message=str(exc))
            except Exception:
                logger.debug("Failed to persist failed rehearsal execution state", exc_info=True)
            self._publish_workflow_refresh(
                project_id=project_id,
                node_id=node_id,
                reason="execution_failed",
            )
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

        exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
        if exec_state is not None:
            status = exec_state.get("status")
            if status == "executing":
                raise FinishTaskNotAllowed("Execution is already in progress for this node.")
            if status == "failed":
                pass  # Allow retry from failed
            elif status is not None and status != "idle":
                raise FinishTaskNotAllowed("Execution has already been started for this node.")

        spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
        spec_content = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        if not spec_content.strip():
            raise FinishTaskNotAllowed("Spec must be non-empty before Finish Task.")

        # Git guardrails
        if self._git_checkpoint_service is not None:
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if workspace_root:
                expected_head = self._resolve_expected_baseline_sha(project_id, node_id, snapshot)
                blockers = self._git_checkpoint_service.validate_guardrails(
                    Path(workspace_root), expected_head=expected_head
                )
                if blockers:
                    raise FinishTaskNotAllowed(blockers[0])

        return spec_content

    def _ensure_execution_thread(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> dict[str, Any]:
        writable_roots = [workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None
        try:
            return self._thread_lineage_service.ensure_forked_thread(
                project_id,
                node_id,
                "execution",
                source_node_id=node_id,
                source_role="audit",
                fork_reason="execution_bootstrap",
                workspace_root=workspace_root,
                base_instructions=build_execution_base_instructions(),
                dynamic_tools=[],
                writable_roots=writable_roots,
            )
        except Exception as exc:
            raise FinishTaskNotAllowed(f"Execution backend unavailable: {exc}") from exc

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
        items: list[dict[str, Any]] | None = None,
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
            if items is not None:
                message["items"] = items

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

    def _resolve_expected_baseline_sha(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
    ) -> str | None:
        """Resolve the expected git HEAD from the checkpoint chain.

        Returns a git commit SHA (40-char hex) for guardrail check 7,
        or None if no baseline can be determined (root node, split before git init).
        """
        node_index = snapshot.get("tree_state", {}).get("node_index", {})
        node = node_index.get(node_id, {})
        parent_id = node.get("parent_id")

        if not parent_id:
            return None

        parent = node_index.get(parent_id, {})
        review_node_id = parent.get("review_node_id")
        if not review_node_id:
            return None

        review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
        if not review_state:
            return None

        checkpoints = review_state.get("checkpoints", [])
        if not checkpoints:
            return None

        latest_sha = checkpoints[-1].get("sha", "")
        if self._git_checkpoint_service is not None:
            if self._git_checkpoint_service.is_git_commit_sha(latest_sha):
                return latest_sha
            # K0 uses sha256: format — fall back to k0_git_head_sha
            k0_git_head = review_state.get("k0_git_head_sha")
            if self._git_checkpoint_service.is_git_commit_sha(k0_git_head):
                return k0_git_head

        return None

    def _compute_initial_sha(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
    ) -> str:
        """Capture initial SHA for execution. Uses git if available, falls back to workspace SHA."""
        if self._git_checkpoint_service is not None:
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if workspace_root:
                return self._git_checkpoint_service.capture_head_sha(Path(workspace_root))

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

    def _assert_rehearsal_workspace_allowed(self, workspace_root: str | None) -> Path:
        raw_workspace_root = str(workspace_root or "").strip()
        if not raw_workspace_root:
            raise ExecutionAuditRehearsalWorkspaceUnsafe(
                "Execution/audit V2 rehearsal requires a project workspace root."
            )
        if self._rehearsal_workspace_root is None:
            raise ExecutionAuditRehearsalWorkspaceUnsafe(
                "Execution/audit V2 rehearsal requires PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT to be configured."
            )
        resolved_workspace_root = Path(raw_workspace_root).expanduser().resolve()
        try:
            resolved_workspace_root.relative_to(self._rehearsal_workspace_root)
        except ValueError as exc:
            raise ExecutionAuditRehearsalWorkspaceUnsafe(
                "Execution/audit V2 rehearsal is allowed only for workspaces under the configured rehearsal root."
            ) from exc
        return resolved_workspace_root

    def _publish_workflow_refresh(self, *, project_id: str, node_id: str, reason: str) -> None:
        if self._workflow_event_publisher_v2 is None:
            return
        exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
        execution_status = (str(exec_state.get("status") or "").strip() or None) if exec_state else None
        self._workflow_event_publisher_v2.publish_workflow_updated(
            project_id=project_id,
            node_id=node_id,
            execution_state=execution_status,
            review_state=None,
        )
        self._workflow_event_publisher_v2.publish_detail_invalidate(
            project_id=project_id,
            node_id=node_id,
            reason=reason,
        )

    def _job_key(self, project_id: str, node_id: str) -> str:
        return f"{project_id}::{node_id}"

    def _mark_live_job(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_jobs_lock:
            self._live_jobs[self._job_key(project_id, node_id)] = turn_id
        if self._chat_service is not None:
            self._chat_service.register_external_live_turn(
                project_id,
                node_id,
                "execution",
                turn_id,
            )

    def _clear_live_job(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_jobs_lock:
            key = self._job_key(project_id, node_id)
            if self._live_jobs.get(key) == turn_id:
                self._live_jobs.pop(key, None)
        if self._chat_service is not None:
            self._chat_service.clear_external_live_turn(
                project_id,
                node_id,
                "execution",
                turn_id,
            )

    # -- Automated Local Review --------------------------------------

    def _start_auto_review(
        self,
        *,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> bool:
        if self._codex_client is None or self._chat_event_broker is None:
            logger.debug(
                "Skipping auto-review for %s/%s: dependencies unavailable.",
                project_id,
                node_id,
            )
            return False

        turn_id = new_id("auto_review")
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

        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None or exec_state.get("status") != "completed":
                logger.debug(
                    "Skipping auto-review for %s/%s: execution status is not 'completed'.",
                    project_id,
                    node_id,
                )
                return False

            existing_auto_review = exec_state.get("auto_review")
            if isinstance(existing_auto_review, dict) and existing_auto_review.get("status") in (
                "running",
                "completed",
            ):
                logger.debug(
                    "Skipping auto-review for %s/%s: already %s.",
                    project_id,
                    node_id,
                    existing_auto_review.get("status"),
                )
                return False

            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role="audit"
            )
            if session.get("active_turn_id"):
                logger.warning(
                    "Skipping auto-review for %s/%s: audit session already has active turn %s.",
                    project_id,
                    node_id,
                    session.get("active_turn_id"),
                )
                return False

            session["active_turn_id"] = turn_id
            session["messages"].append(assistant_message)
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="audit"
            )

            exec_state["auto_review"] = {
                "status": "running",
                "started_at": now,
                "completed_at": None,
                "summary": None,
                "checkpoint_summary": None,
                "overall_severity": None,
                "overall_score": None,
                "findings": [],
                "error_message": None,
                "review_message_id": assistant_message_id,
            }
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

        if self._chat_service is not None:
            self._chat_service.register_external_live_turn(
                project_id, node_id, "audit", turn_id
            )

        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "message_created",
                "assistant_message": assistant_message,
                "active_turn_id": turn_id,
            },
            thread_role="audit",
        )
        self._chat_event_broker.publish(
            project_id,
            node_id,
            {"type": "auto_review_started", "node_id": node_id, "turn_id": turn_id, "message_id": assistant_message_id},
            thread_role="audit",
        )

        threading.Thread(
            target=self._run_background_auto_review,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message_id,
                "workspace_root": workspace_root,
            },
            daemon=True,
        ).start()
        return True

    def _run_background_auto_review(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        workspace_root: str | None,
    ) -> None:
        thread_id: str | None = None
        draft_lock = threading.Lock()
        accumulator = PartAccumulator()
        last_checkpoint_at = time.monotonic()

        def capture_delta(delta: str) -> None:
            nonlocal last_checkpoint_at
            checkpoint_content: str | None = None
            with draft_lock:
                accumulator.on_delta(delta)
                now_t = time.monotonic()
                if now_t - last_checkpoint_at >= _DRAFT_FLUSH_INTERVAL_SEC:
                    checkpoint_content = accumulator.content_projection()
                    last_checkpoint_at = now_t

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_delta",
                    "message_id": assistant_message_id,
                    "delta": delta,
                    "item_id": "assistant_text",
                    "item_type": "assistant_text",
                    "phase": "delta",
                },
                thread_role="audit",
            )

            if checkpoint_content is not None:
                self._persist_auto_review_message(
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
                    items=accumulator.snapshot_items(),
                )

        def capture_tool_call(tool_name: str, arguments: dict[str, Any]) -> None:
            with draft_lock:
                item_id = accumulator.on_tool_call(tool_name, arguments)
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
                    "item_id": item_id,
                    "item_type": "tool_call",
                    "phase": "started",
                },
                thread_role="audit",
            )

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
                    "item_id": "thread_status",
                    "item_type": "thread_status",
                    "phase": "delta",
                },
                thread_role="audit",
            )

        try:
            if self._thread_lineage_service is None:
                raise FinishTaskNotAllowed("Thread lineage service unavailable for auto-review.")

            session = self._thread_lineage_service.resume_or_rebuild_session(
                project_id,
                node_id,
                "audit",
                workspace_root,
                base_instructions=build_auto_review_base_instructions(),
            )
            thread_id = str(session.get("thread_id") or "").strip()
            if not thread_id:
                raise FinishTaskNotAllowed("Auto-review audit thread did not return a thread id.")

            self._persist_auto_review_thread_id(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                thread_id=thread_id,
            )

            prompt = build_auto_review_prompt(
                self._storage,
                project_id,
                node_id,
                workspace_root,
                self._git_checkpoint_service,
            )

            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                writable_roots=None,
                sandbox_profile="read_only",
                on_delta=capture_delta,
                on_tool_call=capture_tool_call,
                on_thread_status=capture_thread_status,
                output_schema=build_auto_review_output_schema(),
            )

            with draft_lock:
                accumulator.finalize()
                streamed_content = accumulator.content_projection()
                final_parts = accumulator.snapshot_parts()
                final_items = accumulator.snapshot_items()

            stdout = str(result.get("stdout", "") or "")
            review_result = extract_auto_review_result(stdout) or extract_auto_review_result(
                streamed_content
            )
            if not review_result:
                raise FinishTaskNotAllowed(
                    "Auto-review did not return a valid structured result."
                )

            now = iso_now()
            with self._storage.project_lock(project_id):
                exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
                if exec_state is not None:
                    auto_review = exec_state.get("auto_review") or {}
                    auto_review.update({
                        "status": "completed",
                        "completed_at": now,
                        "summary": review_result["summary"],
                        "checkpoint_summary": review_result["checkpoint_summary"],
                        "overall_severity": review_result["overall_severity"],
                        "overall_score": review_result["overall_score"],
                        "findings": review_result["findings"],
                        "error_message": None,
                    })
                    exec_state["auto_review"] = auto_review
                    self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            severity = review_result["overall_severity"]
            score = review_result["overall_score"]
            final_content = (
                f"## Automated Local Review\n\n"
                f"**Severity:** {severity} | **Score:** {score}/100\n\n"
                f"{review_result['summary']}"
            )

            finalized_parts = [dict(p) for p in final_parts if p.get("type") != "assistant_text"]
            finalized_parts.append({"type": "assistant_text", "content": final_content, "is_streaming": False})

            persisted = self._persist_auto_review_message(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=final_content,
                status="completed",
                error=None,
                thread_id=str(result.get("thread_id") or thread_id or ""),
                clear_active_turn=True,
                parts=finalized_parts,
                items=final_items,
            )

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_completed",
                        "message_id": assistant_message_id,
                        "content": final_content,
                        "thread_id": str(result.get("thread_id") or thread_id or ""),
                    },
                    thread_role="audit",
                )
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "auto_review_completed",
                        "node_id": node_id,
                        "overall_severity": severity,
                        "overall_score": score,
                        "summary": review_result["summary"],
                    },
                    thread_role="audit",
                )

            self._auto_accept_local_review(project_id=project_id, node_id=node_id)

        except Exception as exc:
            logger.debug(
                "Auto-review failed for %s/%s: %s",
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

                now = iso_now()
                with self._storage.project_lock(project_id):
                    exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
                    if exec_state is not None:
                        auto_review = exec_state.get("auto_review") or {}
                        auto_review.update({
                            "status": "failed",
                            "completed_at": now,
                            "error_message": str(exc),
                        })
                        exec_state["auto_review"] = auto_review
                        self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

                persisted = self._persist_auto_review_message(
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
                    items=accumulator.snapshot_items(),
                )
            except Exception:
                persisted = False
                logger.debug("Failed to persist auto-review error state", exc_info=True)

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {"type": "assistant_error", "message_id": assistant_message_id, "error": str(exc)},
                    thread_role="audit",
                )
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {"type": "auto_review_failed", "node_id": node_id, "error": str(exc)},
                thread_role="audit",
            )
        finally:
            if self._chat_service is not None:
                self._chat_service.clear_external_live_turn(
                    project_id, node_id, "audit", turn_id
                )

    def _auto_accept_local_review(self, *, project_id: str, node_id: str) -> None:
        if self._review_service is None:
            logger.debug(
                "Skipping auto-accept for %s/%s: review_service unavailable.",
                project_id,
                node_id,
            )
            return

        try:
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None or exec_state.get("status") != "completed":
                logger.debug(
                    "Skipping auto-accept for %s/%s: execution status is not 'completed'.",
                    project_id,
                    node_id,
                )
                return

            auto_review = exec_state.get("auto_review") or {}
            checkpoint_summary = str(auto_review.get("checkpoint_summary") or "").strip()
            overall_severity = str(auto_review.get("overall_severity") or "info").strip()
            overall_score = auto_review.get("overall_score")
            score_str = str(overall_score) if isinstance(overall_score, int) else "?"
            full_summary = f"[Auto-reviewed: {overall_severity}/{score_str}] {checkpoint_summary}"

            self._review_service.start_local_review(project_id, node_id)
            response = self._review_service.accept_local_review(project_id, node_id, full_summary)
            activated_sibling_id = response.get("activated_sibling_id")

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "auto_review_accepted",
                    "node_id": node_id,
                    "activated_sibling_id": activated_sibling_id,
                },
                thread_role="audit",
            )
        except Exception as exc:
            logger.warning(
                "Auto-accept failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )

    def _persist_auto_review_message(
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
                project_id, node_id, thread_role="audit"
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
            if items is not None:
                message["items"] = items
            if thread_id is not None:
                session["thread_id"] = thread_id
            if clear_active_turn:
                session["active_turn_id"] = None

            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="audit"
            )
            return True

    def _persist_auto_review_thread_id(
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
                project_id, node_id, thread_role="audit"
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            msg_found = any(
                m.get("message_id") == assistant_message_id
                for m in session.get("messages", [])
            )
            if not msg_found:
                return False
            session["thread_id"] = thread_id
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="audit"
            )
            return True
