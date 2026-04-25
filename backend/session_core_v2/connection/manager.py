from __future__ import annotations

import logging
import threading
import time
from typing import Any

from backend.session_core_v2.connection.state_machine import ConnectionStateMachine
from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.protocol.client import SessionProtocolClientV2
from backend.session_core_v2.storage.runtime_store import RuntimeStoreV2
from backend.session_core_v2.threads.service import ThreadServiceV2
from backend.session_core_v2.turns.service import TurnServiceV2

logger = logging.getLogger(__name__)

_TERMINAL_TURN_STATUSES: frozenset[str] = frozenset({"completed", "failed", "interrupted"})
_SERVER_REQUEST_METHODS: frozenset[str] = frozenset(
    {
        "item/tool/requestUserInput",
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
        "item/permissions/requestApproval",
        "mcpServer/elicitation/request",
    }
)


class SessionManagerV2:
    def __init__(
        self,
        *,
        protocol_client: SessionProtocolClientV2,
        runtime_store: RuntimeStoreV2,
        connection_state_machine: ConnectionStateMachine,
    ) -> None:
        self._protocol_client = protocol_client
        self._runtime_store = runtime_store
        self._connection_state_machine = connection_state_machine
        self._thread_service = ThreadServiceV2(protocol_client, logger=logger)
        self._turn_service = TurnServiceV2(protocol_client, logger=logger)
        # Serialize initialize to avoid concurrent connecting->connecting races.
        self._initialize_lock = threading.Lock()
        self._protocol_client.set_notification_handler(self._on_notification)
        self._protocol_client.set_server_request_handler(self._on_server_request)

    # ------------------------------------------------------------------
    # Connection and threads
    # ------------------------------------------------------------------
    def initialize(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        with self._initialize_lock:
            phase = self._connection_state_machine.phase
            if phase == "initialized":
                return self.status()

            started = time.perf_counter()
            client_info = request_payload.get("clientInfo")
            client_name = client_info.get("name") if isinstance(client_info, dict) else None
            try:
                self._connection_state_machine.set_connecting()
                response = self._protocol_client.initialize(request_payload)
                server_info = response.get("serverInfo")
                server_version = server_info.get("version") if isinstance(server_info, dict) else None
                self._connection_state_machine.set_initialized(
                    client_name=str(client_name or ""),
                    server_version=str(server_version or ""),
                )
                expired_count = self._runtime_store.expire_pending_server_requests_for_new_session()
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "session_core_v2 initialize ok",
                    extra={"latency_ms": elapsed_ms, "expiredPendingRequests": expired_count},
                )
                return self.status()
            except SessionCoreError as exc:
                self._connection_state_machine.set_error(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "session_core_v2 initialize failed",
                    extra={"latency_ms": elapsed_ms, "error_code": exc.code},
                )
                raise
            except Exception as exc:
                self._connection_state_machine.set_error(
                    code="ERR_INTERNAL",
                    message="Unexpected initialization failure.",
                    details={"reason": str(exc)},
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.exception(
                    "session_core_v2 initialize unexpected failure",
                    extra={"latency_ms": elapsed_ms},
                )
                raise SessionCoreError(
                    code="ERR_INTERNAL",
                    message="Unexpected initialization failure.",
                    status_code=500,
                    details={"reason": str(exc)},
                ) from exc

    def status(self) -> dict[str, Any]:
        return {"connection": self._connection_state_machine.snapshot()}

    def thread_start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_start(payload)

    def thread_resume(self, *, thread_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_resume(thread_id=thread_id, params=payload)

    def thread_fork(self, *, thread_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_fork(thread_id=thread_id, params=payload)

    def thread_list(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_list(payload)

    def thread_read(self, *, thread_id: str, include_turns: bool) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_read(thread_id=thread_id, include_turns=include_turns)

    def thread_turns_list(self, *, thread_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        provider_response = self._thread_service.thread_turns_list(thread_id=thread_id, params=payload)
        provider_turns_raw = provider_response.get("data")
        provider_turns = (
            [turn for turn in provider_turns_raw if isinstance(turn, dict)]
            if isinstance(provider_turns_raw, list)
            else []
        )
        runtime_turns = [
            self._to_api_turn(turn)
            for turn in self._runtime_store.list_turns(thread_id=thread_id)
        ]
        merged_turns = self._merge_turns_for_api(provider_turns=provider_turns, runtime_turns=runtime_turns)
        return {
            "data": merged_turns,
            "nextCursor": provider_response.get("nextCursor"),
        }

    def thread_loaded_list(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_loaded_list(params=payload)

    def thread_unsubscribe(self, *, thread_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        return self._thread_service.thread_unsubscribe(thread_id=thread_id)

    def thread_inject_items(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        client_action_id = self._require_non_empty(payload.get("clientActionId"), "clientActionId")
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="thread/inject_items requires non-empty items list.",
                status_code=400,
                details={"field": "items"},
            )
        if any(not isinstance(item, dict) for item in items):
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="thread/inject_items items must be objects.",
                status_code=400,
                details={"field": "items"},
            )

        idempotency_payload = {"threadId": thread_id, **payload}
        idempotent = self._runtime_store.resolve_idempotent_result(
            action_type="thread/inject_items",
            key=client_action_id,
            payload=idempotency_payload,
        )
        if idempotent is not None:
            logger.info(
                "session_core_v2 thread/inject_items idempotent replay",
                extra={
                    "threadId": thread_id,
                    "turnId": None,
                    "clientActionId": client_action_id,
                    "eventSeq": None,
                    "errorCode": None,
                },
            )
            return idempotent

        accepted_payload = self._thread_service.thread_inject_items(
            thread_id=thread_id,
            params=dict(payload),
        )
        replayable_context_items = 0
        for index, raw_item in enumerate(items):
            if not isinstance(raw_item, dict):
                continue
            metadata = self._extract_item_metadata(raw_item)
            if metadata.get("workflowContext") is not True:
                continue
            replayable_context_items += 1
            context_turn_id = self._resolve_context_turn_id(
                thread_id=thread_id,
                client_action_id=client_action_id,
                item=raw_item,
                index=index,
            )
            turn = self._runtime_store.create_turn(
                thread_id=thread_id,
                turn_id=context_turn_id,
                status="completed",
            )
            api_turn = self._to_api_turn(turn)
            self._runtime_store.append_turn_started_if_absent(
                thread_id=thread_id,
                turn_id=context_turn_id,
                turn=api_turn,
            )
            item_payload = dict(raw_item)
            item_payload["turnId"] = context_turn_id
            item_payload["status"] = "completed"
            item_payload["metadata"] = {**metadata, "workflowContext": True}
            self._runtime_store.append_notification(
                method="item/completed",
                params={"item": item_payload},
                thread_id_override=thread_id,
            )
            self._runtime_store.append_notification(
                method="turn/completed",
                params={"turn": api_turn},
                thread_id_override=thread_id,
            )
        self._runtime_store.record_idempotent_result(
            action_type="thread/inject_items",
            key=client_action_id,
            payload=idempotency_payload,
            response=accepted_payload,
            thread_id=thread_id,
        )
        logger.info(
            "session_core_v2 thread/inject_items accepted",
            extra={
                "threadId": thread_id,
                "turnId": None,
                "clientActionId": client_action_id,
                "eventSeq": None,
                "contextItemsAppended": replayable_context_items,
                "errorCode": None,
            },
        )
        return accepted_payload

    def model_list(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_initialized()
        response = self._protocol_client.model_list(payload or {})
        data = response.get("data")
        if not isinstance(data, list):
            data = []
        normalized_data = [entry for entry in data if isinstance(entry, dict)]
        next_cursor = response.get("nextCursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            next_cursor = str(next_cursor)
        return {
            "data": normalized_data,
            "nextCursor": next_cursor,
        }

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------
    def turn_start(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        client_action_id = self._require_non_empty(payload.get("clientActionId"), "clientActionId")
        input_payload = payload.get("input")
        if not isinstance(input_payload, list):
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="turn/start requires input list.",
                status_code=400,
                details={"field": "input"},
            )

        idempotent = self._runtime_store.resolve_idempotent_result(
            action_type="turn/start",
            key=client_action_id,
            payload={"threadId": thread_id, **payload},
        )
        if idempotent is not None:
            logger.info(
                "session_core_v2 turn/start idempotent replay",
                extra={
                    "threadId": thread_id,
                    "turnId": (idempotent.get("turn") or {}).get("id") if isinstance(idempotent.get("turn"), dict) else None,
                    "clientActionId": client_action_id,
                    "eventSeq": None,
                    "errorCode": None,
                },
            )
            return idempotent

        active_turn = self._runtime_store.get_active_turn(thread_id=thread_id)
        if active_turn is not None and str(active_turn.get("status")) not in _TERMINAL_TURN_STATUSES:
            raise SessionCoreError(
                code="ERR_TURN_NOT_STEERABLE",
                message="Cannot start a new turn while another turn is active.",
                status_code=409,
                details={"threadId": thread_id, "activeTurnId": active_turn.get("id")},
            )

        rpc_payload = dict(payload)
        rpc_payload.pop("clientActionId", None)
        response = self._turn_service.turn_start(thread_id=thread_id, params=rpc_payload)
        turn_id = self._extract_turn_id_from_response(response)
        if not turn_id:
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="turn/start response missing turnId (provider contract violation).",
                status_code=502,
                details={
                    "threadId": thread_id,
                    "clientActionId": client_action_id,
                    "providerMethod": "turn/start",
                },
            )

        self._runtime_store.create_turn(thread_id=thread_id, turn_id=turn_id, status="idle")
        turn = self._runtime_store.transition_turn(
            thread_id=thread_id,
            turn_id=turn_id,
            next_status="inProgress",
            allow_same=True,
            last_codex_status="inProgress",
        )
        turn_payload = {"turn": self._to_api_turn(turn)}
        self._runtime_store.append_turn_started_if_absent(
            thread_id=thread_id,
            turn_id=turn_id,
            turn=turn_payload["turn"],
        )
        self._runtime_store.record_idempotent_result(
            action_type="turn/start",
            key=client_action_id,
            payload={"threadId": thread_id, **payload},
            response=turn_payload,
            thread_id=thread_id,
            turn_id=turn_id,
        )
        logger.info(
            "session_core_v2 turn/start accepted",
            extra={
                "threadId": thread_id,
                "turnId": turn_id,
                "clientActionId": client_action_id,
                "eventSeq": None,
                "errorCode": None,
            },
        )
        return turn_payload

    def turn_steer(self, *, thread_id: str, path_turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        client_action_id = self._require_non_empty(payload.get("clientActionId"), "clientActionId")
        expected_turn_id = self._require_non_empty(payload.get("expectedTurnId"), "expectedTurnId")
        input_payload = payload.get("input")
        if not isinstance(input_payload, list):
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="turn/steer requires input list.",
                status_code=400,
                details={"field": "input"},
            )

        idempotent = self._runtime_store.resolve_idempotent_result(
            action_type="turn/steer",
            key=client_action_id,
            payload={"threadId": thread_id, "pathTurnId": path_turn_id, **payload},
        )
        if idempotent is not None:
            logger.info(
                "session_core_v2 turn/steer idempotent replay",
                extra={
                    "threadId": thread_id,
                    "turnId": path_turn_id,
                    "clientActionId": client_action_id,
                    "eventSeq": None,
                    "errorCode": None,
                },
            )
            return idempotent

        active_turn = self._runtime_store.get_active_turn(thread_id=thread_id)
        if active_turn is None:
            raise SessionCoreError(
                code="ERR_TURN_NOT_STEERABLE",
                message="No active turn to steer.",
                status_code=409,
                details={"threadId": thread_id},
            )
        active_turn_id = str(active_turn.get("id") or "")
        active_status = str(active_turn.get("status") or "")
        if active_status in _TERMINAL_TURN_STATUSES:
            raise SessionCoreError(
                code="ERR_TURN_TERMINAL",
                message=f"Turn {active_turn_id} is terminal.",
                status_code=409,
                details={"threadId": thread_id, "turnId": active_turn_id, "status": active_status},
            )
        if active_status != "inProgress":
            raise SessionCoreError(
                code="ERR_TURN_NOT_STEERABLE",
                message=f"Turn {active_turn_id} is not inProgress.",
                status_code=409,
                details={"threadId": thread_id, "turnId": active_turn_id, "status": active_status},
            )
        if expected_turn_id != active_turn_id or path_turn_id != active_turn_id:
            raise SessionCoreError(
                code="ERR_ACTIVE_TURN_MISMATCH",
                message="expectedTurnId/path turnId do not match active turn.",
                status_code=409,
                details={
                    "threadId": thread_id,
                    "activeTurnId": active_turn_id,
                    "expectedTurnId": expected_turn_id,
                    "pathTurnId": path_turn_id,
                },
            )

        rpc_payload = dict(payload)
        rpc_payload.pop("clientActionId", None)
        self._turn_service.turn_steer(thread_id=thread_id, params=rpc_payload)
        turn = self._runtime_store.transition_turn(
            thread_id=thread_id,
            turn_id=active_turn_id,
            next_status="inProgress",
            allow_same=True,
            last_codex_status="inProgress",
        )
        turn_payload = {"turn": self._to_api_turn(turn)}
        self._runtime_store.record_idempotent_result(
            action_type="turn/steer",
            key=client_action_id,
            payload={"threadId": thread_id, "pathTurnId": path_turn_id, **payload},
            response=turn_payload,
            thread_id=thread_id,
            turn_id=active_turn_id,
        )
        logger.info(
            "session_core_v2 turn/steer accepted",
            extra={
                "threadId": thread_id,
                "turnId": active_turn_id,
                "clientActionId": client_action_id,
                "eventSeq": None,
                "errorCode": None,
            },
        )
        return turn_payload

    def turn_interrupt(self, *, thread_id: str, turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        client_action_id = self._require_non_empty(payload.get("clientActionId"), "clientActionId")

        idempotent = self._runtime_store.resolve_idempotent_result(
            action_type="turn/interrupt",
            key=client_action_id,
            payload={"threadId": thread_id, "turnId": turn_id, **payload},
        )
        if idempotent is not None:
            logger.info(
                "session_core_v2 turn/interrupt idempotent replay",
                extra={
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "clientActionId": client_action_id,
                    "eventSeq": None,
                    "errorCode": None,
                },
            )
            return idempotent

        turn = self._runtime_store.get_turn(thread_id=thread_id, turn_id=turn_id)
        if turn is None:
            raise SessionCoreError(
                code="ERR_TURN_NOT_STEERABLE",
                message=f"Turn {turn_id} is not available for interrupt.",
                status_code=409,
                details={"threadId": thread_id, "turnId": turn_id},
            )
        status = str(turn.get("status") or "")
        if status in _TERMINAL_TURN_STATUSES:
            raise SessionCoreError(
                code="ERR_TURN_TERMINAL",
                message=f"Turn {turn_id} is terminal.",
                status_code=409,
                details={"threadId": thread_id, "turnId": turn_id, "status": status},
            )
        if status not in {"inProgress", "waitingUserInput"}:
            raise SessionCoreError(
                code="ERR_TURN_NOT_STEERABLE",
                message=f"Turn {turn_id} cannot be interrupted in state {status}.",
                status_code=409,
                details={"threadId": thread_id, "turnId": turn_id, "status": status},
            )

        active_turn = self._runtime_store.get_active_turn(thread_id=thread_id)
        if active_turn is not None and str(active_turn.get("id") or "") != turn_id:
            raise SessionCoreError(
                code="ERR_ACTIVE_TURN_MISMATCH",
                message="Interrupt target does not match active turn.",
                status_code=409,
                details={"threadId": thread_id, "activeTurnId": active_turn.get("id"), "turnId": turn_id},
            )

        self._turn_service.turn_interrupt(thread_id=thread_id, turn_id=turn_id)
        self._runtime_store.transition_turn(
            thread_id=thread_id,
            turn_id=turn_id,
            next_status="interrupted",
            allow_same=True,
            last_codex_status="interrupted",
        )
        response = {"status": "accepted"}
        self._runtime_store.record_idempotent_result(
            action_type="turn/interrupt",
            key=client_action_id,
            payload={"threadId": thread_id, "turnId": turn_id, **payload},
            response=response,
            thread_id=thread_id,
            turn_id=turn_id,
        )
        logger.info(
            "session_core_v2 turn/interrupt accepted",
            extra={
                "threadId": thread_id,
                "turnId": turn_id,
                "clientActionId": client_action_id,
                "eventSeq": None,
                "errorCode": None,
            },
        )
        return response

    # ------------------------------------------------------------------
    # Server requests
    # ------------------------------------------------------------------
    def requests_pending(self) -> dict[str, Any]:
        self._ensure_initialized()
        return {"data": self._runtime_store.list_pending_server_requests()}

    def request_resolve(self, *, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        normalized_request_id = self._require_non_empty(request_id, "requestId")
        resolution_key = self._require_non_empty(payload.get("resolutionKey"), "resolutionKey")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise SessionCoreError(
                code="ERR_INTERNAL",
                message="resolve requires result object.",
                status_code=400,
                details={"field": "result"},
            )
        idempotent_payload = {"requestId": normalized_request_id, "result": result}
        idempotent = self._runtime_store.resolve_idempotent_result(
            action_type="requests/resolve",
            key=resolution_key,
            payload=idempotent_payload,
        )
        if idempotent is not None:
            return idempotent

        pending = self._runtime_store.get_pending_server_request(request_id=normalized_request_id)
        if pending is None:
            raise SessionCoreError(
                code="ERR_REQUEST_STALE",
                message=f"Request {normalized_request_id} is not pending.",
                status_code=409,
                details={"requestId": normalized_request_id},
            )
        status = str(pending.get("status") or "")
        if status not in {"pending", "submitted"}:
            raise SessionCoreError(
                code="ERR_REQUEST_STALE",
                message=f"Request {normalized_request_id} is no longer active.",
                status_code=409,
                details={"requestId": normalized_request_id, "status": status},
            )
        if status == "submitted":
            raise SessionCoreError(
                code="ERR_REQUEST_STALE",
                message=f"Request {normalized_request_id} is already submitted.",
                status_code=409,
                details={"requestId": normalized_request_id, "status": status},
            )

        raw_request_id = self._runtime_store.pending_server_request_raw_id(request_id=normalized_request_id)
        self._protocol_client.respond_to_server_request(raw_request_id, result)
        self._runtime_store.mark_pending_server_request_submitted(
            request_id=normalized_request_id,
            submission_kind="resolve",
        )
        response = {"status": "accepted"}
        self._runtime_store.record_idempotent_result(
            action_type="requests/resolve",
            key=resolution_key,
            payload=idempotent_payload,
            response=response,
            thread_id=str(pending.get("threadId") or ""),
            turn_id=self._optional_non_empty_str(pending.get("turnId")),
            request_id=normalized_request_id,
        )
        return response

    def request_reject(self, *, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        normalized_request_id = self._require_non_empty(request_id, "requestId")
        resolution_key = self._require_non_empty(payload.get("resolutionKey"), "resolutionKey")
        reason = str(payload.get("reason") or "").strip()
        idempotent_payload = {"requestId": normalized_request_id, "reason": reason}
        idempotent = self._runtime_store.resolve_idempotent_result(
            action_type="requests/reject",
            key=resolution_key,
            payload=idempotent_payload,
        )
        if idempotent is not None:
            return idempotent

        pending = self._runtime_store.get_pending_server_request(request_id=normalized_request_id)
        if pending is None:
            raise SessionCoreError(
                code="ERR_REQUEST_STALE",
                message=f"Request {normalized_request_id} is not pending.",
                status_code=409,
                details={"requestId": normalized_request_id},
            )
        status = str(pending.get("status") or "")
        if status not in {"pending", "submitted"}:
            raise SessionCoreError(
                code="ERR_REQUEST_STALE",
                message=f"Request {normalized_request_id} is no longer active.",
                status_code=409,
                details={"requestId": normalized_request_id, "status": status},
            )
        if status == "submitted":
            raise SessionCoreError(
                code="ERR_REQUEST_STALE",
                message=f"Request {normalized_request_id} is already submitted.",
                status_code=409,
                details={"requestId": normalized_request_id, "status": status},
            )

        raw_request_id = self._runtime_store.pending_server_request_raw_id(request_id=normalized_request_id)
        self._protocol_client.fail_server_request(
            raw_request_id,
            {
                "code": -32000,
                "message": reason or "Server request rejected by client.",
            },
        )
        self._runtime_store.mark_pending_server_request_submitted(
            request_id=normalized_request_id,
            submission_kind="reject",
        )
        response = {"status": "accepted"}
        self._runtime_store.record_idempotent_result(
            action_type="requests/reject",
            key=resolution_key,
            payload=idempotent_payload,
            response=response,
            thread_id=str(pending.get("threadId") or ""),
            turn_id=self._optional_non_empty_str(pending.get("turnId")),
            request_id=normalized_request_id,
        )
        return response

    # ------------------------------------------------------------------
    # Event stream
    # ------------------------------------------------------------------
    def open_event_stream(self, *, thread_id: str, cursor: str | None) -> dict[str, Any]:
        self._ensure_initialized()
        cursor_value = self._runtime_store.parse_cursor(thread_id=thread_id, cursor=cursor)
        replay_events = self._runtime_store.replay_events(thread_id=thread_id, cursor_value=cursor_value)
        subscriber_id = self._runtime_store.subscribe_thread_events(thread_id=thread_id)
        return {
            "cursorValue": cursor_value,
            "replayEvents": replay_events,
            "subscriberId": subscriber_id,
        }

    def read_stream_event(self, *, subscriber_id: str, timeout_sec: float) -> dict[str, Any] | None:
        return self._runtime_store.read_subscriber_event(subscriber_id=subscriber_id, timeout_sec=timeout_sec)

    def close_event_stream(self, *, subscriber_id: str) -> None:
        self._runtime_store.unsubscribe(subscriber_id=subscriber_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_initialized(self) -> None:
        if self._connection_state_machine.phase != "initialized":
            raise SessionCoreError(
                code="ERR_SESSION_NOT_INITIALIZED",
                message="Session has not completed initialize/initialized handshake.",
                status_code=409,
                details={},
            )

    def _on_notification(self, method: str, params: dict[str, Any]) -> None:
        try:
            self._runtime_store.append_notification(method=method, params=params)
        except Exception:
            logger.debug("session_core_v2 notification ingest failed", exc_info=True)

    def _on_server_request(self, raw_request_id: Any, method: str, params: dict[str, Any]) -> None:
        try:
            if self._connection_state_machine.phase != "initialized":
                self._protocol_client.fail_server_request(
                    raw_request_id,
                    {"code": -32002, "message": "Session Core V2 is not initialized."},
                )
                return
            if method not in _SERVER_REQUEST_METHODS:
                self._protocol_client.fail_server_request(
                    raw_request_id,
                    {"code": -32601, "message": f"Unsupported server request method: {method}"},
                )
                return
            thread_id = str(params.get("threadId") or "").strip()
            if not thread_id:
                self._protocol_client.fail_server_request(
                    raw_request_id,
                    {"code": -32602, "message": "Server request is missing threadId."},
                )
                return
            incoming_turn_id = self._optional_non_empty_str(params.get("turnId"))
            turn_id: str | None = incoming_turn_id
            if method == "mcpServer/elicitation/request":
                turn_id = incoming_turn_id
            elif not turn_id:
                active_turn = self._runtime_store.get_active_turn(thread_id=thread_id)
                if active_turn is not None:
                    turn_id = self._optional_non_empty_str(active_turn.get("id"))
                if not turn_id:
                    self._protocol_client.fail_server_request(
                        raw_request_id,
                        {"code": -32602, "message": "Server request is missing turnId and active turn."},
                    )
                    return
            item_id = str(params.get("itemId") or "").strip() or None
            self._runtime_store.register_pending_server_request(
                raw_request_id=raw_request_id,
                method=method,
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                payload=params,
            )
        except SessionCoreError as exc:
            self._protocol_client.fail_server_request(
                raw_request_id,
                {"code": -32001, "message": exc.message, "data": exc.details},
            )
        except Exception:
            logger.exception("session_core_v2 failed to handle server request")
            self._protocol_client.fail_server_request(
                raw_request_id,
                {"code": -32001, "message": "Session Core V2 rejected server request."},
            )

    @staticmethod
    def _extract_turn_id_from_response(response: dict[str, Any]) -> str:
        turn_id = response.get("turnId")
        if isinstance(turn_id, str) and turn_id.strip():
            return turn_id.strip()
        snake_turn_id = response.get("turn_id")
        if isinstance(snake_turn_id, str) and snake_turn_id.strip():
            return snake_turn_id.strip()
        turn = response.get("turn")
        if isinstance(turn, dict):
            nested = turn.get("id")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return ""

    @staticmethod
    def _merge_turns_for_api(
        *,
        provider_turns: list[dict[str, Any]],
        runtime_turns: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []

        for turn in provider_turns:
            turn_id = str(turn.get("id") or "").strip()
            if not turn_id:
                continue
            normalized = dict(turn)
            if "items" not in normalized or not isinstance(normalized.get("items"), list):
                normalized["items"] = []
            merged[turn_id] = normalized
            order.append(turn_id)

        for turn in runtime_turns:
            turn_id = str(turn.get("id") or "").strip()
            if not turn_id:
                continue
            existing = merged.get(turn_id)
            if existing is None:
                merged[turn_id] = dict(turn)
                order.append(turn_id)
                continue
            provider_items = existing.get("items")
            runtime_items = turn.get("items")
            merged_turn = {**existing, **turn}
            if isinstance(runtime_items, list) and runtime_items:
                merged_turn["items"] = runtime_items
            elif isinstance(provider_items, list):
                merged_turn["items"] = provider_items
            else:
                merged_turn["items"] = []
            merged[turn_id] = merged_turn

        return [merged[turn_id] for turn_id in order if turn_id in merged]

    @staticmethod
    def _to_api_turn(turn: dict[str, Any]) -> dict[str, Any]:
        status = str(turn.get("status") or "inProgress")
        if status == "waitingUserInput":
            status = "inProgress"
        if status == "idle":
            status = "inProgress"
        if status not in {"inProgress", "completed", "failed", "interrupted"}:
            status = "failed"
        payload = {
            "id": str(turn.get("id") or ""),
            "status": status,
            "items": list(turn.get("items") or []),
            "startedAtMs": turn.get("startedAtMs"),
            "completedAtMs": turn.get("completedAtMs"),
            "lastCodexStatus": turn.get("lastCodexStatus"),
        }
        error = turn.get("error")
        if isinstance(error, dict):
            payload["error"] = error
        return payload

    @staticmethod
    def _require_non_empty(value: Any, field_name: str) -> str:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
        raise SessionCoreError(
            code="ERR_INTERNAL",
            message=f"{field_name} is required.",
            status_code=400,
            details={"field": field_name},
        )

    @staticmethod
    def _optional_non_empty_str(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized:
            return normalized
        return None

    @staticmethod
    def _extract_item_metadata(item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            return dict(metadata)
        return {}

    @staticmethod
    def _resolve_context_turn_id(
        *,
        thread_id: str,
        client_action_id: str,
        item: dict[str, Any],
        index: int,
    ) -> str:
        explicit_turn_id = str(item.get("turnId") or "").strip()
        if explicit_turn_id:
            return explicit_turn_id
        item_id = str(item.get("id") or "").strip() or f"ctx-item-{index + 1}"
        # Keep turn ids deterministic to preserve replay/idempotency behavior.
        return f"ctx-{thread_id}-{client_action_id}-{item_id}"
