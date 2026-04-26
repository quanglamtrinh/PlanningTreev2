from __future__ import annotations

import json
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
from backend.session_core_v2.thread_store import ThreadRolloutRecorder


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


class _EarlyTerminalTransport(_FakeTransport):
    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        if method != "turn/start":
            return super().request(method, params, timeout_sec=timeout_sec)
        del timeout_sec
        payload = params or {}
        self.requests.append((method, payload))
        if method in self.failures:
            raise self.failures[method]
        thread_id = str(payload.get("threadId") or "thread-1")
        turn_id = "turn-early-terminal-1"
        self.emit_notification(
            "turn/completed",
            {
                "threadId": thread_id,
                "turn": {
                    "id": turn_id,
                    "status": "completed",
                    "items": [{"type": "agentMessage", "text": "done before response"}],
                },
            },
        )
        return {"turnId": turn_id}


class _StartedBeforeResponseTransport(_FakeTransport):
    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        if method != "turn/start":
            return super().request(method, params, timeout_sec=timeout_sec)
        del timeout_sec
        payload = params or {}
        self.requests.append((method, payload))
        thread_id = str(payload.get("threadId") or "thread-1")
        turn_id = "turn-started-before-response-1"
        self.emit_notification(
            "turn/started",
            {
                "threadId": thread_id,
                "turnId": turn_id,
                "turn": {
                    "id": turn_id,
                    "threadId": thread_id,
                    "status": "inProgress",
                },
            },
        )
        return {"turnId": turn_id}


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
    recorder = getattr(client.app.state, "session_thread_rollout_recorder_v2", None)
    assert isinstance(recorder, ThreadRolloutRecorder)
    manager = SessionManagerV2(
        protocol_client=protocol,
        runtime_store=RuntimeStoreV2(),
        connection_state_machine=ConnectionStateMachine(),
        thread_rollout_recorder=recorder,
    )
    client.app.state.session_manager_v2 = manager


def _native_recorder(client: TestClient) -> ThreadRolloutRecorder:
    recorder = getattr(client.app.state, "session_thread_rollout_recorder_v2", None)
    assert isinstance(recorder, ThreadRolloutRecorder)
    return recorder


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
            "thread/fork": {"thread": _fake_thread("thread-fork-1"), "modelProvider": "openai"},
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

    recorder = _native_recorder(client)
    recorder.append_items(
        "thread-start-1",
        [
            {
                "type": "event_msg",
                "event": {
                    "method": "turn/completed",
                    "threadId": "thread-start-1",
                    "params": {
                        "turn": {
                            "id": "turn-1",
                            "status": "completed",
                            "items": [{"id": "item-1", "type": "agentMessage", "text": "done"}],
                        }
                    },
                },
            }
        ],
    )

    read_response = client.get("/v4/session/threads/thread-start-1/read?includeTurns=false")
    assert read_response.status_code == 200
    assert read_response.json()["data"]["thread"]["id"] == "thread-start-1"
    assert read_response.json()["data"]["thread"]["turns"] == []

    fork_response = client.post("/v4/session/threads/thread-resume-1/fork", json={})
    assert fork_response.status_code == 200
    assert fork_response.json()["data"]["thread"]["id"] == "thread-fork-1"

    turns_response = client.get("/v4/session/threads/thread-start-1/turns?limit=10")
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
        "thread/fork",
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


