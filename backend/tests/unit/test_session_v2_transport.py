from __future__ import annotations

import queue
import threading
import time
from typing import Any

from backend.session_core_v2.transport.stdio_jsonrpc import StdioJsonRpcTransportV2


def _capture_writes(transport: StdioJsonRpcTransportV2) -> list[dict[str, Any]]:
    writes: list[dict[str, Any]] = []
    transport.start = lambda: None  # type: ignore[method-assign]
    transport._write_json = lambda payload: writes.append(payload)  # type: ignore[method-assign] # noqa: SLF001
    return writes


def _prepare_server_request_queue(transport: StdioJsonRpcTransportV2, *, capacity: int) -> None:
    transport._server_request_queue = queue.Queue(maxsize=capacity)  # type: ignore[attr-defined] # noqa: SLF001
    transport._server_request_worker_stop.clear()  # type: ignore[attr-defined] # noqa: SLF001


def _start_worker(transport: StdioJsonRpcTransportV2) -> threading.Thread:
    worker = threading.Thread(target=transport._server_request_loop, daemon=True)  # type: ignore[attr-defined] # noqa: SLF001
    worker.start()
    return worker


def test_transport_server_request_dispatches_from_queue_without_auto_ack() -> None:
    transport = StdioJsonRpcTransportV2(codex_cmd="codex", server_request_queue_capacity=4)
    writes = _capture_writes(transport)
    _prepare_server_request_queue(transport, capacity=4)
    seen: list[tuple[Any, str, dict[str, Any]]] = []
    transport.set_server_request_handler(lambda raw_id, method, params: seen.append((raw_id, method, params)))

    transport._handle_incoming_message(  # type: ignore[attr-defined] # noqa: SLF001
        {
            "jsonrpc": "2.0",
            "id": 77,
            "method": "item/tool/requestUserInput",
            "params": {"threadId": "thread-1", "turnId": "turn-1"},
        }
    )
    worker = _start_worker(transport)
    transport._handle_incoming_message(  # type: ignore[attr-defined] # noqa: SLF001
        {
            "jsonrpc": "2.0",
            "id": 78,
            "method": "item/fileChange/requestApproval",
            "params": {"threadId": "thread-1", "turnId": "turn-1"},
        }
    )
    deadline = time.time() + 1.0
    while len(seen) < 2 and time.time() < deadline:
        time.sleep(0.01)
    transport._server_request_worker_stop.set()  # type: ignore[attr-defined] # noqa: SLF001
    worker.join(timeout=1.0)

    assert seen == [
        (77, "item/tool/requestUserInput", {"threadId": "thread-1", "turnId": "turn-1"}),
        (78, "item/fileChange/requestApproval", {"threadId": "thread-1", "turnId": "turn-1"}),
    ]
    assert writes == []


def test_transport_server_request_queue_full_rejects_with_overload() -> None:
    transport = StdioJsonRpcTransportV2(codex_cmd="codex", server_request_queue_capacity=1)
    writes = _capture_writes(transport)
    _prepare_server_request_queue(transport, capacity=1)

    transport._handle_incoming_message(  # type: ignore[attr-defined] # noqa: SLF001
        {
            "jsonrpc": "2.0",
            "id": 88,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thread-1"},
        }
    )
    transport._handle_incoming_message(  # type: ignore[attr-defined] # noqa: SLF001
        {
            "jsonrpc": "2.0",
            "id": 89,
            "method": "item/tool/requestUserInput",
            "params": {"threadId": "thread-1"},
        }
    )

    assert len(writes) == 1
    assert writes[0]["id"] == 89
    assert writes[0]["error"]["code"] == -32001
    assert "queue is full" in writes[0]["error"]["message"].lower()
    request_queue = transport._server_request_queue  # type: ignore[attr-defined] # noqa: SLF001
    assert request_queue is not None
    assert request_queue.qsize() == 1


def test_transport_server_request_handler_failure_is_rejected() -> None:
    transport = StdioJsonRpcTransportV2(codex_cmd="codex", server_request_queue_capacity=4)
    writes = _capture_writes(transport)
    _prepare_server_request_queue(transport, capacity=4)

    def _raise(*_: Any, **__: Any) -> None:
        raise RuntimeError("boom")

    transport.set_server_request_handler(_raise)
    worker = _start_worker(transport)
    transport._handle_incoming_message(  # type: ignore[attr-defined] # noqa: SLF001
        {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "item/fileChange/requestApproval",
            "params": {"threadId": "thread-1"},
        }
    )
    deadline = time.time() + 1.0
    while not writes and time.time() < deadline:
        time.sleep(0.01)
    transport._server_request_worker_stop.set()  # type: ignore[attr-defined] # noqa: SLF001
    worker.join(timeout=1.0)

    assert len(writes) == 1
    assert writes[0]["id"] == "req-1"
    assert writes[0]["error"]["code"] == -32001


def test_transport_server_request_without_handler_is_rejected() -> None:
    transport = StdioJsonRpcTransportV2(codex_cmd="codex", server_request_queue_capacity=4)
    writes = _capture_writes(transport)
    _prepare_server_request_queue(transport, capacity=4)
    worker = _start_worker(transport)

    transport._handle_incoming_message(  # type: ignore[attr-defined] # noqa: SLF001
        {
            "jsonrpc": "2.0",
            "id": 188,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thread-1"},
        }
    )
    deadline = time.time() + 1.0
    while not writes and time.time() < deadline:
        time.sleep(0.01)
    transport._server_request_worker_stop.set()  # type: ignore[attr-defined] # noqa: SLF001
    worker.join(timeout=1.0)

    assert len(writes) == 1
    assert writes[0]["id"] == 188
    assert writes[0]["error"]["code"] == -32001


def test_transport_shutdown_drains_and_rejects_queued_requests() -> None:
    transport = StdioJsonRpcTransportV2(codex_cmd="codex", server_request_queue_capacity=4)
    writes = _capture_writes(transport)
    _prepare_server_request_queue(transport, capacity=4)

    transport._enqueue_server_request(  # type: ignore[attr-defined] # noqa: SLF001
        request_id=901,
        method="item/tool/requestUserInput",
        params={"threadId": "thread-1"},
    )
    transport._enqueue_server_request(  # type: ignore[attr-defined] # noqa: SLF001
        request_id=902,
        method="item/fileChange/requestApproval",
        params={"threadId": "thread-1"},
    )

    transport._stop_server_request_worker(  # type: ignore[attr-defined] # noqa: SLF001
        reject_pending=True,
        error_code=-32001,
        error_message="Session Core V2 transport shutting down.",
    )

    assert [entry["id"] for entry in writes] == [901, 902]
    assert all(entry["error"]["code"] == -32001 for entry in writes)


def test_transport_respond_and_reject_payload_shape() -> None:
    transport = StdioJsonRpcTransportV2(codex_cmd="codex")
    writes = _capture_writes(transport)

    transport.respond_to_server_request(12, {"decision": "accept"})
    transport.fail_server_request(13, {"code": -32000, "message": "declined", "data": {"reason": "policy"}})

    assert writes[0] == {"jsonrpc": "2.0", "id": 12, "result": {"decision": "accept"}}
    assert writes[1]["jsonrpc"] == "2.0"
    assert writes[1]["id"] == 13
    assert writes[1]["error"]["code"] == -32000
    assert writes[1]["error"]["message"] == "declined"
    assert writes[1]["error"]["data"] == {"reason": "policy"}
