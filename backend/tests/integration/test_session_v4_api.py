from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.protocol import SessionProtocolClientV2
from backend.session_core_v2.storage import RuntimeStoreV2


@pytest.fixture
def data_root() -> Path:
    root = Path("pytest_tmp_dir") / "session_v4_api" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


class _FakeTransport:
    def __init__(
        self,
        *,
        responses: dict[str, dict[str, Any]] | None = None,
        failures: dict[str, SessionCoreError] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.failures = failures or {}
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.notification_handler = None
        self.server_request_handler = None
        self.server_request_responses: list[tuple[Any, dict[str, Any]]] = []
        self.server_request_failures: list[tuple[Any, dict[str, Any]]] = []

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
        if method in self.failures:
            raise self.failures[method]
        return self.responses.get(method, {})

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.notifications.append((method, params or {}))

    def respond_to_server_request(self, request_id: Any, result: dict[str, Any] | None = None) -> None:
        self.server_request_responses.append((request_id, result or {}))

    def fail_server_request(self, request_id: Any, error: dict[str, Any] | None = None) -> None:
        self.server_request_failures.append((request_id, error or {}))

    def emit_notification(self, method: str, params: dict[str, Any]) -> None:
        if self.notification_handler is not None:
            self.notification_handler(method, params)

    def emit_server_request(self, raw_request_id: Any, method: str, params: dict[str, Any]) -> None:
        if self.server_request_handler is not None:
            self.server_request_handler(raw_request_id, method, params)


def _fake_thread(thread_id: str) -> dict[str, Any]:
    return {
        "id": thread_id,
        "name": None,
        "preview": None,
        "path": None,
        "cwd": "C:/repo/workspace",
        "modelProvider": "openai",
        "status": {"type": "idle"},
        "turns": [],
        "createdAt": 1,
        "updatedAt": 1,
    }


def _install_fake_manager(client: TestClient, fake_transport: _FakeTransport) -> None:
    protocol = SessionProtocolClientV2(fake_transport)  # type: ignore[arg-type]
    manager = SessionManagerV2(
        protocol_client=protocol,
        runtime_store=RuntimeStoreV2(),
        connection_state_machine=ConnectionStateMachine(),
    )
    client.app.state.session_manager_v2 = manager


def _openapi_schema() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    path = root / "docs" / "remodel" / "contracts" / "session-core-v2" / "s3-session-http-api-v1.openapi.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _resolve_ref(schema_doc: dict[str, Any], ref: str) -> dict[str, Any]:
    assert ref.startswith("#/")
    current: Any = schema_doc
    for part in ref[2:].split("/"):
        current = current[part]
    assert isinstance(current, dict)
    return current


def _assert_schema(instance: Any, schema: dict[str, Any], schema_doc: dict[str, Any]) -> None:
    if "$ref" in schema:
        _assert_schema(instance, _resolve_ref(schema_doc, schema["$ref"]), schema_doc)
        return

    if "allOf" in schema:
        for sub in schema["allOf"]:
            _assert_schema(instance, sub, schema_doc)
        return

    if "oneOf" in schema:
        errors: list[AssertionError] = []
        for candidate in schema["oneOf"]:
            try:
                _assert_schema(instance, candidate, schema_doc)
                return
            except AssertionError as exc:  # pragma: no cover - diagnostics only
                errors.append(exc)
        raise AssertionError(f"oneOf validation failed for value={instance!r}; errors={errors!r}")

    if "const" in schema:
        assert instance == schema["const"]

    if "enum" in schema:
        assert instance in schema["enum"]

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if instance is None and "null" in schema_type:
            return
        non_null_types = [value for value in schema_type if value != "null"]
        assert non_null_types, f"invalid schema type list: {schema_type}"
        schema_type = non_null_types[0]

    if schema_type == "object":
        assert isinstance(instance, dict), f"expected object, got {type(instance)}"
        required = schema.get("required", [])
        for key in required:
            assert key in instance, f"missing required key {key!r}"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert set(instance).issubset(set(properties)), (
                f"unexpected keys: {set(instance) - set(properties)}"
            )
        for key, prop_schema in properties.items():
            if key in instance:
                _assert_schema(instance[key], prop_schema, schema_doc)
        return

    if schema_type == "array":
        assert isinstance(instance, list), f"expected array, got {type(instance)}"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for item in instance:
                _assert_schema(item, item_schema, schema_doc)
        return

    if schema_type == "string":
        assert isinstance(instance, str), f"expected string, got {type(instance)}"
        min_length = schema.get("minLength")
        if isinstance(min_length, int):
            assert len(instance) >= min_length
        return

    if schema_type == "boolean":
        assert isinstance(instance, bool), f"expected boolean, got {type(instance)}"
        return

    if schema_type == "integer":
        assert isinstance(instance, int) and not isinstance(
            instance, bool
        ), f"expected integer, got {type(instance)}"
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int):
            assert instance >= minimum
        if isinstance(maximum, int):
            assert instance <= maximum
        return


