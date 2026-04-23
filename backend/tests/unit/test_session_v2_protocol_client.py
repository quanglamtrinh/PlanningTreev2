from __future__ import annotations

from typing import Any

from backend.session_core_v2.protocol.client import SessionProtocolClientV2


class _FakeTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.server_responses: list[tuple[Any, dict[str, Any]]] = []
        self.server_failures: list[tuple[Any, dict[str, Any]]] = []
        self.notification_handler = None
        self.server_request_handler = None

    def set_notification_handler(self, handler) -> None:  # noqa: ANN001
        self.notification_handler = handler

    def set_server_request_handler(self, handler) -> None:  # noqa: ANN001
        self.server_request_handler = handler

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        del timeout_sec
        payload = params or {}
        self.requests.append((method, payload))
        return {"ok": True}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.notifications.append((method, params or {}))

    def respond_to_server_request(self, request_id: Any, result: dict[str, Any] | None = None) -> None:
        self.server_responses.append((request_id, result or {}))

    def fail_server_request(self, request_id: Any, error: dict[str, Any] | None = None) -> None:
        self.server_failures.append((request_id, error or {}))


def test_protocol_client_mapping_and_camel_case_passthrough() -> None:
    transport = _FakeTransport()
    client = SessionProtocolClientV2(transport)  # type: ignore[arg-type]

    client.initialize(
        {
            "clientInfo": {"name": "PlanningTree", "version": "0.1.0"},
            "capabilities": {"experimentalApi": True, "optOutNotificationMethods": ["thread/started"]},
        }
    )
    client.thread_start({"modelProvider": "openai", "approvalPolicy": "never"})
    client.thread_resume("thread-1", {"modelProvider": "openai", "cwd": "/tmp/work"})
    client.thread_fork("thread-1", {"modelProvider": "openai"})
    client.thread_list({"sourceKinds": ["appServer"], "modelProviders": ["openai"]})
    client.thread_read("thread-1", include_turns=True)
    client.thread_turns_list("thread-1", {"cursor": "c1", "limit": 20})
    client.thread_loaded_list({"cursor": "c0", "limit": 10})
    client.thread_unsubscribe("thread-1")
    client.model_list({"limit": 50, "includeHidden": False})
    client.turn_start(
        "thread-1",
        {
            "clientActionId": "start-1",
            "input": [{"type": "text", "text": "hello"}],
            "approvalPolicy": "onRequest",
        },
    )
    client.turn_steer(
        "thread-1",
        {
            "clientActionId": "steer-1",
            "expectedTurnId": "turn-1",
            "input": [{"type": "text", "text": "continue"}],
        },
    )
    client.turn_interrupt("thread-1", "turn-1")
    client.respond_to_server_request(123, {"decision": "accept"})
    client.fail_server_request(124, {"code": -32000, "message": "rejected"})

    assert transport.requests[0][0] == "initialize"
    assert transport.requests[0][1]["clientInfo"]["name"] == "PlanningTree"
    assert transport.requests[0][1]["capabilities"]["experimentalApi"] is True
    assert transport.requests[0][1]["capabilities"]["optOutNotificationMethods"] == ["thread/started"]
    assert transport.notifications == [("initialized", {})]

    assert transport.requests[1] == ("thread/start", {"modelProvider": "openai", "approvalPolicy": "never"})
    assert transport.requests[2][0] == "thread/resume"
    assert transport.requests[2][1]["threadId"] == "thread-1"
    assert transport.requests[2][1]["modelProvider"] == "openai"
    assert transport.requests[3][0] == "thread/fork"
    assert transport.requests[3][1]["threadId"] == "thread-1"
    assert transport.requests[4][0] == "thread/list"
    assert transport.requests[4][1]["sourceKinds"] == ["appServer"]
    assert transport.requests[5] == (
        "thread/read",
        {"threadId": "thread-1", "includeTurns": True},
    )
    assert transport.requests[6][0] == "thread/turns/list"
    assert transport.requests[6][1]["threadId"] == "thread-1"
    assert transport.requests[7][0] == "thread/loaded/list"
    assert transport.requests[8] == ("thread/unsubscribe", {"threadId": "thread-1"})
    assert transport.requests[9] == ("model/list", {"limit": 50, "includeHidden": False})
    assert transport.requests[10][0] == "turn/start"
    assert transport.requests[10][1]["threadId"] == "thread-1"
    assert transport.requests[10][1]["clientActionId"] == "start-1"
    assert transport.requests[11][0] == "turn/steer"
    assert transport.requests[11][1]["expectedTurnId"] == "turn-1"
    assert transport.requests[12] == ("turn/interrupt", {"threadId": "thread-1", "turnId": "turn-1"})
    assert transport.server_responses == [(123, {"decision": "accept"})]
    assert transport.server_failures == [(124, {"code": -32000, "message": "rejected"})]


def test_protocol_client_wires_server_request_handler() -> None:
    transport = _FakeTransport()
    client = SessionProtocolClientV2(transport)  # type: ignore[arg-type]
    seen: list[tuple[Any, str, dict[str, Any]]] = []

    def _handler(raw_request_id: Any, method: str, params: dict[str, Any]) -> None:
        seen.append((raw_request_id, method, params))

    client.set_server_request_handler(_handler)
    assert transport.server_request_handler is _handler

    transport.server_request_handler(99, "item/tool/requestUserInput", {"threadId": "thread-1"})
    assert seen == [(99, "item/tool/requestUserInput", {"threadId": "thread-1"})]
