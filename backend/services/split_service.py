from __future__ import annotations

import logging
import threading
from typing import Any
from uuid import uuid4

from backend.ai.codex_client import CodexAppClient
from backend.ai.split_context_builder import build_split_context
from backend.ai.legacy_split_prompt_builder import (
    build_legacy_hidden_retry_feedback,
    build_legacy_split_user_message,
    legacy_split_payload_issues,
    validate_legacy_split_payload,
)
from backend.errors.app_errors import InvalidRequest, NodeNotFound, SplitNotAllowed
from backend.services.agent_operation_service import (
    AgentOperationHandle,
    AgentOperationService,
    clear_last_agent_failure,
    set_last_agent_failure,
)
from backend.services.node_task_fields import enrich_nodes_with_task_fields
from backend.services.planning_conversation_adapter import (
    build_planning_split_summary,
    extract_split_payload,
    make_planning_stream_id,
)
from backend.services.thread_service import ThreadService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, load_json, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import PlanningEventBroker

_PHASE_KEYS = ["A", "B", "C", "D", "E"]
_RETRY_LIMIT = 2

logger = logging.getLogger(__name__)


class SplitService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient,
        thread_service: ThreadService,
        planning_event_broker: PlanningEventBroker,
        split_timeout: int,
        agent_operation_service: AgentOperationService | None = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client
        self._thread_service = thread_service
        self._planning_event_broker = planning_event_broker
        self._agent_operation_service = agent_operation_service
        self._split_timeout = int(split_timeout)
        self._live_turns_lock = threading.Lock()
        self._live_turns: set[tuple[str, str]] = set()

    def split_node(
        self,
        project_id: str,
        node_id: str,
        mode: str,
        confirm_replace: bool = False,
    ) -> dict[str, Any]:
        if mode not in {"walking_skeleton", "slice"}:
            raise InvalidRequest("Unsupported split mode.")

        handle: AgentOperationHandle | None = None

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            parent = node_by_id.get(node_id)
            if parent is None:
                raise NodeNotFound(node_id)
            self._validate_split_eligibility(parent, node_by_id, confirm_replace)
            planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
            if planning_state.get("status") == "active" or self._is_live_turn(project_id, node_id):
                raise SplitNotAllowed("A planning turn is already active for this node.")
            if self._agent_operation_service is not None and self._agent_operation_service.is_active(project_id, node_id):
                raise SplitNotAllowed("Another agent operation is already active for this node.")

        if self._agent_operation_service is not None:
            try:
                handle = self._agent_operation_service.start_operation(project_id, node_id, "split")
            except RuntimeError as exc:
                raise SplitNotAllowed(str(exc)) from exc

        try:
            self._thread_service.ensure_planning_thread(project_id, node_id)
            turn_id = new_id("planturn")
            visible_user_message = self._build_visible_user_message(project_id, node_id, mode)
            with self._storage.project_lock(project_id):
                snapshot = self._storage.project_store.load_snapshot(project_id)
                node_by_id = self._tree_service.node_index(snapshot)
                parent = node_by_id.get(node_id)
                if parent is None:
                    raise NodeNotFound(node_id)
                self._validate_split_eligibility(parent, node_by_id, confirm_replace)
                planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
                if planning_state.get("status") == "active" or self._is_live_turn(project_id, node_id):
                    raise SplitNotAllowed("A planning turn is already active for this node.")
                self._assert_no_unresolved_ask_packets(project_id, node_id)
                state = self._storage.node_store.load_state(project_id, node_id)
                clear_last_agent_failure(state)
                self._storage.node_store.save_state(project_id, node_id, state)
                planning_start = self._storage.thread_store.start_planning_conversation_turn(
                    project_id,
                    node_id,
                    thread_id=str(parent.get("planning_thread_id") or "").strip() or None,
                    forked_from_node=str(parent.get("planning_thread_forked_from_node") or "").strip() or None,
                    active_turn_id=turn_id,
                    pending_user_content=visible_user_message,
                    pending_started_at=iso_now(),
                )
                self._thread_service.set_planning_status(
                    project_id,
                    node_id,
                    status="active",
                    active_turn_id=turn_id,
                )
                self._mark_live_turn(project_id, node_id)
        except Exception:
            if handle is not None and self._agent_operation_service is not None:
                self._agent_operation_service.finish_operation(handle)
            raise

        started_at = iso_now()
        if handle is not None and self._agent_operation_service is not None:
            self._agent_operation_service.publish_started(
                handle,
                stage="preparing",
                message="Preparing split.",
            )
        self._planning_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "planning_turn_started",
                "node_id": node_id,
                "turn_id": turn_id,
                "mode": mode,
                "timestamp": started_at,
                "conversation_id": planning_start["planning"]["conversation_id"],
                "stream_id": make_planning_stream_id(turn_id),
                "user_content": visible_user_message,
                "user_event_seq": planning_start["user_event_seq"],
                "assistant_event_seq": planning_start["assistant_event_seq"],
            },
        )
        self._start_background_split(
            project_id=project_id,
            node_id=node_id,
            mode=mode,
            confirm_replace=confirm_replace,
            turn_id=turn_id,
            visible_user_message=visible_user_message,
            handle=handle,
        )
        return {
            "status": "accepted",
            "node_id": node_id,
            "mode": mode,
            "planning_status": "active",
        }

    def _assert_no_unresolved_ask_packets(self, project_id: str, node_id: str) -> None:
        ask_state = self._storage.thread_store.get_ask_state(project_id, node_id)
        unresolved_packets = [
            packet
            for packet in ask_state.get("delta_context_packets", [])
            if isinstance(packet, dict) and packet.get("status") in {"pending", "approved"}
        ]
        if unresolved_packets:
            raise SplitNotAllowed("Resolve ask-thread delta context packets before splitting this node.")

    def get_planning_history(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            if node_id not in node_by_id:
                raise NodeNotFound(node_id)
        turns = self._thread_service.materialize_inherited_planning_history(project_id, node_id)
        return {"node_id": node_id, "turns": turns}

    def _start_background_split(
        self,
        *,
        project_id: str,
        node_id: str,
        mode: str,
        confirm_replace: bool,
        turn_id: str,
        visible_user_message: str,
        handle: AgentOperationHandle | None,
    ) -> None:
        threading.Thread(
            target=self._run_background_split,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "mode": mode,
                "confirm_replace": confirm_replace,
                "turn_id": turn_id,
                "visible_user_message": visible_user_message,
                "handle": handle,
            },
            daemon=True,
        ).start()

    def _run_background_split(
        self,
        *,
        project_id: str,
        node_id: str,
        mode: str,
        confirm_replace: bool,
        turn_id: str,
        visible_user_message: str,
        handle: AgentOperationHandle | None,
    ) -> None:
        try:
            result = self._execute_split_turn(
                project_id=project_id,
                node_id=node_id,
                mode=mode,
                confirm_replace=confirm_replace,
                turn_id=turn_id,
                user_message_override=visible_user_message,
            )
            visible_user_message = result["user_message"]
            tool_calls = result["tool_calls"]
            assistant_content = result["assistant_content"]
            timestamp = result["timestamp"]
            fallback_used = bool(result["fallback_used"])
            created_child_ids = list(result["created_child_ids"])
            tool_event_published = bool(result["tool_event_published"])
            readable_summary = build_planning_split_summary(
                payload=extract_split_payload(tool_calls),
                created_child_ids=created_child_ids,
            )
            if not tool_event_published:
                for tool_call in tool_calls:
                    self._planning_event_broker.publish(
                        project_id,
                        node_id,
                        self._planning_tool_call_event(node_id, turn_id, tool_call),
                    )

            planning_finish = self._storage.thread_store.finish_planning_conversation_turn(project_id, node_id)
            self._planning_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "planning_turn_completed",
                    "node_id": node_id,
                    "turn_id": turn_id,
                    "created_child_ids": created_child_ids,
                    "fallback_used": fallback_used,
                    "timestamp": timestamp,
                    "conversation_id": planning_finish["planning"]["conversation_id"],
                    "stream_id": make_planning_stream_id(turn_id),
                    "assistant_text": readable_summary,
                    "assistant_text_event_seq": planning_finish["assistant_text_event_seq"],
                    "completion_event_seq": planning_finish["completion_event_seq"],
                },
            )
            if handle is not None and self._agent_operation_service is not None:
                self._agent_operation_service.publish_completed(
                    handle,
                    stage="completed",
                    message="Split completed.",
                )
        except Exception as exc:
            logger.exception("Split planning turn failed for node %s", node_id)
            timestamp = iso_now()
            existing_turns = self._storage.thread_store.get_planning_turns(project_id, node_id)
            turn_already_persisted = any(
                isinstance(entry, dict) and str(entry.get("turn_id") or "") == turn_id
                for entry in existing_turns
            )
            if visible_user_message and not turn_already_persisted:
                self._thread_service.append_visible_planning_turn(
                    project_id,
                    node_id,
                    turn_id=turn_id,
                    user_content=visible_user_message,
                    tool_calls=[],
                    assistant_content=f"Split failed: {exc}",
                    timestamp=timestamp,
                )
            planning_finish = self._storage.thread_store.finish_planning_conversation_turn(project_id, node_id)
            self._planning_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "planning_turn_failed",
                    "node_id": node_id,
                    "turn_id": turn_id,
                    "message": str(exc),
                    "timestamp": timestamp,
                    "conversation_id": planning_finish["planning"]["conversation_id"],
                    "stream_id": make_planning_stream_id(turn_id),
                    "assistant_text": f"Split failed: {exc}",
                    "assistant_text_event_seq": planning_finish["assistant_text_event_seq"],
                    "completion_event_seq": planning_finish["completion_event_seq"],
                },
            )
            if handle is not None and self._agent_operation_service is not None:
                with self._storage.project_lock(project_id):
                    failed_state = self._storage.node_store.load_state(project_id, node_id)
                    set_last_agent_failure(
                        failed_state,
                        operation="split",
                        message=str(exc),
                    )
                    self._storage.node_store.save_state(project_id, node_id, failed_state)
                self._agent_operation_service.publish_failed(
                    handle,
                    stage="failed",
                    message=str(exc),
                )
        finally:
            self._clear_live_turn(project_id, node_id)
            if handle is not None and self._agent_operation_service is not None:
                self._agent_operation_service.finish_operation(handle)

    def _build_visible_user_message(self, project_id: str, node_id: str, mode: str) -> str:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            enrich_nodes_with_task_fields(self._storage.node_store, project_id, node_by_id)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            task_context = build_split_context(snapshot, node, node_by_id)
        return build_legacy_split_user_message(mode, task_context)

    def _execute_split_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        mode: str,
        confirm_replace: bool,
        turn_id: str,
        user_message_override: str | None = None,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            enrich_nodes_with_task_fields(self._storage.node_store, project_id, node_by_id)
            parent = node_by_id.get(node_id)
            if parent is None:
                raise NodeNotFound(node_id)
            self._validate_split_eligibility(parent, node_by_id, confirm_replace)
            task_context = build_split_context(snapshot, parent, node_by_id)
            planning_thread_id = str(parent.get("planning_thread_id") or "").strip()
            workspace_root = self._workspace_root_from_snapshot(snapshot)

        if not planning_thread_id:
            planning_thread_id = self._thread_service.ensure_planning_thread(project_id, node_id)

        user_message = user_message_override or build_legacy_split_user_message(mode, task_context)
        tool_event_published = False

        def on_visible_tool_call(tool_name: str, arguments: dict[str, Any]) -> None:
            nonlocal tool_event_published
            if tool_name != "emit_render_data":
                return
            if not isinstance(arguments, dict):
                return
            if str(arguments.get("kind") or "") != "split_result":
                return
            payload = arguments.get("payload")
            if not isinstance(payload, dict) or not validate_legacy_split_payload(mode, payload):
                return
            tool_call = {
                "tool_name": tool_name,
                "arguments": arguments,
            }
            self._planning_event_broker.publish(
                project_id,
                node_id,
                self._planning_tool_call_event(node_id, turn_id, tool_call),
            )
            tool_event_published = True

        response = self._codex_client.run_turn_streaming(
            user_message,
            thread_id=planning_thread_id,
            timeout_sec=self._split_timeout,
            cwd=workspace_root,
            on_tool_call=on_visible_tool_call,
        )
        resolved = self._resolve_tool_payload(mode, response.get("tool_calls", []))
        assistant_content = str(response.get("stdout", ""))
        issues = self._tool_payload_issues(mode, response.get("tool_calls", []))

        if resolved is None:
            resolved = self._retry_hidden_split_turns(
                project_id=project_id,
                node_id=node_id,
                mode=mode,
                planning_thread_id=planning_thread_id,
                workspace_root=workspace_root,
                issues=issues,
            )
            if resolved is not None:
                assistant_content = str(resolved.get("assistant_content") or assistant_content)

        fallback_used = False
        if resolved is None:
            payload = self._deterministic_fallback(mode, task_context)
            resolved = {
                "payload": payload,
                "tool_calls": [self._render_tool_call(payload)],
            }
            assistant_content = "I could not produce a valid structured split, so I applied the deterministic fallback split."
            fallback_used = True

        creation = self._apply_split_payload(
            project_id=project_id,
            node_id=node_id,
            mode=mode,
            confirm_replace=confirm_replace,
            payload=resolved["payload"],
            source="fallback" if fallback_used else "ai",
            task_context=task_context,
        )

        self._thread_service.append_visible_planning_turn(
            project_id,
            node_id,
            turn_id=turn_id,
            user_content=user_message,
            tool_calls=resolved["tool_calls"],
            assistant_content=assistant_content,
            timestamp=creation["timestamp"],
        )

        first_leaf_id = creation["first_leaf_id"]
        if isinstance(first_leaf_id, str) and first_leaf_id and first_leaf_id != node_id:
            self._thread_service.fork_planning_thread(project_id, node_id, first_leaf_id)

        return {
            "user_message": user_message,
            "tool_calls": resolved["tool_calls"],
            "assistant_content": assistant_content,
            "timestamp": creation["timestamp"],
            "fallback_used": fallback_used,
            "created_child_ids": creation["created_child_ids"],
            "tool_event_published": tool_event_published,
        }

    def _retry_hidden_split_turns(
        self,
        *,
        project_id: str,
        node_id: str,
        mode: str,
        planning_thread_id: str,
        workspace_root: str | None,
        issues: list[str],
    ) -> dict[str, Any] | None:
        for attempt in range(_RETRY_LIMIT):
            response = self._codex_client.run_turn_streaming(
                self._hidden_retry_prompt(mode, attempt + 1, issues),
                thread_id=planning_thread_id,
                timeout_sec=self._split_timeout,
                cwd=workspace_root,
            )
            resolved = self._resolve_tool_payload(mode, response.get("tool_calls", []))
            if resolved is not None:
                resolved["assistant_content"] = str(response.get("stdout", ""))
                return resolved
            issues = self._tool_payload_issues(mode, response.get("tool_calls", []))
            logger.warning(
                "emit_render_data validation failed, retrying project=%s node=%s attempt=%s issues=%s",
                project_id,
                node_id,
                attempt + 1,
                "; ".join(issues) if issues else "unknown",
            )
        return None

    def _resolve_tool_payload(
        self,
        mode: str,
        tool_calls: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(tool_calls, list):
            return None
        for raw_tool_call in tool_calls:
            if not isinstance(raw_tool_call, dict):
                continue
            if str(raw_tool_call.get("tool_name") or "") != "emit_render_data":
                continue
            arguments = raw_tool_call.get("arguments")
            if not isinstance(arguments, dict):
                continue
            if str(arguments.get("kind") or "") != "split_result":
                continue
            payload = arguments.get("payload")
            if not isinstance(payload, dict) or not validate_legacy_split_payload(mode, payload):
                continue
            return {
                "payload": payload,
                "tool_calls": [self._render_tool_call(payload)],
            }
        return None

    def _tool_payload_issues(
        self,
        mode: str,
        tool_calls: Any,
    ) -> list[str]:
        if not isinstance(tool_calls, list) or not tool_calls:
            return ["No tool calls were captured for this turn."]

        emit_render_calls = [
            item
            for item in tool_calls
            if isinstance(item, dict) and str(item.get("tool_name") or "") == "emit_render_data"
        ]
        if not emit_render_calls:
            return ["No emit_render_data tool call was captured."]

        issues: list[str] = []
        for index, raw_tool_call in enumerate(emit_render_calls, start=1):
            arguments = raw_tool_call.get("arguments")
            if not isinstance(arguments, dict):
                issues.append(f"emit_render_data call {index} arguments must be an object")
                continue
            kind = str(arguments.get("kind") or "")
            if kind != "split_result":
                issues.append(f"emit_render_data call {index} kind must be 'split_result'")
                continue
            payload = arguments.get("payload")
            if not isinstance(payload, dict):
                issues.append(f"emit_render_data call {index} payload must be an object")
                continue
            payload_issues = legacy_split_payload_issues(mode, payload)
            if payload_issues:
                issues.extend(payload_issues)

        return issues or ["emit_render_data was captured but the payload was still invalid."]

    def _apply_split_payload(
        self,
        *,
        project_id: str,
        node_id: str,
        mode: str,
        confirm_replace: bool,
        payload: dict[str, Any],
        source: str,
        task_context: dict[str, Any],
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            parent = node_by_id.get(node_id)
            if parent is None:
                raise NodeNotFound(node_id)

            active_children = self._validate_split_eligibility(parent, node_by_id, confirm_replace)
            replaced_child_ids = self._supersede_active_children(active_children, node_by_id)
            inherited_locked = parent.get("status") == "locked" or self._tree_service.has_locked_ancestor(
                parent, node_by_id
            )
            now = iso_now()
            created_child_ids: list[str] = []

            try:
                if mode == "walking_skeleton":
                    first_leaf_id = self._create_walking_skeleton_children(
                        snapshot,
                        parent,
                        node_by_id,
                        payload,
                        inherited_locked,
                        now,
                        created_child_ids,
                    )
                else:
                    first_leaf_id = self._create_slice_children(
                        snapshot,
                        parent,
                        node_by_id,
                        payload,
                        inherited_locked,
                        now,
                        created_child_ids,
                    )

                if parent.get("status") in {"ready", "in_progress"}:
                    parent["status"] = "draft"
                parent["planning_mode"] = mode
                parent["split_metadata"] = {
                    "mode": mode,
                    "source": source,
                    "warnings": _dedupe_warnings(
                        [
                            "parent_chain_truncated" if task_context.get("parent_chain_truncated") else None,
                            "fallback_used" if source == "fallback" else None,
                        ]
                    ),
                    "created_child_ids": created_child_ids,
                    "replaced_child_ids": replaced_child_ids,
                    "created_at": now,
                    "revision": _next_revision(parent.get("split_metadata")),
                }
                snapshot["tree_state"]["active_node_id"] = first_leaf_id
                self._persist_snapshot(project_id, snapshot)
                return {
                    "created_child_ids": created_child_ids,
                    "first_leaf_id": first_leaf_id,
                    "timestamp": now,
                }
            except Exception:
                for child_id in reversed(created_child_ids):
                    if not self._snapshot_references_node(project_id, child_id):
                        self._storage.node_store.delete_node_files(project_id, child_id)
                raise

    def _validate_split_eligibility(
        self,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        confirm_replace: bool,
    ) -> list[str]:
        if self._is_superseded(node):
            raise SplitNotAllowed("Cannot split a superseded node.")
        if node.get("status") == "done":
            raise SplitNotAllowed("Cannot split a done node.")

        active_children = self._tree_service.active_child_ids(node, node_by_id)
        if not active_children:
            return []

        if not confirm_replace:
            raise SplitNotAllowed("Re-split requires confirmation because existing children will be replaced.")

        subtree_statuses = self._collect_active_subtree_statuses(active_children, node_by_id)
        if any(status in {"in_progress", "done"} for status in subtree_statuses):
            raise SplitNotAllowed("Cannot re-split: descendants are already in progress or done.")
        return active_children

    def _collect_active_subtree_statuses(
        self,
        root_ids: list[str],
        node_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        statuses: list[str] = []
        stack = list(reversed(root_ids))
        visited: set[str] = set()
        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            node = node_by_id.get(current_id)
            if node is None or self._is_superseded(node):
                continue
            statuses.append(str(node.get("status", "")))
            stack.extend(reversed(self._tree_service.active_child_ids(node, node_by_id)))
        return statuses

    def _supersede_active_children(
        self,
        active_child_ids: list[str],
        node_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        replaced_child_ids: list[str] = []
        for child_id in active_child_ids:
            child = node_by_id.get(child_id)
            if child is None or self._is_superseded(child):
                continue
            child["node_kind"] = "superseded"
            replaced_child_ids.append(child_id)
        return replaced_child_ids

    def _create_walking_skeleton_children(
        self,
        snapshot: dict[str, Any],
        parent: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        generation: dict[str, Any],
        inherited_locked: bool,
        now: str,
        created_child_ids: list[str],
    ) -> str:
        first_leaf_id: str | None = None
        parent_hnum = str(parent.get("hierarchical_number") or "1")
        for epic_index, epic in enumerate(generation.get("epics", []), start=1):
            epic_id = uuid4().hex
            epic_hnum = f"{parent_hnum}.{epic_index}"
            epic_title = str(epic.get("title") or f"Epic {epic_index}")
            epic_description = str(epic.get("prompt") or "")
            epic_node = self._make_node(
                node_id=epic_id,
                parent_id=parent["node_id"],
                status="locked" if inherited_locked or epic_index != 1 else "draft",
                depth=int(parent.get("depth", 0) or 0) + 1,
                display_order=epic_index - 1,
                hierarchical_number=epic_hnum,
                planning_thread_forked_from_node=str(parent["node_id"]),
                now=now,
            )
            parent.setdefault("child_ids", []).append(epic_id)
            self._store_new_node(
                project_id=str(snapshot.get("project", {}).get("id") or ""),
                snapshot=snapshot,
                node_by_id=node_by_id,
                node=epic_node,
                task_title=epic_title,
                task_purpose=epic_description,
                state={
                    "planning_thread_forked_from_node": str(parent["node_id"]),
                },
            )
            created_child_ids.append(epic_id)

            for phase_index, phase in enumerate(epic.get("phases", [])):
                phase_key = _PHASE_KEYS[phase_index]
                phase_id = uuid4().hex
                epic_node.setdefault("child_ids", []).append(phase_id)
                phase_title = f"{phase_key}: {_truncate_for_title(str(phase.get('prompt') or ''))}"
                phase_description = str(phase.get("definition_of_done") or "")
                phase_node = self._make_node(
                    node_id=phase_id,
                    parent_id=epic_id,
                    status=(
                        "locked"
                        if inherited_locked or not (epic_index == 1 and phase_index == 0)
                        else "ready"
                    ),
                    depth=int(epic_node.get("depth", 0) or 0) + 1,
                    display_order=phase_index,
                    hierarchical_number=f"{epic_hnum}.{phase_key}",
                    planning_thread_forked_from_node=str(parent["node_id"]),
                    now=now,
                )
                self._store_new_node(
                    project_id=str(snapshot.get("project", {}).get("id") or ""),
                    snapshot=snapshot,
                    node_by_id=node_by_id,
                    node=phase_node,
                    task_title=phase_title,
                    task_purpose=phase_description,
                    state={
                        "planning_thread_forked_from_node": str(parent["node_id"]),
                    },
                )
                created_child_ids.append(phase_id)
                if first_leaf_id is None:
                    first_leaf_id = phase_id

        if first_leaf_id is None:
            raise SplitNotAllowed("Walking skeleton split did not produce any phases.")
        return first_leaf_id

    def _create_slice_children(
        self,
        snapshot: dict[str, Any],
        parent: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        generation: dict[str, Any],
        inherited_locked: bool,
        now: str,
        created_child_ids: list[str],
    ) -> str:
        first_leaf_id: str | None = None
        parent_hnum = str(parent.get("hierarchical_number") or "1")
        for index, subtask in enumerate(generation.get("subtasks", []), start=1):
            child_id = uuid4().hex
            prompt = str(subtask.get("prompt") or "")
            child_title = _truncate_for_title(prompt)
            child_description = _build_slice_description(subtask)
            child_node = self._make_node(
                node_id=child_id,
                parent_id=parent["node_id"],
                status="locked" if inherited_locked or index != 1 else "ready",
                depth=int(parent.get("depth", 0) or 0) + 1,
                display_order=index - 1,
                hierarchical_number=f"{parent_hnum}.{index}",
                planning_thread_forked_from_node=str(parent["node_id"]),
                now=now,
            )
            parent.setdefault("child_ids", []).append(child_id)
            self._store_new_node(
                project_id=str(snapshot.get("project", {}).get("id") or ""),
                snapshot=snapshot,
                node_by_id=node_by_id,
                node=child_node,
                task_title=child_title,
                task_purpose=child_description,
                state={
                    "planning_thread_forked_from_node": str(parent["node_id"]),
                },
            )
            created_child_ids.append(child_id)
            if first_leaf_id is None:
                first_leaf_id = child_id

        if first_leaf_id is None:
            raise SplitNotAllowed("Slice split did not produce any subtasks.")
        return first_leaf_id

    def _make_node(
        self,
        *,
        node_id: str,
        parent_id: str,
        status: str,
        depth: int,
        display_order: int,
        hierarchical_number: str,
        planning_thread_forked_from_node: str | None,
        now: str,
    ) -> dict[str, Any]:
        return {
            "node_id": node_id,
            "parent_id": parent_id,
            "child_ids": [],
            "status": status,
            "phase": "planning",
            "node_kind": "original",
            "planning_mode": None,
            "depth": depth,
            "display_order": display_order,
            "hierarchical_number": hierarchical_number,
            "split_metadata": None,
            "chat_session_id": None,
            "planning_thread_id": None,
            "execution_thread_id": None,
            "planning_thread_forked_from_node": planning_thread_forked_from_node or None,
            "planning_thread_bootstrapped_at": None,
            "created_at": now,
        }

    def _store_new_node(
        self,
        *,
        project_id: str,
        snapshot: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        node: dict[str, Any],
        task_title: str,
        task_purpose: str,
        state: dict[str, Any] | None = None,
    ) -> None:
        node_id = str(node.get("node_id") or "")
        snapshot["tree_state"]["node_index"][node_id] = node
        node_by_id[node_id] = node
        try:
            self._storage.node_store.create_node_files(
                project_id,
                node_id,
                task={
                    "title": task_title,
                    "purpose": task_purpose,
                    "responsibility": "",
                },
                state=state,
            )
        except Exception:
            self._storage.node_store.delete_node_files(project_id, node_id)
            raise

    def _is_superseded(self, node: dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))

    def _render_tool_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "tool_name": "emit_render_data",
            "arguments": {
                "kind": "split_result",
                "payload": payload,
            },
        }

    def _planning_tool_call_event(
        self,
        node_id: str,
        turn_id: str,
        tool_call: dict[str, Any],
    ) -> dict[str, Any]:
        arguments = tool_call.get("arguments", {})
        return {
            "type": "planning_tool_call",
            "node_id": node_id,
            "turn_id": turn_id,
            "tool_name": tool_call.get("tool_name"),
            "kind": arguments.get("kind") if isinstance(arguments, dict) else None,
            "payload": arguments.get("payload") if isinstance(arguments, dict) else None,
        }

    def _hidden_retry_prompt(self, mode: str, attempt: int, issues: list[str]) -> str:
        return (
            f"{build_legacy_hidden_retry_feedback(mode, issues)}\n\n"
            f"This is hidden retry attempt {attempt}. "
            "Call emit_render_data(kind='split_result', payload=...) with a corrected payload before writing your summary."
        )

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_workspace_root")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _persist_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        now = iso_now()
        snapshot["updated_at"] = now
        snapshot.setdefault("project", {})["updated_at"] = now
        self._storage.project_store.save_snapshot(project_id, snapshot)
        self._storage.project_store.touch_meta(project_id, now)
        return snapshot

    def _snapshot_references_node(self, project_id: str, node_id: str) -> bool:
        tree = load_json(self._storage.project_store.tree_path(project_id))
        if not isinstance(tree, dict):
            return False
        return node_id in self._tree_service.node_index(tree)

    def _deterministic_fallback(
        self,
        mode: str,
        task_context: dict[str, Any],
    ) -> dict[str, Any]:
        current_prompt = str(task_context.get("current_node_prompt", "")).strip()
        title = current_prompt.split(":", 1)[0].strip() or "Task"
        if mode == "walking_skeleton":
            return {
                "epics": [
                    {
                        "title": "Core Implementation",
                        "prompt": f"Core implementation of {title}",
                        "phases": [
                            {"prompt": "Scaffold and setup", "definition_of_done": "Project structure ready"},
                            {"prompt": "Core logic implementation", "definition_of_done": "Main functionality working"},
                            {"prompt": "Integration and testing", "definition_of_done": "Components integrated and tested"},
                        ],
                    },
                    {
                        "title": "Polish and Documentation",
                        "prompt": f"Polish and documentation for {title}",
                        "phases": [
                            {"prompt": "Refinement and edge cases", "definition_of_done": "Edge cases handled"},
                            {"prompt": "Documentation", "definition_of_done": "Documentation complete"},
                            {"prompt": "Final review", "definition_of_done": "Ready for release"},
                        ],
                    },
                ]
            }
        return {
            "subtasks": [
                {"order": 1, "prompt": f"Setup and foundation for {title}", "risk_reason": "", "what_unblocks": ""},
                {"order": 2, "prompt": f"Core implementation of {title}", "risk_reason": "", "what_unblocks": ""},
                {"order": 3, "prompt": f"Testing and integration for {title}", "risk_reason": "", "what_unblocks": ""},
            ]
        }

    def _mark_live_turn(self, project_id: str, node_id: str) -> None:
        with self._live_turns_lock:
            self._live_turns.add((project_id, node_id))

    def _clear_live_turn(self, project_id: str, node_id: str) -> None:
        with self._live_turns_lock:
            self._live_turns.discard((project_id, node_id))

    def _is_live_turn(self, project_id: str, node_id: str) -> bool:
        with self._live_turns_lock:
            return (project_id, node_id) in self._live_turns


def _truncate_for_title(value: str, limit: int = 80) -> str:
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return "Untitled"
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _build_slice_description(subtask: dict[str, Any]) -> str:
    parts = [str(subtask.get("prompt") or "").strip()]
    risk_reason = str(subtask.get("risk_reason") or "").strip()
    what_unblocks = str(subtask.get("what_unblocks") or "").strip()
    if risk_reason:
        parts.append(f"Risk: {risk_reason}")
    if what_unblocks:
        parts.append(f"Unblocks: {what_unblocks}")
    return "\n\n".join(part for part in parts if part)


def _next_revision(split_metadata: Any) -> int:
    if isinstance(split_metadata, dict):
        revision = split_metadata.get("revision")
        if isinstance(revision, int) and revision >= 1:
            return revision + 1
    return 1


def _dedupe_warnings(warnings: list[str | None]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for warning in warnings:
        if not warning or warning in seen:
            continue
        seen.add(warning)
        results.append(warning)
    return results