def _assert_component(instance: Any, component_name: str, schema_doc: dict[str, Any]) -> None:
    schema = schema_doc["components"]["schemas"][component_name]
    _assert_schema(instance, schema, schema_doc)


def test_session_v4_roundtrip_and_guard(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "thread/start": {"thread": _fake_thread("thread-start-1"), "modelProvider": "openai"},
            "thread/resume": {"thread": _fake_thread("thread-resume-1"), "modelProvider": "openai"},
            "thread/list": {"data": [_fake_thread("thread-list-1")], "nextCursor": None},
            "thread/read": {"thread": _fake_thread("thread-read-1")},
            "thread/fork": {"thread": _fake_thread("thread-fork-1"), "modelProvider": "openai"},
            "thread/turns/list": {"data": [{"id": "turn-1", "status": "completed", "items": []}], "nextCursor": None},
            "thread/loaded/list": {"data": ["thread-resume-1"], "nextCursor": None},
            "thread/unsubscribe": {"status": "unsubscribed"},
            "model/list": {
                "data": [
                    {
                        "id": "model-1",
                        "model": "gpt-5.4",
                        "displayName": "GPT-5.4",
                        "description": "Default model",
                        "hidden": False,
                        "isDefault": True,
                    }
                ],
                "nextCursor": None,
            },
        }
    )
    _install_fake_manager(client, fake_transport)

    pre_init = client.post("/v4/session/threads/start", json={})
    assert pre_init.status_code == 409
    assert pre_init.json()["error"]["code"] == "ERR_SESSION_NOT_INITIALIZED"

    init_response = client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    )
    assert init_response.status_code == 200
    assert init_response.json()["data"]["connection"]["phase"] == "initialized"

    status_response = client.get("/v4/session/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"]["connection"]["phase"] == "initialized"

    start_response = client.post("/v4/session/threads/start", json={"modelProvider": "openai"})
    assert start_response.status_code == 200
    assert start_response.json()["data"]["thread"]["id"] == "thread-start-1"

    resume_response = client.post("/v4/session/threads/thread-resume-1/resume", json={"cwd": "C:/repo/workspace"})
    assert resume_response.status_code == 200
    assert resume_response.json()["data"]["thread"]["id"] == "thread-resume-1"

    list_response = client.get("/v4/session/threads/list?modelProviders=openai&sourceKinds=appServer")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["data"][0]["id"] == "thread-list-1"

    read_response = client.get("/v4/session/threads/thread-read-1/read?includeTurns=false")
    assert read_response.status_code == 200
    assert read_response.json()["data"]["thread"]["id"] == "thread-read-1"

    fork_response = client.post("/v4/session/threads/thread-resume-1/fork", json={})
    assert fork_response.status_code == 200
    assert fork_response.json()["data"]["thread"]["id"] == "thread-fork-1"

    turns_response = client.get("/v4/session/threads/thread-read-1/turns?cursor=c1&limit=10")
    assert turns_response.status_code == 200
    assert turns_response.json()["data"]["data"][0]["id"] == "turn-1"

    loaded_response = client.get("/v4/session/threads/loaded/list?cursor=c0&limit=10")
    assert loaded_response.status_code == 200
    assert loaded_response.json()["data"]["data"] == ["thread-resume-1"]

    unsubscribe_response = client.post("/v4/session/threads/thread-read-1/unsubscribe")
    assert unsubscribe_response.status_code == 200
    assert unsubscribe_response.json()["data"]["status"] == "unsubscribed"

    models_response = client.get("/v4/session/models/list?limit=25&includeHidden=false")
    assert models_response.status_code == 200
    assert models_response.json()["data"]["data"][0]["model"] == "gpt-5.4"

    assert [method for method, _ in fake_transport.requests] == [
        "initialize",
        "thread/start",
        "thread/resume",
        "thread/list",
        "thread/read",
        "thread/fork",
        "thread/turns/list",
        "thread/loaded/list",
        "thread/unsubscribe",
        "model/list",
    ]
    assert fake_transport.notifications == [("initialized", {})]


