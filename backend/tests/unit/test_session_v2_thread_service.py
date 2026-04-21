from __future__ import annotations

from typing import Any

from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.threads.service import ThreadServiceV2


class _FakeProtocolClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def thread_turns_list(self, thread_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"threadId": thread_id}
        payload.update(params or {})
        self.calls.append(("thread/turns/list", payload))
        raise SessionCoreError(
            code="ERR_PROVIDER_UNAVAILABLE",
            message="Invalid request: unknown variant `thread/turns/list`",
            status_code=502,
            details={"rpcCode": -32600, "rpcData": None},
        )

    def thread_read(self, thread_id: str, include_turns: bool) -> dict[str, Any]:
        self.calls.append(("thread/read", {"threadId": thread_id, "includeTurns": include_turns}))
        return {
            "thread": {
                "id": thread_id,
                "turns": [
                    {"id": "turn-1", "status": "completed", "items": []},
                    {"id": "turn-2", "status": "failed", "items": []},
                    {"id": "turn-3", "status": "interrupted", "items": []},
                ],
            }
        }


class _FakeLogger:
    def info(self, _message: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        del args, kwargs


def test_thread_turns_list_falls_back_to_thread_read_when_method_is_unsupported() -> None:
    protocol = _FakeProtocolClient()
    service = ThreadServiceV2(protocol, logger=_FakeLogger())

    response = service.thread_turns_list(thread_id="thread-1", params={"cursor": "1", "limit": 2})

    assert response["data"] == [
        {"id": "turn-2", "status": "failed", "items": []},
        {"id": "turn-3", "status": "interrupted", "items": []},
    ]
    assert response["nextCursor"] is None
    assert protocol.calls == [
        ("thread/turns/list", {"threadId": "thread-1", "cursor": "1", "limit": 2}),
        ("thread/read", {"threadId": "thread-1", "includeTurns": True}),
    ]

