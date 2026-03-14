from __future__ import annotations

import copy
import logging
import time
from typing import Any

from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.split_prompt_builder import build_planning_base_instructions, planning_render_tool
from backend.errors.app_errors import NodeNotFound, NodeUpdateNotAllowed
from backend.services.node_task_fields import enrich_nodes_with_task_fields
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)
PLANNING_STALE_TURN_ERROR = "This split was interrupted because the server restarted before it completed."

_BOOTSTRAP_PROMPTS = {
    "root_init": "Bootstrap this planning thread for future inheritance. Reply with a short acknowledgement.",
    "activation": "Bootstrap this planning thread after activation so it can be used as a future fork source. Reply with a short acknowledgement.",
    "lineage_recreate": "Bootstrap this recreated planning thread with the inherited planning lineage summary. Reply with a short acknowledgement.",
}


class ThreadService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client

    def initialize_root_planning_thread(self, project_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            root_id = str(snapshot.get("tree_state", {}).get("root_node_id") or "")
            root = node_by_id.get(root_id)
            if root is None:
                raise NodeNotFound(root_id)
            thread_id = root.get("planning_thread_id")
            if isinstance(thread_id, str) and thread_id.strip():
                return snapshot
            workspace_root = self._workspace_root_from_snapshot(snapshot)

        response = self._codex_client.start_planning_thread(
            base_instructions=build_planning_base_instructions(),
            dynamic_tools=[planning_render_tool()],
            cwd=workspace_root,
        )
        thread_id = str(response.get("thread_id") or "").strip()
        if not thread_id:
            raise CodexTransportError("Planning thread start did not return a thread id", "rpc_error")

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            root = node_by_id.get(root_id)
            if root is None:
                raise NodeNotFound(root_id)
            self._sync_node_state_cache(
                project_id,
                root_id,
                root,
                planning_thread_id=thread_id,
                planning_thread_forked_from_node=None,
                planning_thread_bootstrapped_at=None,
            )
            self._persist_snapshot(project_id, snapshot)
            self._storage.thread_store.set_planning_status(
                project_id,
                root_id,
                thread_id=thread_id,
                forked_from_node=None,
                status="idle",
                active_turn_id=None,
            )

        self.bootstrap_planning_thread_hidden(project_id, root_id, reason="root_init")

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            return snapshot

    def ensure_planning_thread(
        self,
        project_id: str,
        node_id: str,
        *,
        source_node_id: str | None = None,
    ) -> str:
        existing_thread_id: str | None = None
        source_thread_id: str | None = None
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            existing = node.get("planning_thread_id")
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if isinstance(existing, str) and existing.strip():
                existing_thread_id = existing
            if source_node_id:
                source_node = node_by_id.get(source_node_id)
                if source_node is not None:
                    raw_source_thread_id = source_node.get("planning_thread_id")
                    if isinstance(raw_source_thread_id, str) and raw_source_thread_id.strip():
                        source_thread_id = raw_source_thread_id

        if isinstance(existing_thread_id, str) and existing_thread_id.strip():
            if self._thread_is_available(existing_thread_id, workspace_root):
                return existing_thread_id
            logger.warning(
                "Planning thread %s for node %s in project %s is unavailable; recreating",
                existing_thread_id,
                node_id,
                project_id,
            )

        if source_thread_id:
            try:
                thread_id = self._fork_planning_thread_with_retry(
                    source_thread_id,
                    workspace_root,
                )
            except CodexTransportError as exc:
                if not self._is_missing_rollout_error(exc):
                    raise
                logger.warning(
                    "Source planning thread %s for node %s is unavailable; starting a fresh planning thread",
                    source_thread_id,
                    node_id,
                )
                thread_id = self._start_planning_thread(workspace_root)
        else:
            thread_id = self._start_planning_thread(workspace_root)

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            self._sync_node_state_cache(
                project_id,
                node_id,
                node,
                planning_thread_id=thread_id,
                planning_thread_forked_from_node=source_node_id,
                planning_thread_bootstrapped_at=node.get("planning_thread_bootstrapped_at"),
            )
            self._persist_snapshot(project_id, snapshot)
            self._storage.thread_store.set_planning_status(
                project_id,
                node_id,
                thread_id=thread_id,
                forked_from_node=source_node_id,
                status="idle",
                active_turn_id=None,
            )
        return thread_id

    def fork_planning_thread(self, project_id: str, source_node_id: str, target_node_id: str) -> str:
        thread_id = self.ensure_planning_thread(
            project_id,
            target_node_id,
            source_node_id=source_node_id,
        )
        self.materialize_inherited_planning_history(project_id, target_node_id)
        self.bootstrap_planning_thread_hidden(project_id, target_node_id, reason="activation")
        return thread_id

    def bootstrap_planning_thread_hidden(
        self,
        project_id: str,
        node_id: str,
        *,
        reason: str,
        lineage_summary: str | None = None,
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            planning_thread_id = str(node.get("planning_thread_id") or "").strip()
            if not planning_thread_id:
                raise CodexTransportError("Planning thread is required before bootstrap", "rpc_error")
            workspace_root = self._workspace_root_from_snapshot(snapshot)

        prompt = _BOOTSTRAP_PROMPTS.get(reason, _BOOTSTRAP_PROMPTS["activation"])
        if lineage_summary:
            prompt = f"{prompt}\n\nInherited planning lineage:\n{lineage_summary}"

        self._codex_client.run_turn_streaming(
            prompt,
            thread_id=planning_thread_id,
            timeout_sec=30,
            cwd=workspace_root,
        )

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            bootstrapped_at = iso_now()
            self._sync_node_state_cache(
                project_id,
                node_id,
                node,
                planning_thread_bootstrapped_at=bootstrapped_at,
            )
            self._persist_snapshot(project_id, snapshot)
            self._storage.thread_store.set_planning_status(
                project_id,
                node_id,
                status="idle",
                active_turn_id=None,
            )

    def create_execution_thread(
        self,
        project_id: str,
        node_id: str,
        *,
        force_recreate: bool = False,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            state = self._storage.node_store.load_state(project_id, node_id)
            current_phase = str(state.get("phase") or node.get("phase") or "planning")
            if current_phase not in {"ready_for_execution", "executing"}:
                raise NodeUpdateNotAllowed(
                    f"Cannot create execution thread in phase '{current_phase}'. "
                    "Node must be in 'ready_for_execution' or 'executing' phase."
                )
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            existing_session = {} if force_recreate else self._load_existing_execution_session(project_id, node_id)
            existing = node.get("execution_thread_id")
            if not isinstance(existing, str) or not existing.strip():
                candidate = existing_session.get("thread_id")
                if isinstance(candidate, str) and candidate.strip():
                    existing = candidate.strip()

        if (
            not force_recreate
            and isinstance(existing, str)
            and existing.strip()
            and self._thread_is_available(existing, workspace_root)
        ):
            session = self._merge_execution_session(
                project_id,
                node_id,
                existing,
                workspace_root,
                existing_session,
            )
            with self._storage.project_lock(project_id):
                snapshot = self._storage.project_store.load_snapshot(project_id)
                node_by_id = self._tree_service.node_index(snapshot)
                node = node_by_id.get(node_id)
                if node is None:
                    raise NodeNotFound(node_id)
                if node.get("execution_thread_id") != existing:
                    self._sync_node_state_cache(
                        project_id,
                        node_id,
                        node,
                        execution_thread_id=existing,
                    )
                    self._persist_snapshot(project_id, snapshot)
                self._storage.thread_store.write_execution_session(project_id, node_id, session)
                chat_state = self._storage.chat_store.read_chat_state(project_id)
                chat_state[node_id] = copy.deepcopy(session)
                self._storage.chat_store.write_chat_state(project_id, chat_state)
            return {"thread_id": existing, "session": copy.deepcopy(session)}

        if isinstance(existing, str) and existing.strip():
            logger.warning(
                "Execution thread %s for node %s in project %s is unavailable; recreating",
                existing,
                node_id,
                project_id,
            )

        planning_thread_id = self.ensure_planning_thread(project_id, node_id)

        try:
            response = self._codex_client.fork_thread(
                planning_thread_id,
                cwd=workspace_root,
                timeout_sec=30,
            )
        except CodexTransportError as exc:
            if not self._is_missing_rollout_error(exc):
                raise
            logger.warning(
                "Planning thread %s for node %s could not be forked; recreating the planning thread first",
                planning_thread_id,
                node_id,
            )
            planning_thread_id = self._recreate_planning_thread(project_id, node_id, workspace_root)
            response = self._codex_client.fork_thread(
                planning_thread_id,
                cwd=workspace_root,
                timeout_sec=30,
            )
        execution_thread_id = str(response.get("thread_id") or "").strip()
        if not execution_thread_id:
            raise CodexTransportError("Execution thread fork did not return a thread id", "rpc_error")

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            self._sync_node_state_cache(
                project_id,
                node_id,
                node,
                execution_thread_id=execution_thread_id,
            )
            self._persist_snapshot(project_id, snapshot)
            session = self._merge_execution_session(
                project_id,
                node_id,
                execution_thread_id,
                workspace_root,
                existing_session,
            )
            self._storage.thread_store.write_execution_session(project_id, node_id, session)
            chat_state = self._storage.chat_store.read_chat_state(project_id)
            chat_state[node_id] = copy.deepcopy(session)
            self._storage.chat_store.write_chat_state(project_id, chat_state)
            return {"thread_id": execution_thread_id, "session": copy.deepcopy(session)}

    def reconcile_interrupted_planning_turns(self) -> None:
        for project_id in self._storage.project_store.list_project_ids():
            try:
                recovered_nodes = 0
                appended_failures = 0
                with self._storage.project_lock(project_id):
                    snapshot = self._storage.project_store.load_snapshot(project_id)
                    node_by_id = self._tree_service.node_index(snapshot)
                    thread_state = self._storage.thread_store.read_thread_state(project_id)
                    did_change = False

                    for node_id, raw_node_state in thread_state.items():
                        if not isinstance(raw_node_state, dict):
                            continue
                        planning = raw_node_state.get("planning")
                        if not isinstance(planning, dict):
                            continue
                        if str(planning.get("status") or "").strip().lower() != "active":
                            continue

                        recovered_nodes += 1
                        did_change = True
                        active_turn_id = str(planning.get("active_turn_id") or "").strip()
                        planning["status"] = "idle"
                        planning["active_turn_id"] = None

                        if not active_turn_id or node_id not in node_by_id:
                            continue

                        turns = planning.get("turns")
                        if not isinstance(turns, list):
                            turns = []
                            planning["turns"] = turns
                        if self._has_terminal_planning_assistant_turn(turns, active_turn_id):
                            continue

                        turns.append(
                            self._build_planning_assistant_turn(
                                node_id=node_id,
                                turn_id=active_turn_id,
                                assistant_content=PLANNING_STALE_TURN_ERROR,
                                timestamp=iso_now(),
                            )
                        )
                        planning["event_seq"] = int(planning.get("event_seq", 0) or 0) + 1
                        appended_failures += 1

                    if did_change:
                        self._storage.thread_store.write_thread_state(project_id, thread_state)

                if recovered_nodes:
                    logger.info(
                        "Recovered interrupted planning turns for project %s (nodes=%s, failure_turns=%s)",
                        project_id,
                        recovered_nodes,
                        appended_failures,
                    )
            except Exception:
                logger.exception("Failed to reconcile interrupted planning turns for project %s", project_id)

    def append_visible_planning_turn(
        self,
        project_id: str,
        node_id: str,
        *,
        turn_id: str,
        user_content: str,
        tool_calls: list[dict[str, Any]],
        assistant_content: str,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        turns = self._build_visible_planning_turns(
            node_id=node_id,
            turn_id=turn_id,
            user_content=user_content,
            tool_calls=tool_calls,
            assistant_content=assistant_content,
            timestamp=timestamp,
        )
        for entry in turns:
            self._storage.thread_store.append_planning_turn(project_id, node_id, entry)
        return turns

    def materialize_inherited_planning_history(self, project_id: str, node_id: str) -> list[dict[str, Any]]:
        return self._materialize_planning_history(project_id, node_id, visited=set())

    def set_planning_status(
        self,
        project_id: str,
        node_id: str,
        *,
        status: str | None,
        active_turn_id: str | None,
    ) -> dict[str, Any]:
        return self._storage.thread_store.set_planning_status(
            project_id,
            node_id,
            status=status,
            active_turn_id=active_turn_id,
        )

    def get_internal_thread_ids(self, project_id: str, node_id: str) -> dict[str, str | None]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            return {
                "planning_thread_id": node.get("planning_thread_id"),
                "execution_thread_id": node.get("execution_thread_id"),
            }

    def _fork_planning_thread_with_retry(
        self,
        source_thread_id: str,
        workspace_root: str | None,
        *,
        attempts: int = 3,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._codex_client.fork_thread(
                    source_thread_id,
                    cwd=workspace_root,
                    base_instructions=build_planning_base_instructions(),
                    dynamic_tools=[planning_render_tool()],
                    timeout_sec=30,
                )
                thread_id = str(response.get("thread_id") or "").strip()
                if thread_id:
                    return thread_id
                raise CodexTransportError("Planning thread fork returned no thread id", "rpc_error")
            except Exception as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(1 + attempt)
                    continue
                raise
        if last_error:
            raise last_error
        raise CodexTransportError("Planning thread fork failed", "rpc_error")

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_workspace_root")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None

    def _default_execution_session(
        self,
        project_id: str,
        node_id: str,
        thread_id: str,
        workspace_root: str | None,
    ) -> dict[str, Any]:
        cwd = workspace_root or ""
        writable_roots = [workspace_root] if workspace_root else []
        return {
            "project_id": project_id,
            "node_id": node_id,
            "thread_id": thread_id,
            "active_turn_id": None,
            "event_seq": 0,
            "status": "idle",
            "mode": "idle",
            "plan_message_start_index": 0,
            "messages": [],
            "config": {
                "access_mode": "project_write",
                "cwd": cwd,
                "writable_roots": writable_roots,
                "timeout_sec": 120,
            },
            "forked_from_planning": True,
        }

    def _build_visible_planning_turns(
        self,
        *,
        node_id: str,
        turn_id: str,
        user_content: str,
        tool_calls: list[dict[str, Any]],
        assistant_content: str,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        turns = []
        turns.append(
            {
                "turn_id": turn_id,
                "role": "user",
                "content": user_content,
                "timestamp": timestamp,
                "is_inherited": False,
                "origin_node_id": node_id,
            }
        )
        for tool_call in tool_calls:
            arguments = tool_call.get("arguments", {})
            turns.append(
                {
                    "turn_id": turn_id,
                    "role": "tool_call",
                    "tool_name": tool_call.get("tool_name"),
                    "arguments": copy.deepcopy(arguments) if isinstance(arguments, dict) else {},
                    "timestamp": timestamp,
                    "is_inherited": False,
                    "origin_node_id": node_id,
                }
            )
        turns.append(
            {
                "turn_id": turn_id,
                "role": "assistant",
                "content": assistant_content,
                "timestamp": timestamp,
                "is_inherited": False,
                "origin_node_id": node_id,
            }
        )
        return turns

    def _build_planning_assistant_turn(
        self,
        *,
        node_id: str,
        turn_id: str,
        assistant_content: str,
        timestamp: str,
    ) -> dict[str, Any]:
        return {
            "turn_id": turn_id,
            "role": "assistant",
            "content": assistant_content,
            "timestamp": timestamp,
            "is_inherited": False,
            "origin_node_id": node_id,
        }

    def _start_planning_thread(self, workspace_root: str | None) -> str:
        response = self._codex_client.start_planning_thread(
            base_instructions=build_planning_base_instructions(),
            dynamic_tools=[planning_render_tool()],
            cwd=workspace_root,
        )
        thread_id = str(response.get("thread_id") or "").strip()
        if not thread_id:
            raise CodexTransportError("Planning thread start did not return a thread id", "rpc_error")
        return thread_id

    def _recreate_planning_thread(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> str:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            enrich_nodes_with_task_fields(self._storage.node_store, project_id, node_by_id)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            lineage_summary = self._build_lineage_summary(node, node_by_id)

        thread_id = self._start_planning_thread(workspace_root)

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            self._sync_node_state_cache(
                project_id,
                node_id,
                node,
                planning_thread_id=thread_id,
                planning_thread_bootstrapped_at=None,
            )
            self._persist_snapshot(project_id, snapshot)
            self._storage.thread_store.set_planning_status(
                project_id,
                node_id,
                thread_id=thread_id,
                forked_from_node=node.get("planning_thread_forked_from_node"),
                status="idle",
                active_turn_id=None,
            )

        self.bootstrap_planning_thread_hidden(
            project_id,
            node_id,
            reason="lineage_recreate",
            lineage_summary=lineage_summary,
        )
        return thread_id

    def _build_lineage_summary(
        self,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> str:
        chain: list[str] = []
        parent_id = node.get("parent_id")
        visited: set[str] = set()
        while isinstance(parent_id, str) and parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = node_by_id.get(parent_id)
            if parent is None:
                break
            title = str(parent.get("title") or "").strip()
            if title:
                chain.append(title)
            parent_id = parent.get("parent_id")
        chain.reverse()

        lines = []
        if chain:
            lines.append(f"Parent chain: {' > '.join(chain)}")
        title = str(node.get("title") or "").strip()
        description = str(node.get("description") or "").strip()
        if title:
            lines.append(f"Current node: {title}")
        if description:
            lines.append(f"Description: {description}")
        return "\n".join(lines).strip()

    def _load_existing_execution_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        execution_session = self._storage.thread_store.get_execution_session(project_id, node_id)
        if self._has_execution_session_data(execution_session):
            return copy.deepcopy(execution_session)
        chat_state = self._storage.chat_store.read_chat_state(project_id)
        raw_chat_session = chat_state.get(node_id, {})
        if isinstance(raw_chat_session, dict):
            return copy.deepcopy(raw_chat_session)
        return {}

    def _has_execution_session_data(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        return any(payload.get(key) for key in ("thread_id", "active_turn_id", "messages", "config"))

    def _merge_execution_session(
        self,
        project_id: str,
        node_id: str,
        thread_id: str,
        workspace_root: str | None,
        existing_session: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base = self._default_execution_session(project_id, node_id, thread_id, workspace_root)
        if not isinstance(existing_session, dict):
            return base

        messages = existing_session.get("messages")
        if isinstance(messages, list):
            base["messages"] = copy.deepcopy(messages)

        config = existing_session.get("config")
        if isinstance(config, dict):
            base["config"] = copy.deepcopy(config)
            if workspace_root:
                base["config"]["cwd"] = config.get("cwd") or workspace_root
                writable_roots = config.get("writable_roots")
                if not isinstance(writable_roots, list) or not writable_roots:
                    base["config"]["writable_roots"] = [workspace_root]

        try:
            base["event_seq"] = max(0, int(existing_session.get("event_seq", 0)))
        except (TypeError, ValueError):
            base["event_seq"] = 0
        active_turn_id = existing_session.get("active_turn_id")
        base["active_turn_id"] = (
            active_turn_id if isinstance(active_turn_id, str) and active_turn_id.strip() else None
        )
        status = str(existing_session.get("status") or "").strip().lower()
        if status not in {"active", "idle"}:
            status = "active" if base["active_turn_id"] else "idle"
        base["status"] = status
        mode = str(existing_session.get("mode") or "").strip().lower()
        if mode in {"plan", "execute"}:
            base["mode"] = mode
        try:
            base["plan_message_start_index"] = max(
                0,
                int(existing_session.get("plan_message_start_index", 0) or 0),
            )
        except (TypeError, ValueError):
            base["plan_message_start_index"] = 0
        base["forked_from_planning"] = True
        base["thread_id"] = thread_id
        return base

    def _materialize_planning_history(
        self,
        project_id: str,
        node_id: str,
        *,
        visited: set[str],
    ) -> list[dict[str, Any]]:
        if node_id in visited:
            return []
        visited = set(visited)
        visited.add(node_id)

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            source_node_id = node.get("planning_thread_forked_from_node")
            planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
            current_turns = planning_state.get("turns", [])

        normalized_current = self._normalize_local_planning_turns(node_id, current_turns)
        if normalized_current:
            if normalized_current != current_turns:
                self._storage.thread_store.replace_planning_turns(project_id, node_id, normalized_current)
            return normalized_current

        if not isinstance(source_node_id, str) or not source_node_id.strip():
            return []

        source_turns = self._materialize_planning_history(
            project_id,
            source_node_id,
            visited=visited,
        )
        if not source_turns:
            return []

        inherited_turns = self._inherit_planning_turns(source_node_id, source_turns)
        self._storage.thread_store.replace_planning_turns(project_id, node_id, inherited_turns)
        return inherited_turns

    def _normalize_local_planning_turns(
        self,
        node_id: str,
        turns: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(turns, list):
            return []
        normalized: list[dict[str, Any]] = []
        for raw_turn in turns:
            if not isinstance(raw_turn, dict):
                continue
            turn = copy.deepcopy(raw_turn)
            origin_node_id = turn.get("origin_node_id")
            if not isinstance(origin_node_id, str) or not origin_node_id.strip():
                turn["origin_node_id"] = node_id
            is_inherited = turn.get("is_inherited")
            if not isinstance(is_inherited, bool):
                turn["is_inherited"] = False
            normalized.append(turn)
        return normalized

    def _has_terminal_planning_assistant_turn(
        self,
        turns: Any,
        turn_id: str,
    ) -> bool:
        if not isinstance(turns, list) or not turn_id:
            return False
        for raw_turn in turns:
            if not isinstance(raw_turn, dict):
                continue
            if str(raw_turn.get("turn_id") or "") != turn_id:
                continue
            if str(raw_turn.get("role") or "") != "assistant":
                continue
            content = raw_turn.get("content")
            if isinstance(content, str):
                return True
        return False

    def _inherit_planning_turns(
        self,
        source_node_id: str,
        source_turns: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        inherited_turns: list[dict[str, Any]] = []
        for raw_turn in source_turns:
            if not isinstance(raw_turn, dict):
                continue
            turn = copy.deepcopy(raw_turn)
            origin_node_id = turn.get("origin_node_id")
            if not isinstance(origin_node_id, str) or not origin_node_id.strip():
                turn["origin_node_id"] = source_node_id
            turn["is_inherited"] = True
            inherited_turns.append(turn)
        return inherited_turns

    def _thread_is_available(self, thread_id: str, workspace_root: str | None) -> bool:
        try:
            self._codex_client.resume_thread(
                thread_id,
                cwd=workspace_root,
                timeout_sec=15,
            )
            return True
        except CodexTransportError as exc:
            if self._is_missing_rollout_error(exc):
                return False
            raise

    def _is_missing_rollout_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message

    def _persist_snapshot(self, project_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        now = iso_now()
        snapshot["updated_at"] = now
        snapshot.setdefault("project", {})["updated_at"] = now
        self._storage.project_store.save_snapshot(project_id, snapshot)
        self._storage.project_store.touch_meta(project_id, now)
        return snapshot

    def _sync_node_state_cache(
        self,
        project_id: str,
        node_id: str,
        node: dict[str, Any],
        **updates: Any,
    ) -> None:
        state = self._storage.node_store.load_state(project_id, node_id)
        for key, value in updates.items():
            if key in {
                "planning_thread_id",
                "execution_thread_id",
                "planning_thread_forked_from_node",
                "planning_thread_bootstrapped_at",
                "chat_session_id",
            }:
                node[key] = value if value not in {"", None} else None
                state[key] = "" if value is None else value
        self._storage.node_store.save_state(project_id, node_id, state)