def test_session_v4_turn_runtime_and_idempotency(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {"turnId": "turn-start-1"},
            "turn/steer": {"turnId": "turn-start-1"},
            "turn/interrupt": {},
        }
    )
    _install_fake_manager(client, fake_transport)

    init_response = client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    )
    assert init_response.status_code == 200

    start_payload = {
        "clientActionId": "start-1",
        "input": [{"type": "text", "text": "hello"}],
    }
    start_response = client.post("/v4/session/threads/thread-1/turns/start", json=start_payload)
    assert start_response.status_code == 200
    assert start_response.json()["data"]["turn"]["id"] == "turn-start-1"
    assert start_response.json()["data"]["turn"]["status"] == "inProgress"

    duplicate_start_response = client.post("/v4/session/threads/thread-1/turns/start", json=start_payload)
    assert duplicate_start_response.status_code == 200
    assert duplicate_start_response.json()["data"]["turn"]["id"] == "turn-start-1"

    request_methods = [method for method, _ in fake_transport.requests]
    assert request_methods.count("turn/start") == 1

    steer_response = client.post(
        "/v4/session/threads/thread-1/turns/turn-start-1/steer",
        json={
            "clientActionId": "steer-1",
            "expectedTurnId": "turn-start-1",
            "input": [{"type": "text", "text": "continue"}],
        },
    )
    assert steer_response.status_code == 200

    mismatch_response = client.post(
        "/v4/session/threads/thread-1/turns/turn-start-1/steer",
        json={
            "clientActionId": "steer-2",
            "expectedTurnId": "turn-other",
            "input": [{"type": "text", "text": "bad"}],
        },
    )
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["error"]["code"] == "ERR_ACTIVE_TURN_MISMATCH"

    interrupt_response = client.post(
        "/v4/session/threads/thread-1/turns/turn-start-1/interrupt",
        json={"clientActionId": "interrupt-1"},
    )
    assert interrupt_response.status_code == 200


def test_session_v4_pending_requests_lists_all_phase3_methods(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {"turnId": "turn-start-1"},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post("/v4/session/initialize", json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}}).status_code == 200
    assert client.post(
        "/v4/session/threads/thread-1/turns/start",
        json={"clientActionId": "start-1", "input": [{"type": "text", "text": "hello"}]},
    ).status_code == 200

    methods = [
        "item/tool/requestUserInput",
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
        "item/permissions/requestApproval",
        "mcpServer/elicitation/request",
    ]
    for index, method in enumerate(methods):
        fake_transport.emit_server_request(
            index + 1,
            method,
            {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": f"item-{index}"},
        )

    pending_response = client.get("/v4/session/requests/pending")
    assert pending_response.status_code == 200
    pending_rows = pending_response.json()["data"]["data"]
    assert len(pending_rows) == 5
    assert {row["method"] for row in pending_rows} == set(methods)


def test_session_v4_mcp_pending_request_allows_null_turn_id(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post("/v4/session/initialize", json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}}).status_code == 200

    fake_transport.emit_server_request(
        707,
        "mcpServer/elicitation/request",
        {"threadId": "thread-1", "itemId": "mcp-1", "turnId": None},
    )

    pending_response = client.get("/v4/session/requests/pending")
    assert pending_response.status_code == 200
    rows = pending_response.json()["data"]["data"]
    assert len(rows) == 1
    assert rows[0]["method"] == "mcpServer/elicitation/request"
    assert rows[0]["turnId"] is None
    assert fake_transport.server_request_failures == []


