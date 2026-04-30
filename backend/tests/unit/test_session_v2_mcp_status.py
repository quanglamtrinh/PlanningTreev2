from __future__ import annotations

from typing import Any

from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.protocol import SessionProtocolClientV2
from backend.session_core_v2.storage import RuntimeStoreV2


class _FakeTransport:
    def __init__(self) -> None:
        self.notification_handler = None
        self.server_request_handler = None
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def set_notification_handler(self, handler) -> None:  # noqa: ANN001
        self.notification_handler = handler

    def set_server_request_handler(self, handler) -> None:  # noqa: ANN001
        self.server_request_handler = handler

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: int | None = None) -> dict[str, Any]:
        del timeout_sec
        payload = params or {}
        self.requests.append((method, payload))
        if method == "mcpServerStatus/list":
            return {"servers": [{"serverId": "fs", "state": "ready"}], "nextCursor": "cursor-1"}
        return {}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        del method, params


class _FakeMcpService:
    def runtime_state_for_hash(self, mcp_config_hash: str | None = None) -> dict[str, Any]:
        del mcp_config_hash
        return {
            "activeRuntimeMcpConfigHash": "sha256:runtime",
            "activeTurns": [
                {"threadId": "thread-1", "turnId": "turn-1", "mcpConfigHash": "sha256:a"},
                {"threadId": "thread-2", "turnId": "turn-2", "mcpConfigHash": "sha256:a"},
            ],
            "conflict": True,
        }


def test_mcp_server_status_list_augments_thread_scoped_runtime() -> None:
    transport = _FakeTransport()
    protocol = SessionProtocolClientV2(transport)  # type: ignore[arg-type]
    state_machine = ConnectionStateMachine()
    state_machine.set_connecting()
    state_machine.set_initialized(client_name="PlanningTree", server_version="1.0.0")
    manager = SessionManagerV2(
        protocol_client=protocol,
        runtime_store=RuntimeStoreV2(),
        connection_state_machine=state_machine,
        mcp_service=_FakeMcpService(),
    )

    response = manager.mcp_server_status_list(thread_id="thread-2", payload={"limit": 10})

    assert transport.requests == [("mcpServerStatus/list", {"limit": 10})]
    assert response["servers"] == [{"serverId": "fs", "state": "ready"}]
    assert response["nextCursor"] == "cursor-1"
    assert response["threadId"] == "thread-2"
    assert response["runtime"] == {
        "activeRuntimeMcpConfigHash": "sha256:runtime",
        "activeTurns": [{"threadId": "thread-2", "turnId": "turn-2", "mcpConfigHash": "sha256:a"}],
        "threadHasActiveTurn": True,
        "conflict": True,
    }
