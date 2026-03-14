from __future__ import annotations

import copy
import json
import logging
import threading
from typing import Any

from backend.ai.ask_prompt_builder import build_ask_base_instructions, ask_thread_render_tool
from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.errors.app_errors import (
    AskBlockedByPlanningActive,
    AskThreadReadOnly,
    AskTurnAlreadyActive,
    InvalidPacketTransition,
    MergeBlockedBySplit,
    MergePlanningThreadUnavailable,
    NodeNotFound,
    PacketMutationBlockedBySplit,
    PacketNotFound,
)
from backend.services.node_task_fields import load_task_prompt_fields
from backend.services.thread_service import ThreadService
from backend.storage.file_utils import iso_now, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import AskEventBroker

STALE_ASK_TURN_ERROR = "Ask session interrupted - the server restarted before this response completed."

logger = logging.getLogger(__name__)


class AskService:
    def __init__(
        self,
        storage: Storage,
        codex_client: CodexAppClient,
        event_broker: AskEventBroker,
        thread_service: ThreadService,
    ) -> None:
        self._storage = storage
        self._client = codex_client
        self._event_broker = event_broker
        self._thread_service = thread_service
        self._live_turns_lock = threading.Lock()
        self._live_turns: set[tuple[str, str, str]] = set()

    def get_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            self._load_node_context(project_id, node_id)
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            session, recovered = self._recover_stale_turn(session)
            if recovered or raw_session != self._storage_session_payload(session):
                self._write_ask_session_state(project_id, node_id, session)
            return {"session": self._public_session(session)}

    def create_message(self, project_id: str, node_id: str, content: Any) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise ValueError("content is required")

        with self._storage.project_lock(project_id):
            self._assert_node_is_writable(project_id, node_id)

        ask_thread_id = self._ensure_ask_thread(project_id, node_id)

        with self._storage.project_lock(project_id):
            snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
            self._assert_node_is_writable(project_id, node_id, snapshot=snapshot, node=node)
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            if session["active_turn_id"]:
                raise AskTurnAlreadyActive()

            created_at = iso_now()
            turn_id = new_id("askturn")
            user_message = {
                "message_id": new_id("msg"),
                "role": "user",
                "content": text,
                "status": "completed",
                "created_at": created_at,
                "updated_at": created_at,
                "error": None,
            }
            assistant_message = {
                "message_id": new_id("msg"),
                "role": "assistant",
                "content": "",
                "status": "pending",
                "created_at": created_at,
                "updated_at": created_at,
                "error": None,
            }
            session["thread_id"] = ask_thread_id
            session["created_at"] = str(session.get("created_at") or created_at)
            session["messages"].extend([user_message, assistant_message])
            session["active_turn_id"] = turn_id
            session["status"] = "active"
            prompt = self._build_ask_prompt(
                project_id=project_id,
                snapshot=snapshot,
                node=node,
                workspace_root=workspace_root,
                user_message=text,
            )
            runtime_config = self._runtime_config(workspace_root)
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_message_created",
                    "active_turn_id": turn_id,
                    "user_message": copy.deepcopy(user_message),
                    "assistant_message": copy.deepcopy(assistant_message),
                },
            )
            self._mark_live_turn(project_id, node_id, turn_id)

        self._event_broker.publish(project_id, node_id, event)
        self._start_background_turn(
            project_id=project_id,
            node_id=node_id,
            turn_id=turn_id,
            user_message_id=user_message["message_id"],
            assistant_message_id=assistant_message["message_id"],
            prompt=prompt,
            thread_id=ask_thread_id,
            runtime_config=runtime_config,
        )
        return {
            "status": "accepted",
            "user_message_id": user_message["message_id"],
            "assistant_message_id": assistant_message["message_id"],
        }

    def reset_session(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            _, node, _ = self._load_node_context(project_id, node_id)
            self._assert_node_is_read_only(node)
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            if session["active_turn_id"]:
                raise AskTurnAlreadyActive()
            session["thread_id"] = None
            session["forked_from_planning_thread_id"] = None
            session["created_at"] = None
            session["messages"] = []
            session["active_turn_id"] = None
            session["status"] = None
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_session_reset",
                    "session": self._public_session(session),
                },
            )
            response = {"session": self._public_session(session)}

        self._event_broker.publish(project_id, node_id, event)
        return response

    def list_packets(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            self._load_node_context(project_id, node_id)
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
        return {"packets": copy.deepcopy(session.get("delta_context_packets", []))}

    def create_packet(
        self,
        project_id: str,
        node_id: str,
        summary: str,
        context_text: str,
        source_message_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_summary = str(summary or "").strip()
        normalized_context = str(context_text or "").strip()
        if not normalized_summary:
            raise ValueError("summary is required")
        if not normalized_context:
            raise ValueError("context_text is required")

        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_node_context(project_id, node_id)
            self._assert_node_is_writable(project_id, node_id, snapshot=snapshot, node=node)
            self._reject_packet_creation_after_split(
                snapshot=snapshot,
                node=node,
                node_id=node_id,
                action="create",
                raise_on_block=True,
            )
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            packet = self._build_packet(
                node_id=node_id,
                summary=normalized_summary,
                context_text=normalized_context,
                source_message_ids=[
                    message_id.strip()
                    for message_id in (source_message_ids or [])
                    if isinstance(message_id, str) and message_id.strip()
                ],
                suggested_by="user",
            )
            session["delta_context_packets"].append(copy.deepcopy(packet))
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_delta_context_suggested",
                    "packet": copy.deepcopy(packet),
                },
            )

        self._event_broker.publish(project_id, node_id, event)
        return {"packet": copy.deepcopy(packet)}

    def approve_packet(self, project_id: str, node_id: str, packet_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_node_context(project_id, node_id)
            self._assert_node_is_writable(project_id, node_id, snapshot=snapshot, node=node)
            if self._node_has_active_children(snapshot, node):
                raise PacketMutationBlockedBySplit("approve", node_id)
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            packet = self._find_packet(session, packet_id)
            if packet is None:
                raise PacketNotFound(packet_id)
            from_status = str(packet.get("status") or "")
            if from_status != "pending":
                raise InvalidPacketTransition(from_status, "approved")
            packet["status"] = "approved"
            packet["status_reason"] = None
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_packet_status_changed",
                    "packet": copy.deepcopy(packet),
                },
            )

        self._event_broker.publish(project_id, node_id, event)
        return {"packet": copy.deepcopy(packet)}

    def reject_packet(self, project_id: str, node_id: str, packet_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_node_context(project_id, node_id)
            self._assert_node_is_writable(project_id, node_id, snapshot=snapshot, node=node)
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            packet = self._find_packet(session, packet_id)
            if packet is None:
                raise PacketNotFound(packet_id)
            from_status = str(packet.get("status") or "")
            if from_status not in {"pending", "approved"}:
                raise InvalidPacketTransition(from_status, "rejected")
            packet["status"] = "rejected"
            packet["status_reason"] = "Rejected by user"
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_packet_status_changed",
                    "packet": copy.deepcopy(packet),
                },
            )

        self._event_broker.publish(project_id, node_id, event)
        return {"packet": copy.deepcopy(packet)}

    def merge_packet(self, project_id: str, node_id: str, packet_id: str) -> dict[str, Any]:
        reserved_turn_id: str | None = None
        event: dict[str, Any] | None = None
        response_packet: dict[str, Any] | None = None
        commit_succeeded = False
        packet_summary = ""
        packet_context_text = ""

        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_node_context(project_id, node_id)
            planning_thread_id = str(node.get("planning_thread_id") or "").strip()

        if not planning_thread_id:
            self._thread_service.ensure_planning_thread(project_id, node_id)

        try:
            with self._storage.project_lock(project_id):
                snapshot, node, workspace_root = self._load_node_context(project_id, node_id)
                self._assert_merge_preconditions(project_id, node_id, snapshot, node)
                raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
                session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
                packet = self._find_packet(session, packet_id)
                if packet is None:
                    raise PacketNotFound(packet_id)
                from_status = str(packet.get("status") or "")
                if from_status != "approved":
                    raise InvalidPacketTransition(from_status, "merged")
                planning_thread_id = str(node.get("planning_thread_id") or "").strip()
                if not planning_thread_id:
                    raise MergePlanningThreadUnavailable(node_id)

                reserved_turn_id = new_id("mergeturn")
                self._storage.thread_store.set_planning_status(
                    project_id,
                    node_id,
                    status="active",
                    active_turn_id=reserved_turn_id,
                )
                packet_summary = str(packet.get("summary") or "")
                packet_context_text = str(packet.get("context_text") or "")

            merge_prompt = (
                "The user approved a delta context packet from an ask-thread conversation. "
                "Integrate the following insight into your planning context for future decomposition. "
                "Reply with a brief acknowledgement.\n\n"
                f"Summary: {packet_summary}\n\n"
                f"Context:\n{packet_context_text}"
            )
            self._client.run_turn_streaming(
                merge_prompt,
                thread_id=planning_thread_id,
                timeout_sec=30,
                cwd=workspace_root,
            )

            with self._storage.project_lock(project_id):
                snapshot, node, _ = self._load_node_context(project_id, node_id)
                if self._node_has_active_children(snapshot, node):
                    raise MergeBlockedBySplit(node_id)
                if node.get("status") == "done" or self._is_superseded(node):
                    raise AskThreadReadOnly()

                planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
                if (
                    planning_state.get("status") != "active"
                    or str(planning_state.get("active_turn_id") or "") != reserved_turn_id
                ):
                    raise MergePlanningThreadUnavailable(node_id)

                raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
                session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
                packet = self._find_packet(session, packet_id)
                if packet is None:
                    raise PacketNotFound(packet_id)
                from_status = str(packet.get("status") or "")
                if from_status != "approved":
                    raise InvalidPacketTransition(from_status, "merged")

                now = iso_now()
                packet["status"] = "merged"
                packet["status_reason"] = None
                packet["merged_at"] = now
                packet["merged_planning_turn_id"] = reserved_turn_id
                self._advance_event_seq(session)
                event = {
                    "type": "ask_packet_status_changed",
                    "event_seq": session["event_seq"],
                    "packet": copy.deepcopy(packet),
                }
                planning_turn = {
                    "turn_id": reserved_turn_id,
                    "role": "context_merge",
                    "content": packet_context_text,
                    "summary": packet_summary,
                    "packet_id": packet_id,
                    "timestamp": now,
                    "is_inherited": False,
                    "origin_node_id": node_id,
                }
                self._storage.thread_store.write_ask_session_and_append_planning_turn(
                    project_id,
                    node_id,
                    ask_session=self._storage_session_payload(session),
                    planning_turn=planning_turn,
                    planning_status="idle",
                    planning_active_turn_id=None,
                )
                response_packet = copy.deepcopy(packet)
                commit_succeeded = True
        except CodexTransportError as exc:
            if reserved_turn_id is not None and not commit_succeeded:
                self._release_reserved_merge_turn(project_id, node_id, reserved_turn_id)
            if self._is_missing_rollout_error(exc):
                raise MergePlanningThreadUnavailable(node_id) from exc
            raise
        except Exception:
            if reserved_turn_id is not None and not commit_succeeded:
                self._release_reserved_merge_turn(project_id, node_id, reserved_turn_id)
            raise

        if event is None or response_packet is None:
            raise MergePlanningThreadUnavailable(node_id)
        self._event_broker.publish(project_id, node_id, event)
        return {"packet": response_packet}

    def reconcile_interrupted_ask_turns(self) -> None:
        for project_id in self._storage.project_store.list_project_ids():
            try:
                with self._storage.project_lock(project_id):
                    thread_state = self._storage.thread_store.read_thread_state(project_id)
                    did_change = False
                    for node_id, raw_node_state in thread_state.items():
                        if not isinstance(raw_node_state, dict):
                            continue
                        raw_ask_state = raw_node_state.get("ask")
                        if not isinstance(raw_ask_state, dict):
                            continue
                        session = self._normalize_ask_session(
                            project_id=project_id,
                            node_id=str(node_id),
                            ask_state=raw_ask_state,
                        )
                        session, recovered = self._recover_stale_turn(session)
                        payload = self._storage_session_payload(session)
                        if recovered or raw_ask_state != payload:
                            raw_node_state["ask"] = payload
                            did_change = True
                    if did_change:
                        self._storage.thread_store.write_thread_state(project_id, thread_state)
            except Exception:
                logger.exception("Failed to reconcile interrupted ask turns for project %s", project_id)

    def _ensure_ask_thread(self, project_id: str, node_id: str) -> str:
        with self._storage.project_lock(project_id):
            _, _, workspace_root = self._load_node_context(project_id, node_id)
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)

        existing_thread_id = session.get("thread_id")
        if isinstance(existing_thread_id, str) and existing_thread_id.strip():
            if self._thread_is_available(existing_thread_id, workspace_root):
                return existing_thread_id
            logger.warning(
                "Ask thread %s for node %s in project %s is unavailable; recreating",
                existing_thread_id,
                node_id,
                project_id,
            )

        planning_thread_id = self._thread_service.ensure_planning_thread(project_id, node_id)
        try:
            response = self._client.fork_thread(
                planning_thread_id,
                cwd=workspace_root,
                base_instructions=build_ask_base_instructions(),
                dynamic_tools=[ask_thread_render_tool()],
                timeout_sec=30,
            )
        except CodexTransportError as exc:
            if not self._is_missing_rollout_error(exc):
                raise
            logger.warning(
                "Planning thread %s for ask node %s is unavailable; recreating before ask fork",
                planning_thread_id,
                node_id,
            )
            planning_thread_id = self._thread_service.ensure_planning_thread(project_id, node_id)
            response = self._client.fork_thread(
                planning_thread_id,
                cwd=workspace_root,
                base_instructions=build_ask_base_instructions(),
                dynamic_tools=[ask_thread_render_tool()],
                timeout_sec=30,
            )

        ask_thread_id = str(response.get("thread_id") or "").strip()
        if not ask_thread_id:
            raise CodexTransportError("Ask thread fork did not return a thread id", "rpc_error")

        session["thread_id"] = ask_thread_id
        session["forked_from_planning_thread_id"] = planning_thread_id
        session["created_at"] = str(session.get("created_at") or iso_now())
        if session.get("status") not in {"active", "idle", None}:
            session["status"] = None
        with self._storage.project_lock(project_id):
            self._write_ask_session_state(project_id, node_id, session)
        return ask_thread_id

    def _thread_is_available(self, thread_id: str, workspace_root: str | None) -> bool:
        try:
            self._client.resume_thread(
                thread_id,
                cwd=workspace_root,
                timeout_sec=15,
                writable_roots=[],
            )
            return True
        except CodexTransportError as exc:
            if self._is_missing_rollout_error(exc):
                return False
            raise

    def _is_missing_rollout_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message

    def _load_node_context(
        self,
        project_id: str,
        node_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        node = self._node_from_snapshot(snapshot, node_id)
        if node is None:
            raise NodeNotFound(node_id)
        workspace_root = self._workspace_root_from_snapshot(snapshot)
        if not workspace_root:
            raise ValueError("project workspace_root is required for ask")
        return snapshot, node, workspace_root

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_workspace_root")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return None
        return workspace_root.strip()

    def _normalize_ask_session(
        self,
        *,
        project_id: str,
        node_id: str,
        ask_state: Any,
    ) -> dict[str, Any]:
        payload = ask_state if isinstance(ask_state, dict) else {}
        messages = [
            self._normalize_message(item)
            for item in payload.get("messages", [])
            if isinstance(item, dict)
        ]
        delta_context_packets = [
            copy.deepcopy(item)
            for item in payload.get("delta_context_packets", [])
            if isinstance(item, dict)
        ]
        thread_id = payload.get("thread_id")
        forked_from_planning_thread_id = payload.get("forked_from_planning_thread_id")
        active_turn_id = payload.get("active_turn_id")
        created_at = payload.get("created_at")
        event_seq = payload.get("event_seq", 0)
        try:
            normalized_event_seq = max(0, int(event_seq))
        except (TypeError, ValueError):
            normalized_event_seq = 0
        status_raw = payload.get("status")
        if status_raw is None:
            status = None if not active_turn_id else "active"
        else:
            status = str(status_raw).strip().lower()
            if status not in {"active", "idle"}:
                status = "active" if active_turn_id else None
        return {
            "project_id": project_id,
            "node_id": node_id,
            "thread_id": thread_id if isinstance(thread_id, str) and thread_id.strip() else None,
            "forked_from_planning_thread_id": (
                forked_from_planning_thread_id
                if isinstance(forked_from_planning_thread_id, str) and forked_from_planning_thread_id.strip()
                else None
            ),
            "created_at": str(created_at) if isinstance(created_at, str) and created_at.strip() else None,
            "active_turn_id": (
                active_turn_id if isinstance(active_turn_id, str) and active_turn_id.strip() else None
            ),
            "event_seq": normalized_event_seq,
            "status": status,
            "messages": messages,
            "delta_context_packets": delta_context_packets,
        }

    def _public_session(self, session: dict[str, Any]) -> dict[str, Any]:
        public_session = copy.deepcopy(session)
        public_session.pop("thread_id", None)
        public_session.pop("forked_from_planning_thread_id", None)
        public_session.pop("created_at", None)
        return public_session

    def _runtime_config(self, workspace_root: str) -> dict[str, Any]:
        return {
            "access_mode": "read_only",
            "cwd": workspace_root,
            "writable_roots": [],
            "timeout_sec": 120,
        }

    def _build_ask_prompt(
        self,
        *,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        workspace_root: str,
        user_message: str,
    ) -> str:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            project = {}
        fields = load_task_prompt_fields(
            self._storage.node_store,
            project_id,
            str(node.get("node_id") or ""),
        )
        hidden_context = {
            "project_name": str(project.get("name") or ""),
            "project_root_goal": str(project.get("root_goal") or ""),
            "workspace_root": workspace_root,
            "node_id": str(node.get("node_id") or ""),
            "node_title": fields["title"],
            "node_description": fields["description"],
            "node_hierarchical_number": str(node.get("hierarchical_number") or ""),
            "node_status": str(node.get("status") or ""),
            "node_planning_mode": node.get("planning_mode"),
        }
        return (
            "Hidden context:\n"
            f"{json.dumps(hidden_context, ensure_ascii=True, indent=2)}\n\n"
            "User message:\n"
            f"{user_message}"
        )

    def _start_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        user_message_id: str,
        assistant_message_id: str,
        prompt: str,
        thread_id: str,
        runtime_config: dict[str, Any],
    ) -> None:
        threading.Thread(
            target=self._run_background_turn,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "prompt": prompt,
                "thread_id": thread_id,
                "runtime_config": runtime_config,
            },
            daemon=True,
        ).start()

    def _run_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        user_message_id: str,
        assistant_message_id: str,
        prompt: str,
        thread_id: str,
        runtime_config: dict[str, Any],
    ) -> None:
        try:
            response = self._client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=int(runtime_config.get("timeout_sec", 120)),
                cwd=str(runtime_config.get("cwd") or ""),
                writable_roots=list(runtime_config.get("writable_roots", [])),
                on_delta=lambda delta: self._append_assistant_delta(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    delta=delta,
                ),
                on_tool_call=lambda tool_name, arguments: self._handle_tool_call(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                    tool_name=tool_name,
                    arguments=arguments,
                ),
            )
        except Exception as exc:
            self._mark_turn_failed(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                error_message=str(exc),
            )
        else:
            self._mark_turn_completed(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=str(response.get("stdout", "")),
                thread_id=response.get("thread_id"),
            )
        finally:
            self._clear_live_turn(project_id, node_id, turn_id)

    def _append_assistant_delta(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        delta: str,
    ) -> None:
        if not delta:
            return
        with self._storage.project_lock(project_id):
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return
            message["content"] = f"{message.get('content', '')}{delta}"
            message["status"] = "streaming"
            message["updated_at"] = iso_now()
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_assistant_delta",
                    "message_id": assistant_message_id,
                    "delta": delta,
                    "content": str(message["content"]),
                    "updated_at": str(message["updated_at"]),
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _mark_turn_completed(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        content: str,
        thread_id: Any,
    ) -> None:
        with self._storage.project_lock(project_id):
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return
            final_content = content or str(message.get("content", ""))
            message["content"] = final_content
            message["status"] = "completed"
            message["error"] = None
            message["updated_at"] = iso_now()
            session["active_turn_id"] = None
            session["status"] = "idle"
            if isinstance(thread_id, str) and thread_id.strip():
                session["thread_id"] = thread_id.strip()
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_assistant_completed",
                    "message_id": assistant_message_id,
                    "content": final_content,
                    "updated_at": str(message["updated_at"]),
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _mark_turn_failed(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        error_message: str,
    ) -> None:
        with self._storage.project_lock(project_id):
            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            if session.get("active_turn_id") != turn_id:
                return
            message = self._find_message(session, assistant_message_id)
            if message is None:
                return
            message["status"] = "error"
            message["error"] = error_message
            message["updated_at"] = iso_now()
            session["active_turn_id"] = None
            session["status"] = "idle"
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_assistant_error",
                    "message_id": assistant_message_id,
                    "content": str(message.get("content", "")),
                    "updated_at": str(message["updated_at"]),
                    "error": error_message,
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _handle_tool_call(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        user_message_id: str,
        assistant_message_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        if tool_name != "emit_render_data":
            return
        if not isinstance(arguments, dict):
            logger.warning("Invalid emit_render_data arguments for node %s", node_id)
            return
        kind = arguments.get("kind")
        if kind != "delta_context_suggestion":
            logger.warning("Unknown emit_render_data kind %r for node %s", kind, node_id)
            return
        payload = arguments.get("payload")
        if not isinstance(payload, dict):
            logger.warning("Invalid emit_render_data payload for node %s", node_id)
            return
        try:
            self._handle_delta_context_suggestion(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                payload=payload,
            )
        except Exception:
            logger.exception("Failed to capture ask delta context suggestion for node %s", node_id)

    def _handle_delta_context_suggestion(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        user_message_id: str,
        assistant_message_id: str,
        payload: dict[str, Any],
    ) -> None:
        summary = str(payload.get("summary") or "").strip()
        context_text = str(payload.get("context_text") or "").strip()
        if not summary or not context_text:
            logger.warning("Skipping ask delta context suggestion with empty fields for node %s", node_id)
            return

        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_node_context(project_id, node_id)
            if node.get("status") == "done" or self._is_superseded(node):
                logger.info("Ignoring ask packet suggestion for non-mutable node %s", node_id)
                return
            planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
            if planning_state.get("status") == "active":
                logger.info("Ignoring ask packet suggestion while planning is active for node %s", node_id)
                return
            if self._reject_packet_creation_after_split(
                snapshot=snapshot,
                node=node,
                node_id=node_id,
                action="create",
                raise_on_block=False,
            ):
                return

            raw_session = self._storage.thread_store.get_ask_state(project_id, node_id)
            session = self._normalize_ask_session(project_id=project_id, node_id=node_id, ask_state=raw_session)
            if session.get("active_turn_id") != turn_id:
                logger.info("Ignoring stale ask packet suggestion for node %s turn %s", node_id, turn_id)
                return
            if self._find_message(session, user_message_id) is None or self._find_message(session, assistant_message_id) is None:
                logger.info("Ignoring ask packet suggestion with missing source messages for node %s", node_id)
                return

            packet = self._build_packet(
                node_id=node_id,
                summary=summary,
                context_text=context_text,
                source_message_ids=[user_message_id, assistant_message_id],
                suggested_by="agent",
            )
            session["delta_context_packets"].append(copy.deepcopy(packet))
            event = self._persist_session_event(
                project_id,
                node_id,
                session,
                {
                    "type": "ask_delta_context_suggested",
                    "packet": copy.deepcopy(packet),
                },
            )

        self._event_broker.publish(project_id, node_id, event)

    def _node_has_active_children(self, snapshot: dict[str, Any], node: dict[str, Any]) -> bool:
        node_by_id = self._snapshot_node_index(snapshot)
        for child_id in node.get("child_ids", []):
            if not isinstance(child_id, str):
                continue
            child = node_by_id.get(child_id)
            if child is None or self._is_superseded(child):
                continue
            return True
        return False

    def _build_packet(
        self,
        *,
        node_id: str,
        summary: str,
        context_text: str,
        source_message_ids: list[str],
        suggested_by: str,
    ) -> dict[str, Any]:
        return {
            "packet_id": new_id("dctx"),
            "node_id": node_id,
            "created_at": iso_now(),
            "source_message_ids": list(source_message_ids),
            "summary": summary,
            "context_text": context_text,
            "status": "pending",
            "status_reason": None,
            "merged_at": None,
            "merged_planning_turn_id": None,
            "suggested_by": suggested_by,
        }

    def _reject_packet_creation_after_split(
        self,
        *,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_id: str,
        action: str,
        raise_on_block: bool,
    ) -> bool:
        if not self._node_has_active_children(snapshot, node):
            return False
        if raise_on_block:
            raise PacketMutationBlockedBySplit(action, node_id)
        logger.info("Ignoring ask packet %s on split node %s", action, node_id)
        return True

    def _assert_merge_preconditions(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
    ) -> None:
        if self._node_has_active_children(snapshot, node):
            raise MergeBlockedBySplit(node_id)
        if node.get("status") == "done" or self._is_superseded(node):
            raise AskThreadReadOnly()
        planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
        if planning_state.get("status") == "active":
            raise AskBlockedByPlanningActive()
        ask_state = self._storage.thread_store.get_ask_state(project_id, node_id)
        if ask_state.get("active_turn_id"):
            raise AskTurnAlreadyActive()

    def _release_reserved_merge_turn(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._storage.project_lock(project_id):
            planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
            if (
                planning_state.get("status") == "active"
                and str(planning_state.get("active_turn_id") or "") == turn_id
            ):
                self._storage.thread_store.set_planning_status(
                    project_id,
                    node_id,
                    status="idle",
                    active_turn_id=None,
                )

    def _persist_session_event(
        self,
        project_id: str,
        node_id: str,
        session: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event_seq = self._advance_event_seq(session)
        self._write_ask_session_state(project_id, node_id, session)
        event = {"event_seq": event_seq, **payload}
        if payload.get("type") == "ask_session_reset":
            event["session"] = self._public_session(session)
        return event

    def _write_ask_session_state(self, project_id: str, node_id: str, session: dict[str, Any]) -> None:
        self._storage.thread_store.write_ask_session(
            project_id,
            node_id,
            self._storage_session_payload(session),
        )

    def _storage_session_payload(self, session: dict[str, Any]) -> dict[str, Any]:
        return {
            "thread_id": session.get("thread_id"),
            "forked_from_planning_thread_id": session.get("forked_from_planning_thread_id"),
            "status": session.get("status"),
            "active_turn_id": session.get("active_turn_id"),
            "messages": copy.deepcopy(session.get("messages", [])),
            "event_seq": session.get("event_seq", 0),
            "delta_context_packets": copy.deepcopy(session.get("delta_context_packets", [])),
            "created_at": session.get("created_at"),
        }

    def _advance_event_seq(self, session: dict[str, Any]) -> int:
        try:
            current = int(session.get("event_seq", 0))
        except (TypeError, ValueError):
            current = 0
        next_event_seq = max(0, current) + 1
        session["event_seq"] = next_event_seq
        return next_event_seq

    def _find_message(self, session: dict[str, Any], message_id: str) -> dict[str, Any] | None:
        for message in session.get("messages", []):
            if isinstance(message, dict) and str(message.get("message_id")) == message_id:
                return message
        return None

    def _find_packet(self, session: dict[str, Any], packet_id: str) -> dict[str, Any] | None:
        for packet in session.get("delta_context_packets", []):
            if isinstance(packet, dict) and str(packet.get("packet_id")) == packet_id:
                return packet
        return None

    def _recover_stale_turn(self, session: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        active_turn_id = session.get("active_turn_id")
        if not active_turn_id:
            return session, False
        turn_key = (
            str(session.get("project_id") or ""),
            str(session.get("node_id") or ""),
            str(active_turn_id),
        )
        if self._is_live_turn(turn_key):
            return session, False
        session["active_turn_id"] = None
        session["status"] = "idle"
        updated_at = iso_now()
        for message in reversed(session.get("messages", [])):
            if (
                isinstance(message, dict)
                and message.get("role") == "assistant"
                and message.get("status") in {"pending", "streaming"}
            ):
                message["status"] = "error"
                message["error"] = STALE_ASK_TURN_ERROR
                message["updated_at"] = updated_at
                break
        return session, True

    def _normalize_message(self, message: dict[str, Any]) -> dict[str, Any]:
        created_at = str(message.get("created_at") or iso_now())
        updated_at = str(message.get("updated_at") or created_at)
        error = message.get("error")
        return {
            "message_id": str(message.get("message_id") or new_id("msg")),
            "role": "assistant" if str(message.get("role")) == "assistant" else "user",
            "content": str(message.get("content") or ""),
            "status": self._normalize_message_status(message.get("status")),
            "created_at": created_at,
            "updated_at": updated_at,
            "error": str(error) if error is not None and str(error).strip() else None,
        }

    def _normalize_message_status(self, raw_status: Any) -> str:
        status = str(raw_status or "").strip().lower()
        if status in {"pending", "streaming", "completed", "error"}:
            return status
        return "completed"

    def _assert_node_is_read_only(self, node: dict[str, Any]) -> None:
        if node.get("status") == "done" or self._is_superseded(node):
            raise AskThreadReadOnly()

    def _assert_node_is_writable(
        self,
        project_id: str,
        node_id: str,
        *,
        snapshot: dict[str, Any] | None = None,
        node: dict[str, Any] | None = None,
    ) -> None:
        if snapshot is None or node is None:
            snapshot, node, _ = self._load_node_context(project_id, node_id)
        self._assert_node_is_read_only(node)
        planning_state = self._storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
        if planning_state.get("status") == "active":
            raise AskBlockedByPlanningActive()

    def _snapshot_node_index(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        tree_state = snapshot.get("tree_state", {})
        if not isinstance(tree_state, dict):
            return {}
        node_index = tree_state.get("node_index")
        if isinstance(node_index, dict):
            return {
                str(node_id): node
                for node_id, node in node_index.items()
                if isinstance(node_id, str) and isinstance(node, dict)
            }
        registry = tree_state.get("node_registry", [])
        if not isinstance(registry, list):
            return {}
        return {
            str(item["node_id"]): item
            for item in registry
            if isinstance(item, dict) and isinstance(item.get("node_id"), str)
        }

    def _node_from_snapshot(self, snapshot: dict[str, Any], node_id: str) -> dict[str, Any] | None:
        return self._snapshot_node_index(snapshot).get(node_id)

    def _is_superseded(self, node: dict[str, Any]) -> bool:
        return str(node.get("node_kind") or "") == "superseded" or bool(node.get("is_superseded"))

    def _mark_live_turn(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_turns_lock:
            self._live_turns.add((project_id, node_id, turn_id))

    def _clear_live_turn(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_turns_lock:
            self._live_turns.discard((project_id, node_id, turn_id))

    def _is_live_turn(self, turn_key: tuple[str, str, str]) -> bool:
        with self._live_turns_lock:
            return turn_key in self._live_turns