def test_session_v4_turn_start_accepts_terminal_notification_before_response(client: TestClient) -> None:
    fake_transport = _EarlyTerminalTransport(
        responses={"initialize": {"serverInfo": {"version": "1.2.3"}}}
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    start_payload = {
        "clientActionId": "start-terminal-before-response",
        "input": [{"type": "text", "text": "hello"}],
    }
    start_response = client.post("/v4/session/threads/thread-1/turns/start", json=start_payload)

    assert start_response.status_code == 200
    turn = start_response.json()["data"]["turn"]
    assert turn["id"] == "turn-early-terminal-1"
    assert turn["status"] == "completed"
    assert turn["items"][0]["text"] == "done before response"

    runtime_store = client.app.state.session_manager_v2._runtime_store  # noqa: SLF001
    assert runtime_store.get_active_turn(thread_id="thread-1") is None
    journal = runtime_store.read_thread_journal("thread-1")
    methods = [event.get("method") for event in journal]
    assert "turn/completed" in methods
    assert "turn/started" not in methods

    replay = client.post("/v4/session/threads/thread-1/turns/start", json=start_payload)
    assert replay.status_code == 200
    assert replay.json()["data"]["turn"]["status"] == "completed"
    assert [method for method, _ in fake_transport.requests].count("turn/start") == 1


def test_session_v4_turn_start_persists_internal_metadata_for_early_terminal_turn(client: TestClient) -> None:
    fake_transport = _EarlyTerminalTransport(
        responses={"initialize": {"serverInfo": {"version": "1.2.3"}}}
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    manager = client.app.state.session_manager_v2
    response = manager.turn_start(
        thread_id="thread-1",
        payload={
            "clientActionId": "artifact-turn-1",
            "input": [{"type": "text", "text": "generate clarify"}],
            "metadata": {"workflowInternal": True, "artifactKind": "clarify"},
        },
    )

    turn = response["turn"]
    assert turn["status"] == "completed"
    assert turn["metadata"]["workflowInternal"] is True

    journal = manager._runtime_store.read_thread_journal("thread-1")  # noqa: SLF001
    started_events = [event for event in journal if event.get("method") == "turn/started"]
    assert started_events
    assert started_events[-1]["params"]["turn"]["metadata"]["workflowInternal"] is True


def test_session_v4_turn_start_replays_internal_metadata_when_provider_started_first(client: TestClient) -> None:
    fake_transport = _StartedBeforeResponseTransport(
        responses={"initialize": {"serverInfo": {"version": "1.2.3"}}}
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    manager = client.app.state.session_manager_v2
    manager.turn_start(
        thread_id="thread-1",
        payload={
            "clientActionId": "artifact-turn-started-first",
            "input": [{"type": "text", "text": "generate spec"}],
            "metadata": {"workflowInternal": True, "artifactKind": "spec"},
        },
    )

    journal = manager._runtime_store.read_thread_journal("thread-1")  # noqa: SLF001
    started_events = [event for event in journal if event.get("method") == "turn/started"]
    assert len(started_events) == 2
    assert "metadata" not in started_events[0]["params"]["turn"]
    assert started_events[1]["params"]["turn"]["metadata"]["workflowInternal"] is True


def test_session_v4_thread_read_include_turns_uses_native_rollout(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={"initialize": {"serverInfo": {"version": "1.2.3"}}},
        failures={
            "thread/read": SessionCoreError(
                code="ERR_INTERNAL",
                message="thread thread-1 is not materialized yet; includeTurns is unavailable before first user message",
                status_code=400,
                details={"rpcCode": -32602},
            )
        },
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200
    _native_recorder(client).ensure_thread(thread_id="thread-1", title="Native thread")
    _native_recorder(client).append_items(
        "thread-1",
        [
            {
                "type": "event_msg",
                "event": {
                    "method": "turn/completed",
                    "threadId": "thread-1",
                    "params": {"turn": {"id": "turn-native-1", "status": "completed"}},
                },
            }
        ],
    )

    response = client.get("/v4/session/threads/thread-1/read?includeTurns=true")

    assert response.status_code == 200, response.json()
    thread = response.json()["data"]["thread"]
    assert thread["id"] == "thread-1"
    assert thread["name"] == "Native thread"
    assert thread["turns"][0]["id"] == "turn-native-1"
    assert thread["turns"][0]["status"] == "completed"
    assert "thread/read" not in [method for method, _ in fake_transport.requests]


def test_session_v4_thread_resume_uses_native_rollout_when_thread_exists(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "thread/resume": {"thread": _fake_thread("provider-resume-thread"), "modelProvider": "openai"},
        },
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200
    _native_recorder(client).ensure_thread(thread_id="thread-1", title="Native running thread", status="running")
    _native_recorder(client).append_items(
        "thread-1",
        [
            {
                "type": "event_msg",
                "event": {
                    "method": "turn/started",
                    "threadId": "thread-1",
                    "turnId": "turn-native-1",
                    "params": {"turn": {"id": "turn-native-1", "status": "inProgress"}},
                },
            }
        ],
    )

    response = client.post("/v4/session/threads/thread-1/resume", json={"cwd": "C:/repo/workspace"})

    assert response.status_code == 200, response.json()
    thread = response.json()["data"]["thread"]
    assert thread["id"] == "thread-1"
    assert thread["status"]["type"] == "active"
    assert "thread/resume" not in [method for method, _ in fake_transport.requests]


def test_session_v4_thread_recover_backfills_provider_turn_into_native_rollout(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "thread/read": {
                "thread": {
                    "id": "thread-1",
                    "name": "Provider thread",
                    "status": {"type": "idle"},
                    "turns": [
                        {
                            "id": "turn-provider-1",
                            "threadId": "thread-1",
                            "status": "completed",
                            "items": [
                                {
                                    "id": "item-provider-1",
                                    "type": "agentMessage",
                                    "text": "Recovered from provider",
                                }
                            ],
                        }
                    ],
                }
            },
        },
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    response = client.post("/v4/session/threads/thread-1/recover", json={})

    assert response.status_code == 200, response.json()
    thread = response.json()["data"]["thread"]
    assert thread["id"] == "thread-1"
    assert thread["turns"][0]["id"] == "turn-provider-1"
    assert thread["turns"][0]["status"] == "completed"
    assert thread["turns"][0]["items"][0]["text"] == "Recovered from provider"
    assert ("thread/read", {"threadId": "thread-1", "includeTurns": True}) in fake_transport.requests

    runtime_turn = client.app.state.session_manager_v2.get_runtime_turn(
        thread_id="thread-1",
        turn_id="turn-provider-1",
    )
    assert runtime_turn["status"] == "completed"
    assert runtime_turn["items"][0]["text"] == "Recovered from provider"


def test_session_v4_turns_list_uses_native_rollout_when_provider_history_unavailable(
    client: TestClient,
) -> None:
    fake_transport = _FakeTransport(
        responses={"initialize": {"serverInfo": {"version": "1.2.3"}}},
        failures={
            "thread/turns/list": SessionCoreError(
                code="ERR_INTERNAL",
                message="thread thread-1 is not materialized yet; thread/turns/list is unavailable before first user message",
                status_code=400,
                details={"rpcCode": -32602},
            )
        },
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200
    _native_recorder(client).ensure_thread(thread_id="thread-1")
    _native_recorder(client).append_items(
        "thread-1",
        [
            {
                "type": "event_msg",
                "event": {
                    "method": "turn/started",
                    "threadId": "thread-1",
                    "turnId": "turn-native-1",
                    "params": {"turnId": "turn-native-1"},
                },
            }
        ],
    )

    response = client.get("/v4/session/threads/thread-1/turns?limit=10")

    assert response.status_code == 200, response.json()
    payload = response.json()["data"]
    assert payload["nextCursor"] is None
    assert payload["data"][0]["id"] == "turn-native-1"
    assert payload["data"][0]["status"] == "inProgress"
    assert "thread/turns/list" not in [method for method, _ in fake_transport.requests]


def test_session_v4_thread_read_missing_native_rollout_returns_not_found(client: TestClient) -> None:
    fake_transport = _FakeTransport(responses={"initialize": {"serverInfo": {"version": "1.2.3"}}})
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    response = client.get("/v4/session/threads/missing-thread/read?includeTurns=true")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "no rollout found for thread id missing-thread"


def test_session_v4_turn_start_missing_turn_id_fails_deterministically_without_idempotent_commit(
    client: TestClient,
) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    payload = {
        "clientActionId": "start-missing-turn-id",
        "input": [{"type": "text", "text": "hello"}],
    }
    first = client.post("/v4/session/threads/thread-1/turns/start", json=payload)
    assert first.status_code == 502
    assert first.json()["error"]["code"] == "ERR_INTERNAL"
    assert "missing turnId" in first.json()["error"]["message"]

    second = client.post("/v4/session/threads/thread-1/turns/start", json=payload)
    assert second.status_code == 502
    assert second.json()["error"]["code"] == "ERR_INTERNAL"
    assert [method for method, _ in fake_transport.requests].count("turn/start") == 2

    runtime_store = client.app.state.session_manager_v2._runtime_store  # noqa: SLF001
    assert runtime_store.get_active_turn(thread_id="thread-1") is None


def test_session_v4_turn_start_invariants_runtime_journal_turns_and_replay(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {"turnId": "turn-start-1"},
            "thread/turns/list": {"data": [], "nextCursor": None},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    start_payload = {
        "clientActionId": "start-invariants-1",
        "input": [{"type": "text", "text": "hello"}],
    }
    start_response = client.post("/v4/session/threads/thread-1/turns/start", json=start_payload)
    assert start_response.status_code == 200
    assert start_response.json()["data"]["turn"]["id"] == "turn-start-1"

    runtime_store = client.app.state.session_manager_v2._runtime_store  # noqa: SLF001
    active_turn = runtime_store.get_active_turn(thread_id="thread-1")
    assert active_turn is not None
    assert active_turn["id"] == "turn-start-1"
    assert active_turn["status"] == "inProgress"

    turns_response = client.get("/v4/session/threads/thread-1/turns")
    assert turns_response.status_code == 200
    turns = turns_response.json()["data"]["data"]
    assert any(str(turn.get("id")) == "turn-start-1" for turn in turns)

    journal = runtime_store.read_thread_journal("thread-1")
    started_events = [event for event in journal if event.get("method") == "turn/started"]
    assert len(started_events) == 1
    assert started_events[0]["turnId"] == "turn-start-1"

    manager = client.app.state.session_manager_v2
    original_read_stream_event = manager.read_stream_event
    manager.read_stream_event = lambda **_: None
    try:
        stream_response = client.get("/v4/session/threads/thread-1/events?cursor=0")
    finally:
        manager.read_stream_event = original_read_stream_event
    assert stream_response.status_code == 200
    data_lines = [line[len("data: ") :] for line in stream_response.text.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line) for line in data_lines]
    assert any(
        str(payload.get("method") or "") == "turn/started"
        and str(payload.get("turnId") or "") == "turn-start-1"
        for payload in payloads
    )


def test_session_v4_turn_started_notification_dedupes_against_synthetic_event(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "turn/start": {"turnId": "turn-start-1"},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    assert client.post(
        "/v4/session/threads/thread-1/turns/start",
        json={"clientActionId": "start-dedupe-1", "input": [{"type": "text", "text": "hello"}]},
    ).status_code == 200

    fake_transport.emit_notification(
        "turn/started",
        {
            "threadId": "thread-1",
            "turn": {"id": "turn-start-1", "status": "inProgress", "items": []},
        },
    )

    runtime_store = client.app.state.session_manager_v2._runtime_store  # noqa: SLF001
    journal = runtime_store.read_thread_journal("thread-1")
    assert [event.get("method") for event in journal].count("turn/started") == 1


def test_session_v4_inject_items_idempotent_without_starting_turn(client: TestClient) -> None:
    injected_item = {
        "id": "context-item-1",
        "type": "systemMessage",
        "text": "Workflow context",
        "metadata": {"workflowContext": True},
    }
    thread_with_context = _fake_thread("thread-1")
    thread_with_context["turns"] = [
        {"id": "context-turn-1", "status": "completed", "items": [injected_item]},
    ]
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "thread/inject_items": {"status": "accepted"},
        }
    )
    _install_fake_manager(client, fake_transport)

    payload = {"clientActionId": "inject-1", "items": [injected_item]}
    pre_init_response = client.post("/v4/session/threads/thread-1/inject-items", json=payload)
    assert pre_init_response.status_code == 409
    assert pre_init_response.json()["error"]["code"] == "ERR_SESSION_NOT_INITIALIZED"

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    invalid_response = client.post(
        "/v4/session/threads/thread-1/inject-items",
        json={"clientActionId": "inject-invalid", "items": []},
    )
    assert invalid_response.status_code == 422

    first_response = client.post("/v4/session/threads/thread-1/inject-items", json=payload)
    duplicate_response = client.post("/v4/session/threads/thread-1/inject-items", json=payload)
    assert first_response.status_code == 200
    assert duplicate_response.status_code == 200
    assert first_response.json()["data"]["status"] == "accepted"
    assert duplicate_response.json()["data"]["status"] == "accepted"

    request_methods = [method for method, _ in fake_transport.requests]
    assert request_methods.count("thread/inject_items") == 1
    assert "turn/start" not in request_methods
    assert (
        "thread/inject_items",
        {"threadId": "thread-1", "clientActionId": "inject-1", "items": [injected_item]},
    ) in fake_transport.requests
    runtime_store = client.app.state.session_manager_v2._runtime_store  # noqa: SLF001
    active_turn = runtime_store.get_active_turn(thread_id="thread-1")
    assert active_turn is None

    read_response = client.get("/v4/session/threads/thread-1/read?includeTurns=true")
    assert read_response.status_code == 200
    replayed_item = read_response.json()["data"]["thread"]["turns"][0]["items"][0]
    assert replayed_item["id"] == injected_item["id"]
    assert replayed_item["type"] == injected_item["type"]
    assert replayed_item["text"] == injected_item["text"]
    assert replayed_item["metadata"] == injected_item["metadata"]
    assert replayed_item["status"] == "completed"

    mismatch_response = client.post(
        "/v4/session/threads/thread-1/inject-items",
        json={
            "clientActionId": "inject-1",
            "items": [{"id": "context-item-2", "type": "systemMessage"}],
        },
    )
    assert mismatch_response.status_code == 409
    assert mismatch_response.json()["error"]["code"] == "ERR_IDEMPOTENCY_PAYLOAD_MISMATCH"
    assert [method for method, _ in fake_transport.requests].count("thread/inject_items") == 1


def test_session_v4_inject_items_workflow_context_is_replayable_and_marked_hidden_metadata(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "thread/inject_items": {"status": "accepted"},
            "thread/turns/list": {"data": [], "nextCursor": None},
        }
    )
    _install_fake_manager(client, fake_transport)

    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    payload = {
        "clientActionId": "inject-context-1",
        "items": [
            {
                "id": "workflow-context-1",
                "type": "systemMessage",
                "text": "context payload",
                "metadata": {
                    "workflowContext": True,
                    "role": "execution",
                    "contextPacketHash": "sha256:packet",
                },
            }
        ],
    }
    response = client.post("/v4/session/threads/thread-1/inject-items", json=payload)
    assert response.status_code == 200

    runtime_store = client.app.state.session_manager_v2._runtime_store  # noqa: SLF001
    journal = runtime_store.read_thread_journal("thread-1")
    methods = [str(event.get("method") or "") for event in journal]
    assert "turn/started" in methods
    assert "item/completed" in methods
    assert "turn/completed" in methods
    context_item_events = [event for event in journal if str(event.get("method") or "") == "item/completed"]
    assert context_item_events
    context_item = context_item_events[-1]["params"]["item"]
    assert context_item["metadata"]["workflowContext"] is True
    assert context_item["metadata"]["role"] == "execution"
    assert context_item["metadata"]["contextPacketHash"] == "sha256:packet"

    turns_response = client.get("/v4/session/threads/thread-1/turns")
    assert turns_response.status_code == 200
    turns = turns_response.json()["data"]["data"]
    assert any(str(turn.get("status") or "") == "completed" for turn in turns)


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

        inject_response = client.post(
            "/v4/session/threads/thread-1/inject-items",
            json={
                "clientActionId": "inject-1",
                "items": [{"type": "systemMessage", "text": "context"}],
            },
        )
        assert inject_response.status_code == 501
        assert inject_response.json()["error"]["code"] == "ERR_PHASE_NOT_ENABLED"

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
                "turn/start": {"turnId": "turn-start-1"},
            "turn/steer": {"turnId": "turn-start-1"},
            "turn/interrupt": {},
            "thread/inject_items": {"status": "accepted"},
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
    read_payload = client.get("/v4/session/threads/thread-start-1/read").json()
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
    inject_payload = client.post(
        "/v4/session/threads/thread-1/inject-items",
        json={
            "clientActionId": "inject-contract-1",
            "items": [{"type": "systemMessage", "text": "context"}],
        },
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
    _assert_component(inject_payload, "BasicOkEnvelope", schema_doc)
    _assert_component(pending_payload, "PendingRequestsEnvelope", schema_doc)
    _assert_component(resolve_payload, "BasicOkEnvelope", schema_doc)
    _assert_component(reject_payload, "BasicOkEnvelope", schema_doc)


def test_session_v4_events_stream_drops_non_session_namespace_events(client: TestClient) -> None:
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
        }
    )
    _install_fake_manager(client, fake_transport)
    assert client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).status_code == 200

    manager = client.app.state.session_manager_v2
    runtime_store = manager._runtime_store  # noqa: SLF001
    runtime_store.append_event(
        thread_id="thread-1",
        method="workflow/state_changed",
        params={"projectId": "project-1"},
        turn_id=None,
        source="journal",
        replayable=True,
    )

    original_read_stream_event = manager.read_stream_event
    manager.read_stream_event = lambda **_: None
    try:
        stream_response = client.get("/v4/session/threads/thread-1/events?cursor=0")
    finally:
        manager.read_stream_event = original_read_stream_event
    assert stream_response.status_code == 200
    data_lines = [line for line in stream_response.text.splitlines() if line.startswith("data: ")]
    assert data_lines == []


def test_session_v4_remaining_phase_gated_route_returns_deterministic_501(client: TestClient) -> None:
    response = client.post("/v4/session/threads/thread-1/archive", json={})
    assert response.status_code == 501
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ERR_PHASE_NOT_ENABLED"