def test_session_v4_missing_turn_id_fallback_and_validation(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {"turnId": "turn-start-1"},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post("/v4/session/initialize", json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}}).status_code == 200
    assert client.post(
        "/v4/session/threads/thread-1/turns/start",
        json={"clientActionId": "start-1", "input": [{"type": "text", "text": "hello"}]},
    ).status_code == 200

    fake_transport.emit_server_request(
        808,
        "item/commandExecution/requestApproval",
        {"threadId": "thread-1", "itemId": "cmd-1"},
    )
    pending_rows = client.get("/v4/session/requests/pending").json()["data"]["data"]
    assert len(pending_rows) == 1
    assert pending_rows[0]["turnId"] == "turn-start-1"

    fake_transport.emit_server_request(
        809,
        "item/fileChange/requestApproval",
        {"threadId": "thread-2", "itemId": "file-1"},
    )
    pending_after = client.get("/v4/session/requests/pending").json()["data"]["data"]
    assert len(pending_after) == 1
    assert pending_after[0]["threadId"] == "thread-1"
    assert fake_transport.server_request_failures[-1][0] == 809
    assert fake_transport.server_request_failures[-1][1]["code"] == -32602


def test_session_v4_request_lifecycle_resolve_reject_cleanup_and_ordering(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {"turnId": "turn-start-1"},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post("/v4/session/initialize", json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}}).status_code == 200
    assert client.post(
        "/v4/session/threads/thread-1/turns/start",
        json={"clientActionId": "start-1", "input": [{"type": "text", "text": "hello"}]},
    ).status_code == 200

    fake_transport.emit_server_request(
        101,
        "item/tool/requestUserInput",
        {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": "item-1"},
    )
    pending_payload = client.get("/v4/session/requests/pending").json()
    resolve_request_id = pending_payload["data"]["data"][0]["requestId"]
    journal_after_create = client.app.state.session_manager_v2._runtime_store.read_thread_journal("thread-1")  # noqa: SLF001
    created_events = [event for event in journal_after_create if event["method"] == "serverRequest/created"]
    assert len(created_events) == 1
    assert created_events[0]["params"]["request"]["requestId"] == resolve_request_id
    assert created_events[0]["params"]["request"]["status"] == "pending"

    resolve_response = client.post(
        f"/v4/session/requests/{resolve_request_id}/resolve",
        json={"resolutionKey": "resolve-1", "result": {"decision": "accept"}},
    )
    assert resolve_response.status_code == 200
    assert fake_transport.server_request_responses[-1] == (101, {"decision": "accept"})
    journal_after_submit = client.app.state.session_manager_v2._runtime_store.read_thread_journal("thread-1")  # noqa: SLF001
    submitted_events = [event for event in journal_after_submit if event["method"] == "serverRequest/updated"]
    assert len(submitted_events) == 1
    assert submitted_events[0]["params"]["request"]["requestId"] == resolve_request_id
    assert submitted_events[0]["params"]["request"]["status"] == "submitted"

    fake_transport.emit_notification("serverRequest/resolved", {"threadId": "thread-1", "requestId": 101})
    fake_transport.emit_notification(
        "turn/completed",
        {"threadId": "thread-1", "turn": {"id": "turn-start-1", "status": "completed", "items": []}},
    )
    after_resolve = client.get("/v4/session/requests/pending").json()
    assert after_resolve["data"]["data"] == []

    journal = client.app.state.session_manager_v2._runtime_store.read_thread_journal("thread-1")  # noqa: SLF001
    methods = [event["method"] for event in journal]
    assert methods.index("serverRequest/resolved") < methods.index("turn/completed")
    resolved_event = next(event for event in journal if event["method"] == "serverRequest/resolved")
    assert resolved_event["params"]["request"]["requestId"] == resolve_request_id
    assert resolved_event["params"]["request"]["status"] == "resolved"

    fake_transport.emit_server_request(
        202,
        "item/commandExecution/requestApproval",
        {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": "item-2"},
    )
    reject_pending = client.get("/v4/session/requests/pending").json()["data"]["data"]
    reject_request_id = reject_pending[0]["requestId"]
    reject_response = client.post(
        f"/v4/session/requests/{reject_request_id}/reject",
        json={"resolutionKey": "reject-1", "reason": "policy"},
    )
    assert reject_response.status_code == 200
    assert fake_transport.server_request_failures[-1][0] == 202
    assert fake_transport.server_request_failures[-1][1]["message"] == "policy"
    fake_transport.emit_notification("serverRequest/resolved", {"threadId": "thread-1", "requestId": 202})
    assert client.get("/v4/session/requests/pending").json()["data"]["data"] == []
    journal_after_reject = client.app.state.session_manager_v2._runtime_store.read_thread_journal("thread-1")  # noqa: SLF001
    reject_resolved = [
        event
        for event in journal_after_reject
        if event["method"] == "serverRequest/resolved"
        and event.get("params", {}).get("request", {}).get("requestId") == reject_request_id
    ]
    assert reject_resolved[-1]["params"]["request"]["status"] == "rejected"

    fake_transport.emit_server_request(
        303,
        "item/fileChange/requestApproval",
        {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": "item-3"},
    )
    cleanup_pending = client.get("/v4/session/requests/pending").json()["data"]["data"]
    cleanup_request_id = cleanup_pending[0]["requestId"]
    fake_transport.emit_notification("serverRequest/resolved", {"threadId": "thread-1", "requestId": 303})
    stale_response = client.post(
        f"/v4/session/requests/{cleanup_request_id}/resolve",
        json={"resolutionKey": "resolve-stale", "result": {"decision": "accept"}},
    )
    assert stale_response.status_code == 409
    assert stale_response.json()["error"]["code"] == "ERR_REQUEST_STALE"
    journal_after_expire = client.app.state.session_manager_v2._runtime_store.read_thread_journal("thread-1")  # noqa: SLF001
    expired_resolved = [
        event
        for event in journal_after_expire
        if event["method"] == "serverRequest/resolved"
        and event.get("params", {}).get("request", {}).get("requestId") == cleanup_request_id
    ]
    assert expired_resolved[-1]["params"]["request"]["status"] == "expired"


def test_session_v4_request_resolution_idempotency(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {"turnId": "turn-start-1"},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post("/v4/session/initialize", json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}}).status_code == 200
    assert client.post(
        "/v4/session/threads/thread-1/turns/start",
        json={"clientActionId": "start-1", "input": [{"type": "text", "text": "hello"}]},
    ).status_code == 200

    fake_transport.emit_server_request(
        500,
        "item/permissions/requestApproval",
        {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": "item-5"},
    )
    request_id = client.get("/v4/session/requests/pending").json()["data"]["data"][0]["requestId"]

    payload = {"resolutionKey": "resolve-idem-1", "result": {"decision": "accept"}}
    first = client.post(f"/v4/session/requests/{request_id}/resolve", json=payload)
    second = client.post(f"/v4/session/requests/{request_id}/resolve", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(fake_transport.server_request_responses) == 1

    mismatch = client.post(
        f"/v4/session/requests/{request_id}/resolve",
        json={"resolutionKey": "resolve-idem-1", "result": {"decision": "decline"}},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "ERR_IDEMPOTENCY_PAYLOAD_MISMATCH"

    fake_transport.emit_notification("serverRequest/resolved", {"threadId": "thread-1", "requestId": 500})
    fake_transport.emit_server_request(
        501,
        "item/commandExecution/requestApproval",
        {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": "item-6"},
    )
    reject_request_id = client.get("/v4/session/requests/pending").json()["data"]["data"][0]["requestId"]
    reject_payload = {"resolutionKey": "reject-idem-1", "reason": "policy"}
    reject_first = client.post(f"/v4/session/requests/{reject_request_id}/reject", json=reject_payload)
    reject_second = client.post(f"/v4/session/requests/{reject_request_id}/reject", json=reject_payload)
    assert reject_first.status_code == 200
    assert reject_second.status_code == 200
    assert len(fake_transport.server_request_failures) == 1

    reject_mismatch = client.post(
        f"/v4/session/requests/{reject_request_id}/reject",
        json={"resolutionKey": "reject-idem-1", "reason": "different"},
    )
    assert reject_mismatch.status_code == 409
    assert reject_mismatch.json()["error"]["code"] == "ERR_IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_session_v4_events_stream_replay_format(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
        }
    )
    _install_fake_manager(client, fake_transport)

    init_response = client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    )
    assert init_response.status_code == 200

    fake_transport.emit_notification("thread/started", {"threadId": "thread-stream-1"})
    fake_transport.emit_notification(
        "thread/status/changed",
        {"threadId": "thread-stream-1", "status": {"type": "idle"}},
    )

    manager = client.app.state.session_manager_v2
    original_read_stream_event = manager.read_stream_event
    manager.read_stream_event = lambda **_: None
    try:
        response = client.get("/v4/session/threads/thread-stream-1/events?cursor=0")
    finally:
        manager.read_stream_event = original_read_stream_event

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line]
    assert any(line.startswith("id: ") for line in lines)
    assert any(line.startswith("event: thread/") for line in lines)
    assert any(line.startswith("data: ") for line in lines)


def test_session_v4_feature_flags_gate_turns_and_events(client: TestClient) -> None:
    client.app.state.session_core_v2_enable_turns = False
    client.app.state.session_core_v2_enable_events = False
    client.app.state.session_core_v2_enable_requests = False
    try:
        turn_response = client.post(
            "/v4/session/threads/thread-1/turns/start",
            json={"clientActionId": "start-1", "input": [{"type": "text", "text": "hi"}]},
        )
        assert turn_response.status_code == 501
        assert turn_response.json()["error"]["code"] == "ERR_PHASE_NOT_ENABLED"

        events_response = client.get("/v4/session/threads/thread-1/events")
        assert events_response.status_code == 501
        assert events_response.json()["error"]["code"] == "ERR_PHASE_NOT_ENABLED"

        requests_response = client.get("/v4/session/requests/pending")
        assert requests_response.status_code == 501
        assert requests_response.json()["error"]["code"] == "ERR_PHASE_NOT_ENABLED"
    finally:
        client.app.state.session_core_v2_enable_turns = True
        client.app.state.session_core_v2_enable_events = True
        client.app.state.session_core_v2_enable_requests = True


def test_session_v4_initialize_failure_sets_error_state(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        failures={
            "initialize": SessionCoreError(
                code="ERR_PROVIDER_UNAVAILABLE",
                message="mock disconnect",
                status_code=503,
                details={"reason": "disconnect"},
            )
        }
    )
    _install_fake_manager(client, fake_transport)

    init_response = client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    )
    assert init_response.status_code == 503
    assert init_response.json()["error"]["code"] == "ERR_PROVIDER_UNAVAILABLE"

    status_response = client.get("/v4/session/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"]["connection"]["phase"] == "error"
    assert status_response.json()["data"]["connection"]["error"]["code"] == "ERR_PROVIDER_UNAVAILABLE"


def test_session_v4_contract_conformance_for_phase3_endpoints(client: TestClient) -> None:
    schema_doc = _openapi_schema()
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "thread/start": {"thread": _fake_thread("thread-start-1"), "modelProvider": "openai"},
            "thread/resume": {"thread": _fake_thread("thread-resume-1"), "modelProvider": "openai"},
            "thread/list": {"data": [_fake_thread("thread-list-1")], "nextCursor": None},
            "thread/read": {"thread": _fake_thread("thread-read-1")},
            "turn/start": {"turnId": "turn-start-1"},
            "turn/steer": {"turnId": "turn-start-1"},
            "turn/interrupt": {},
        }
    )
    _install_fake_manager(client, fake_transport)

    init_payload = client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).json()
    status_payload = client.get("/v4/session/status").json()
    start_payload = client.post("/v4/session/threads/start", json={}).json()
    assert ("thread/start", {}) in fake_transport.requests
    resume_payload = client.post("/v4/session/threads/thread-resume-1/resume", json={}).json()
    list_payload = client.get("/v4/session/threads/list").json()
    read_payload = client.get("/v4/session/threads/thread-read-1/read").json()
    turn_start_payload = client.post(
        "/v4/session/threads/thread-1/turns/start",
        json={"clientActionId": "start-1", "input": [{"type": "text", "text": "hi"}]},
    ).json()
    turn_steer_payload = client.post(
        "/v4/session/threads/thread-1/turns/turn-start-1/steer",
        json={
            "clientActionId": "steer-1",
            "expectedTurnId": "turn-start-1",
            "input": [{"type": "text", "text": "continue"}],
        },
    ).json()
    turn_interrupt_payload = client.post(
        "/v4/session/threads/thread-1/turns/turn-start-1/interrupt",
        json={"clientActionId": "interrupt-1"},
    ).json()
    fake_transport.emit_server_request(
        900,
        "item/tool/requestUserInput",
        {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": "item-1"},
    )
    pending_payload = client.get("/v4/session/requests/pending").json()
    request_id = pending_payload["data"]["data"][0]["requestId"]
    resolve_payload = client.post(
        f"/v4/session/requests/{request_id}/resolve",
        json={"resolutionKey": "resolve-contract-1", "result": {"decision": "accept"}},
    ).json()
    fake_transport.emit_notification("serverRequest/resolved", {"threadId": "thread-1", "requestId": 900})
    fake_transport.emit_server_request(
        901,
        "item/commandExecution/requestApproval",
        {"threadId": "thread-1", "turnId": "turn-start-1", "itemId": "item-2"},
    )
    reject_request_id = client.get("/v4/session/requests/pending").json()["data"]["data"][0]["requestId"]
    reject_payload = client.post(
        f"/v4/session/requests/{reject_request_id}/reject",
        json={"resolutionKey": "reject-contract-1", "reason": "policy"},
    ).json()

    _assert_component(init_payload, "InitializeResponseEnvelope", schema_doc)
    _assert_component(status_payload, "ConnectionStatusEnvelope", schema_doc)
    _assert_component(start_payload, "ThreadConfigEnvelope", schema_doc)
    _assert_component(resume_payload, "ThreadConfigEnvelope", schema_doc)
    _assert_component(list_payload, "ThreadListEnvelope", schema_doc)
    _assert_component(read_payload, "ThreadEnvelope", schema_doc)
    _assert_component(turn_start_payload, "TurnEnvelope", schema_doc)
    _assert_component(turn_steer_payload, "TurnEnvelope", schema_doc)
    _assert_component(turn_interrupt_payload, "BasicOkEnvelope", schema_doc)
    _assert_component(pending_payload, "PendingRequestsEnvelope", schema_doc)
    _assert_component(resolve_payload, "BasicOkEnvelope", schema_doc)
    _assert_component(reject_payload, "BasicOkEnvelope", schema_doc)


def test_session_v4_remaining_phase_gated_route_returns_deterministic_501(client: TestClient) -> None:
    response = client.post("/v4/session/threads/thread-1/archive", json={})
    assert response.status_code == 501
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ERR_PHASE_NOT_ENABLED"
