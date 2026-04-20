from __future__ import annotations

from typing import Any

from backend.session_core_v2.protocol.client import SessionProtocolClientV2


class _FakeTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.notification_handler = None

    def set_notification_handler(self, handler) -> None:  # noqa: ANN001
        self.notification_handler = handler

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
    client.thread_list({"sourceKinds": ["appServer"], "modelProviders": ["openai"]})
    client.thread_read("thread-1", include_turns=True)

    assert transport.requests[0][0] == "initialize"
    assert transport.requests[0][1]["clientInfo"]["name"] == "PlanningTree"
    assert transport.requests[0][1]["capabilities"]["experimentalApi"] is True
    assert transport.requests[0][1]["capabilities"]["optOutNotificationMethods"] == ["thread/started"]
    assert transport.notifications == [("initialized", {})]

    assert transport.requests[1] == ("thread/start", {"modelProvider": "openai", "approvalPolicy": "never"})
    assert transport.requests[2][0] == "thread/resume"
    assert transport.requests[2][1]["threadId"] == "thread-1"
    assert transport.requests[2][1]["modelProvider"] == "openai"
    assert transport.requests[3][0] == "thread/list"
    assert transport.requests[3][1]["sourceKinds"] == ["appServer"]
    assert transport.requests[4] == (
        "thread/read",
        {"threadId": "thread-1", "includeTurns": True},
    )

