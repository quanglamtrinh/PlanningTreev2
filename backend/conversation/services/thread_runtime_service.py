from __future__ import annotations

import json
import logging
import threading
from typing import Any

from backend.conversation.domain import events as event_types
from backend.conversation.domain.types import (
    ConversationItem,
    ThreadRole,
    ThreadSnapshotV2,
    UserInputAnswer,
    copy_snapshot,
    normalize_user_input_answer,
)
from backend.conversation.projector.thread_event_projector import (
    apply_lifecycle,
    apply_raw_event,
    apply_resolved_user_input,
    finalize_turn,
    patch_item,
    upsert_item,
)
from backend.conversation.services.request_ledger_service import RequestLedgerService
from backend.conversation.services.thread_query_service import ThreadQueryService
from backend.errors.app_errors import ChatBackendUnavailable, ChatTurnAlreadyActive, InvalidRequest
from backend.storage.file_utils import iso_now, new_id

logger = logging.getLogger(__name__)

_ASK_READ_ONLY_POLICY_ERROR = (
    "Ask lane is read-only. File-change output is not allowed in ask turns."
)


class ThreadRuntimeService:
    def __init__(
        self,
        *,
        storage: Any,
        tree_service: Any,
        chat_service: Any,
        codex_client: Any,
        query_service: ThreadQueryService,
        request_ledger_service: RequestLedgerService,
        chat_timeout: int,
        max_message_chars: int = 10000,
        ask_rollout_metrics_service: Any | None = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._chat_service = chat_service
        self._codex_client = codex_client
        self._query_service = query_service
        self._request_ledger_service = request_ledger_service
        self._chat_timeout = int(chat_timeout)
        self._max_message_chars = int(max_message_chars)
        self._ask_rollout_metrics_service = ask_rollout_metrics_service

    def start_turn(
        self,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del metadata
        self._chat_service._validate_thread_access(project_id, node_id, thread_role)
        self._chat_service._check_thread_writable(project_id, node_id, thread_role)
        cleaned = str(text or "").strip()
        if not cleaned:
            raise InvalidRequest("Message text is required.")
        if len(cleaned) > self._max_message_chars:
            raise InvalidRequest(
                f"Message text exceeds {self._max_message_chars} character limit."
            )
        if thread_role == "audit":
            self._chat_service._maybe_start_local_review_for_audit_write(project_id, node_id)

        snapshot = self._query_service.get_thread_snapshot(project_id, node_id, thread_role)
        if snapshot.get("activeTurnId"):
            raise ChatTurnAlreadyActive()
        thread_id = str(snapshot.get("threadId") or "").strip()
        if not thread_id:
            raise ChatBackendUnavailable("V2 thread bootstrap did not return a thread id.")

        turn_id = new_id("turn")
        user_item = self._build_local_user_item(
            snapshot=snapshot,
            thread_id=thread_id,
            turn_id=turn_id,
            text=cleaned,
        )
        updated = self.begin_turn(
            project_id=project_id,
            node_id=node_id,
            thread_role=thread_role,
            origin="interactive",
            created_items=[user_item],
            turn_id=turn_id,
        )
        if thread_role == "ask_planning":
            self._append_legacy_user_message(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                turn_id=turn_id,
                text=cleaned,
            )

        threading.Thread(
            target=self._run_background_turn,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "thread_role": thread_role,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "input_text": cleaned,
            },
            daemon=True,
        ).start()

        return {
            "accepted": True,
            "threadId": thread_id,
            "turnId": turn_id,
            "snapshotVersion": updated["snapshotVersion"],
            "createdItems": [user_item],
        }

    def begin_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        origin: str,
        created_items: list[ConversationItem],
        turn_id: str | None = None,
    ) -> ThreadSnapshotV2:
        del origin
        snapshot = self._query_service.get_thread_snapshot(project_id, node_id, thread_role)
        if snapshot.get("activeTurnId"):
            raise ChatTurnAlreadyActive()
        resolved_turn_id = str(turn_id or new_id("turn"))
        thread_id = str(snapshot.get("threadId") or "").strip() or None
        updated = copy_snapshot(snapshot)
        events: list[dict[str, Any]] = []
        for item in created_items:
            normalized = dict(item)
            normalized["threadId"] = thread_id or str(item.get("threadId") or "")
            normalized["turnId"] = resolved_turn_id
            updated, item_events = upsert_item(updated, normalized)  # type: ignore[arg-type]
            events.extend(item_events)
        updated, lifecycle_events = apply_lifecycle(
            updated,
            state=event_types.TURN_STARTED,
            processing_state="running",
            active_turn_id=resolved_turn_id,
        )
        events.extend(lifecycle_events)
        persisted, _ = self._query_service.persist_thread_mutation(
            project_id,
            node_id,
            thread_role,
            updated,
            events,
        )
        if thread_role == "ask_planning":
            self._query_service.sync_legacy_turn_state(
                project_id,
                node_id,
                thread_role,
                thread_id=thread_id,
                active_turn_id=resolved_turn_id,
            )
        self._chat_service.register_external_live_turn(
            project_id,
            node_id,
            thread_role,
            resolved_turn_id,
        )
        return persisted

    def complete_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        turn_id: str,
        outcome: str,
        error_item: ConversationItem | None = None,
    ) -> ThreadSnapshotV2:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        updated, events = finalize_turn(
            snapshot,
            turn_id=turn_id,
            outcome=outcome,
            error_item=error_item,
        )

        persisted, _ = self._query_service.persist_thread_mutation(
            project_id,
            node_id,
            thread_role,
            updated,
            events,
        )
        if outcome == "waiting_user_input":
            return persisted
        if thread_role == "ask_planning":
            self._query_service.clear_legacy_turn_state(
                project_id,
                node_id,
                thread_role,
                thread_id=persisted.get("threadId"),
            )
        self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)
        return persisted

    def resolve_user_input(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        request_id: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        pending = self._find_pending_request(snapshot, request_id)
        if pending is None:
            raise InvalidRequest(f"Unknown user-input request {request_id!r}.")
        normalized_answers = self._normalize_answers(answers)
        submitted_at = iso_now()
        updated = self._request_ledger_service.submit_answers(
            snapshot,
            request_id=request_id,
            answers=normalized_answers,
        )
        updated, submit_events = patch_item(
            updated,
            str(pending.get("itemId") or ""),
            {
                "kind": "userInput",
                "answersReplace": normalized_answers,
                "status": "answer_submitted",
                "updatedAt": submitted_at,
            },
        )
        self._query_service.persist_thread_mutation(
            project_id,
            node_id,
            thread_role,
            updated,
            submit_events,
        )

        rpc_answers = {str(answer["questionId"]): answer.get("value") for answer in normalized_answers}
        record = self._codex_client.resolve_runtime_request_user_input(
            request_id,
            answers=rpc_answers,
        )
        if record is None:
            raise InvalidRequest(f"Unknown runtime user-input request {request_id!r}.")

        resolved_at = iso_now()
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        updated, resolved_events = apply_resolved_user_input(
            snapshot,
            request_id=request_id,
            item_id=str(pending.get("itemId") or ""),
            answers=normalized_answers,
            resolved_at=resolved_at,
        )
        if (
            snapshot.get("processingState") == "waiting_user_input"
            and str(snapshot.get("activeTurnId") or "") == str(pending.get("turnId") or "")
        ):
            updated, lifecycle_events = apply_lifecycle(
                updated,
                state=event_types.TURN_COMPLETED,
                processing_state="idle",
                active_turn_id=None,
            )
            resolved_events.extend(lifecycle_events)
        persisted, _ = self._query_service.persist_thread_mutation(
            project_id,
            node_id,
            thread_role,
            updated,
            resolved_events,
        )
        if str(persisted.get("activeTurnId") or "") != str(pending.get("turnId") or ""):
            if thread_role == "ask_planning":
                self._query_service.clear_legacy_turn_state(
                    project_id,
                    node_id,
                    thread_role,
                    thread_id=persisted.get("threadId"),
                )
            turn_id = str(pending.get("turnId") or "").strip()
            if turn_id:
                self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)
        return {
            "requestId": request_id,
            "itemId": str(pending.get("itemId") or ""),
            "threadId": str(snapshot.get("threadId") or ""),
            "turnId": pending.get("turnId"),
            "status": "answer_submitted",
            "answers": normalized_answers,
            "submittedAt": submitted_at,
        }

    def upsert_system_message(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        item_id: str,
        turn_id: str | None,
        text: str,
        tone: str = "neutral",
        metadata: dict[str, Any] | None = None,
    ) -> ThreadSnapshotV2:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        now = iso_now()
        item: ConversationItem = {
            "id": item_id,
            "kind": "message",
            "threadId": str(snapshot.get("threadId") or ""),
            "turnId": turn_id,
            "sequence": self._next_sequence(snapshot),
            "createdAt": now,
            "updatedAt": now,
            "status": "completed",
            "source": "backend",
            "tone": tone,  # type: ignore[typeddict-item]
            "metadata": dict(metadata or {}),
            "role": "system",
            "text": str(text or ""),
            "format": "markdown",
        }
        updated, events = upsert_item(snapshot, item)
        persisted, _ = self._query_service.persist_thread_mutation(
            project_id,
            node_id,
            thread_role,
            updated,
            events,
        )
        return persisted

    def stream_agent_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        thread_id: str,
        turn_id: str,
        prompt: str,
        cwd: str | None,
        writable_roots: list[str] | None = None,
        sandbox_profile: str | None = None,
        output_schema: dict[str, Any] | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        provisional_tool_calls: dict[str, dict[str, Any]] = {}
        final_turn_status = "completed"

        def handle_raw_event(raw_event: dict[str, Any]) -> None:
            nonlocal final_turn_status
            method = str(raw_event.get("method") or "").strip()
            if not method:
                return
            if method == "item/tool/call":
                call_id = str(raw_event.get("call_id") or "").strip()
                if not call_id:
                    return
                params = raw_event.get("params", {})
                provisional_tool_calls[call_id] = {
                    "callId": call_id,
                    "toolName": str(params.get("tool_name") or params.get("toolName") or "").strip() or None
                    if isinstance(params, dict)
                    else None,
                    "arguments": params.get("arguments") if isinstance(params, dict) else {},
                    "threadId": str(raw_event.get("thread_id") or thread_id),
                    "turnId": str(raw_event.get("turn_id") or turn_id),
                    "createdAt": str(raw_event.get("received_at") or iso_now()),
                    "matched": False,
                }
                return

            current = self._query_service.get_thread_snapshot(
                project_id,
                node_id,
                thread_role,
                publish_repairs=False,
                ensure_binding=False,
                allow_thread_read_hydration=False,
            )
            updated = current
            events: list[dict[str, Any]] = []

            if method == "item/started":
                self._enrich_started_item_from_provisional_call(raw_event, provisional_tool_calls)

            if method == "turn/completed":
                params = raw_event.get("params", {})
                turn_payload = params.get("turn", {}) if isinstance(params, dict) else {}
                raw_status = (
                    str(turn_payload.get("status") or params.get("status") or "").strip().lower()
                    if isinstance(turn_payload, dict)
                    else str(params.get("status") or "").strip().lower()
                )
                if raw_status:
                    final_turn_status = raw_status

            updated, raw_events = apply_raw_event(updated, raw_event)
            events.extend(raw_events)
            if events:
                self._query_service.persist_thread_mutation(
                    project_id,
                    node_id,
                    thread_role,
                    updated,
                    events,
                )

        try:
            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=int(timeout_sec or self._chat_timeout),
                cwd=cwd,
                writable_roots=writable_roots,
                sandbox_profile=sandbox_profile,
                on_raw_event=handle_raw_event,
                output_schema=output_schema,
            )
            returned_status = str(result.get("turn_status") or "").strip().lower()
            if returned_status:
                final_turn_status = returned_status
            self._flush_unmatched_provisional_tools(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                provisional_tool_calls=provisional_tool_calls,
            )
            return {
                "result": result,
                "turnStatus": final_turn_status,
            }
        except Exception:
            self._flush_unmatched_provisional_tools(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                provisional_tool_calls=provisional_tool_calls,
            )
            raise

    @staticmethod
    def outcome_from_turn_status(turn_status: str | None) -> str:
        normalized = str(turn_status or "").strip().lower()
        if normalized in {"waiting_user_input", "waitingforuserinput", "waiting_for_user_input"}:
            return "waiting_user_input"
        if normalized in {"failed", "error", "interrupted", "cancelled"}:
            return "failed"
        return "completed"

    @staticmethod
    def _looks_like_patch_text(text: str) -> bool:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        return (
            "*** Begin Patch" in normalized
            or "diff --git " in normalized
            or "\n@@ " in f"\n{normalized}"
            or "\n+++ " in f"\n{normalized}"
            or "\n--- " in f"\n{normalized}"
        )

    @classmethod
    def _tool_call_arguments_text(cls, arguments: Any) -> str | None:
        if isinstance(arguments, str):
            trimmed = arguments.strip()
            return trimmed or None

        if isinstance(arguments, dict):
            for key in ("input", "patch", "diff", "content", "text", "value", "body"):
                raw = arguments.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw
            for raw in arguments.values():
                if isinstance(raw, str) and cls._looks_like_patch_text(raw):
                    return raw
            if arguments:
                return json.dumps(arguments, ensure_ascii=True, sort_keys=True)

        return None

    @classmethod
    def _enrich_started_item_from_provisional_call(
        cls,
        raw_event: dict[str, Any],
        provisional_tool_calls: dict[str, dict[str, Any]],
    ) -> None:
        params = raw_event.get("params", {})
        item = params.get("item", {}) if isinstance(params, dict) else {}
        if not isinstance(item, dict):
            return

        call_id = str(item.get("callId") or item.get("call_id") or "").strip()
        item_id = str(item.get("id") or "").strip()
        candidate_ids: list[str] = []
        if call_id:
            candidate_ids.append(call_id)
        if item_id and item_id not in candidate_ids:
            candidate_ids.append(item_id)

        matched_call_id: str | None = None
        record: dict[str, Any] | None = None
        for candidate_id in candidate_ids:
            candidate_record = provisional_tool_calls.get(candidate_id)
            if isinstance(candidate_record, dict):
                matched_call_id = candidate_id
                record = candidate_record
                break
        if record is None:
            return

        record["matched"] = True
        if not call_id and matched_call_id:
            item["callId"] = matched_call_id

        if not item.get("toolName") and record.get("toolName"):
            item["toolName"] = record.get("toolName")

        item_type = str(item.get("type") or "").strip()
        if item_type != "fileChange":
            return

        existing = item.get("argumentsText")
        if isinstance(existing, str) and existing.strip():
            return

        arguments_text = cls._tool_call_arguments_text(record.get("arguments"))
        if isinstance(arguments_text, str) and arguments_text.strip():
            item["argumentsText"] = arguments_text

    def build_error_item_for_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        turn_id: str,
        message: str,
        thread_id: str | None = None,
    ) -> ConversationItem:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        resolved_thread_id = str(thread_id or snapshot.get("threadId") or "")
        return self._build_error_item(
            turn_id=turn_id,
            thread_id=resolved_thread_id,
            message=message,
            sequence=self._next_sequence(snapshot),
        )

    def _run_background_turn(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        thread_id: str,
        turn_id: str,
        input_text: str,
    ) -> None:
        provisional_tool_calls: dict[str, dict[str, Any]] = {}
        final_turn_status = "completed"
        boundary_prompt_kind: str | None = None

        def handle_raw_event(raw_event: dict[str, Any]) -> None:
            nonlocal final_turn_status
            method = str(raw_event.get("method") or "").strip()
            if not method:
                return
            if method == "item/tool/call":
                call_id = str(raw_event.get("call_id") or "").strip()
                if not call_id:
                    return
                params = raw_event.get("params", {})
                provisional_tool_calls[call_id] = {
                    "callId": call_id,
                    "toolName": str(params.get("tool_name") or params.get("toolName") or "").strip() or None
                    if isinstance(params, dict)
                    else None,
                    "arguments": params.get("arguments") if isinstance(params, dict) else {},
                    "threadId": str(raw_event.get("thread_id") or thread_id),
                    "turnId": str(raw_event.get("turn_id") or turn_id),
                    "createdAt": str(raw_event.get("received_at") or iso_now()),
                    "matched": False,
                }
                return

            current = self._query_service.get_thread_snapshot(
                project_id,
                node_id,
                thread_role,
                publish_repairs=False,
                ensure_binding=False,
                allow_thread_read_hydration=False,
            )
            updated = current
            events: list[dict[str, Any]] = []

            if method == "item/started":
                self._enrich_started_item_from_provisional_call(raw_event, provisional_tool_calls)

            if method == "turn/completed":
                params = raw_event.get("params", {})
                turn_payload = params.get("turn", {}) if isinstance(params, dict) else {}
                raw_status = (
                    str(turn_payload.get("status") or params.get("status") or "").strip().lower()
                    if isinstance(turn_payload, dict)
                    else str(params.get("status") or "").strip().lower()
                )
                if raw_status:
                    final_turn_status = raw_status
                return

            updated, raw_events = apply_raw_event(updated, raw_event)
            events.extend(raw_events)
            if events:
                self._query_service.persist_thread_mutation(
                    project_id,
                    node_id,
                    thread_role,
                    updated,
                    events,
                )

        try:
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            workspace_root = self._chat_service._workspace_root_from_snapshot(snapshot)
            prompt, boundary_prompt_kind = self._chat_service._build_prompt_for_turn(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                thread_role=thread_role,
                snapshot=snapshot,
                node=node,
                node_by_id=node_by_id,
                user_content=input_text,
            )
            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                writable_roots=None,
                sandbox_profile="read_only" if thread_role == "ask_planning" else None,
                on_raw_event=handle_raw_event,
            )
            returned_status = str(result.get("turn_status") or "").strip().lower()
            if returned_status:
                final_turn_status = returned_status
            self._flush_unmatched_provisional_tools(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                provisional_tool_calls=provisional_tool_calls,
            )
            policy_violation_message: str | None = None
            if thread_role == "ask_planning":
                policy_snapshot = self._query_service.get_thread_snapshot(
                    project_id,
                    node_id,
                    thread_role,
                    publish_repairs=False,
                    ensure_binding=False,
                    allow_thread_read_hydration=False,
                )
                if self._ask_turn_contains_file_change_items(policy_snapshot, turn_id):
                    policy_violation_message = _ASK_READ_ONLY_POLICY_ERROR
                    self._record_ask_guard_violation()
                    final_turn_status = "failed"
            outcome = "completed"
            if final_turn_status in {"waiting_user_input", "waitingforuserinput", "waiting_for_user_input"}:
                outcome = "waiting_user_input"
            elif final_turn_status in {"failed", "error", "interrupted", "cancelled"}:
                outcome = "failed"
            error_item = None
            if outcome == "failed" and policy_violation_message:
                current_snapshot = self._query_service.get_thread_snapshot(
                    project_id,
                    node_id,
                    thread_role,
                    publish_repairs=False,
                )
                error_item = self._build_error_item(
                    turn_id=turn_id,
                    thread_id=thread_id,
                    message=policy_violation_message,
                    sequence=self._next_sequence(current_snapshot),
                )
            self.complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role=thread_role,
                turn_id=turn_id,
                outcome=outcome,
                error_item=error_item,
            )
            waiting_for_user_input = final_turn_status in {
                "waiting_user_input",
                "waitingforuserinput",
                "waiting_for_user_input",
            }
            if not waiting_for_user_input:
                if thread_role == "ask_planning":
                    self._query_service.clear_legacy_turn_state(
                        project_id,
                        node_id,
                        thread_role,
                        thread_id=thread_id,
                    )
                self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)
                if thread_role == "ask_planning":
                    final_snapshot = self._query_service.get_thread_snapshot(
                        project_id,
                        node_id,
                        thread_role,
                        publish_repairs=False,
                    )
                    self._upsert_legacy_assistant_message_from_snapshot(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role=thread_role,
                        turn_id=turn_id,
                        snapshot=final_snapshot,
                        error=None if final_turn_status not in {"failed", "error", "interrupted", "cancelled"} else "Turn failed.",
                    )
                if boundary_prompt_kind == "local_review" and thread_role == "audit":
                    self._chat_service._mark_local_review_prompt_consumed(project_id, node_id)
                elif boundary_prompt_kind == "package_review" and thread_role == "audit":
                    self._chat_service._mark_package_review_prompt_consumed(project_id, node_id)
        except Exception as exc:
            logger.debug(
                "V2 thread turn failed for %s/%s/%s: %s",
                project_id,
                node_id,
                thread_role,
                exc,
                exc_info=True,
            )
            try:
                self._flush_unmatched_provisional_tools(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    provisional_tool_calls=provisional_tool_calls,
                )
                current_snapshot = self._query_service.get_thread_snapshot(
                    project_id,
                    node_id,
                    thread_role,
                    publish_repairs=False,
                )
                error_item = self._build_error_item(
                    turn_id=turn_id,
                    thread_id=thread_id,
                    message=str(exc),
                    sequence=self._next_sequence(current_snapshot),
                )
                final_snapshot = self.complete_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role=thread_role,
                    turn_id=turn_id,
                    outcome="failed",
                    error_item=error_item,
                )
                if thread_role == "ask_planning":
                    self._upsert_legacy_assistant_message_from_snapshot(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role=thread_role,
                        turn_id=turn_id,
                        snapshot=final_snapshot,
                        error=str(exc),
                    )
            finally:
                if thread_role == "ask_planning":
                    self._query_service.clear_legacy_turn_state(
                        project_id,
                        node_id,
                        thread_role,
                        thread_id=thread_id,
                    )
                self._chat_service.clear_external_live_turn(project_id, node_id, thread_role, turn_id)

    @staticmethod
    def _ask_turn_contains_file_change_items(snapshot: ThreadSnapshotV2, turn_id: str) -> bool:
        for item in snapshot.get("items", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("turnId") or "") != str(turn_id):
                continue
            if str(item.get("kind") or "").strip() != "tool":
                continue
            if str(item.get("toolType") or "").strip() == "fileChange":
                return True
            output_files = item.get("outputFiles")
            if isinstance(output_files, list) and len(output_files) > 0:
                return True
        return False

    def _record_ask_guard_violation(self) -> None:
        metrics = self._ask_rollout_metrics_service
        if metrics is None:
            return
        try:
            metrics.record_guard_violation()
        except Exception:
            logger.debug("Failed to record ask guard violation metric.", exc_info=True)

    def _build_local_user_item(
        self,
        *,
        snapshot: ThreadSnapshotV2,
        thread_id: str,
        turn_id: str,
        text: str,
    ) -> ConversationItem:
        now = iso_now()
        return {
            "id": f"turn:{turn_id}:user",
            "kind": "message",
            "threadId": thread_id,
            "turnId": turn_id,
            "sequence": self._next_sequence(snapshot),
            "createdAt": now,
            "updatedAt": now,
            "status": "completed",
            "source": "local",
            "tone": "neutral",
            "metadata": {},
            "role": "user",
            "text": text,
            "format": "markdown",
        }

    def _build_error_item(
        self,
        *,
        turn_id: str,
        thread_id: str,
        message: str,
        sequence: int,
    ) -> ConversationItem:
        now = iso_now()
        return {
            "id": f"error:{turn_id}",
            "kind": "error",
            "threadId": thread_id,
            "turnId": turn_id,
            "sequence": sequence,
            "createdAt": now,
            "updatedAt": now,
            "status": "failed",
            "source": "backend",
            "tone": "danger",
            "metadata": {},
            "code": "conversation_turn_failed",
            "title": "Turn failed",
            "message": message,
            "recoverable": True,
            "relatedItemId": None,
        }

    def _flush_unmatched_provisional_tools(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        provisional_tool_calls: dict[str, dict[str, Any]],
    ) -> None:
        snapshot = self._query_service.get_thread_snapshot(
            project_id,
            node_id,
            thread_role,
            publish_repairs=False,
        )
        updated, events = self._finalize_unmatched_provisional_tools(
            snapshot,
            provisional_tool_calls,
        )
        if events:
            self._query_service.persist_thread_mutation(
                project_id,
                node_id,
                thread_role,
                updated,
                events,
            )

    def _finalize_unmatched_provisional_tools(
        self,
        snapshot: ThreadSnapshotV2,
        provisional_tool_calls: dict[str, dict[str, Any]],
    ) -> tuple[ThreadSnapshotV2, list[dict[str, Any]]]:
        updated = copy_snapshot(snapshot)
        events: list[dict[str, Any]] = []
        for call_id, record in list(provisional_tool_calls.items()):
            if record.get("matched"):
                continue
            arguments = record.get("arguments") if isinstance(record.get("arguments"), dict) else {}
            arguments_text = json.dumps(arguments, ensure_ascii=True, sort_keys=True) if arguments else None
            item: ConversationItem = {
                "id": f"tool-call:{call_id}",
                "kind": "tool",
                "threadId": str(record.get("threadId") or snapshot.get("threadId") or ""),
                "turnId": str(record.get("turnId") or snapshot.get("activeTurnId") or "") or None,
                "sequence": self._next_sequence(updated),
                "createdAt": str(record.get("createdAt") or iso_now()),
                "updatedAt": iso_now(),
                "status": "completed",
                "source": "upstream",
                "tone": "neutral",
                "metadata": {"provisional": True},
                "toolType": "generic",
                "title": str(record.get("toolName") or "tool"),
                "toolName": record.get("toolName"),
                "callId": call_id,
                "argumentsText": arguments_text,
                "outputText": "",
                "outputFiles": [],
                "exitCode": None,
            }
            updated, upsert_events = upsert_item(updated, item)
            events.extend(upsert_events)
            provisional_tool_calls[call_id]["matched"] = True
        return updated, events

    def _normalize_answers(self, answers: list[dict[str, Any]]) -> list[UserInputAnswer]:
        normalized_answers: list[UserInputAnswer] = []
        for answer in answers:
            normalized = normalize_user_input_answer(answer)
            if normalized is not None:
                normalized_answers.append(normalized)
        if not normalized_answers:
            raise InvalidRequest("answers must contain at least one valid answer.")
        return normalized_answers

    def _find_pending_request(self, snapshot: ThreadSnapshotV2, request_id: str) -> dict[str, Any] | None:
        for pending in snapshot.get("pendingRequests", []):
            if str(pending.get("requestId") or "") == request_id:
                return pending
        return None

    def _append_legacy_user_message(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        turn_id: str,
        text: str,
    ) -> None:
        now = iso_now()
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            session["messages"].append(
                {
                    "message_id": new_id("msg"),
                    "role": "user",
                    "content": text,
                    "status": "completed",
                    "error": None,
                    "turn_id": turn_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            self._storage.chat_state_store.write_session(
                project_id,
                node_id,
                session,
                thread_role=thread_role,
            )

    def _upsert_legacy_assistant_message_from_snapshot(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_role: ThreadRole,
        turn_id: str,
        snapshot: ThreadSnapshotV2,
        error: str | None,
    ) -> None:
        assistant_items = [
            item
            for item in snapshot.get("items", [])
            if str(item.get("kind") or "") == "message"
            and str(item.get("role") or "") == "assistant"
            and str(item.get("turnId") or "") == turn_id
        ]
        content = str(assistant_items[-1].get("text") or "") if assistant_items else ""
        status = "error" if error else "completed"
        now = iso_now()
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            target = None
            for message in reversed(session.get("messages", [])):
                if str(message.get("role") or "") == "assistant" and str(message.get("turn_id") or "") == turn_id:
                    target = message
                    break
            if target is None:
                session["messages"].append(
                    {
                        "message_id": new_id("msg"),
                        "role": "assistant",
                        "content": content,
                        "status": status,
                        "error": error,
                        "turn_id": turn_id,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            else:
                target["content"] = content
                target["status"] = status
                target["error"] = error
                target["updated_at"] = now
            self._storage.chat_state_store.write_session(
                project_id,
                node_id,
                session,
                thread_role=thread_role,
            )

    @staticmethod
    def _next_sequence(snapshot: ThreadSnapshotV2) -> int:
        return max((int(item.get("sequence") or 0) for item in snapshot.get("items", [])), default=0) + 1
