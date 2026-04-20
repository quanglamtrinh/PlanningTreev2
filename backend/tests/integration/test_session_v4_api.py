from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.errors import SessionCoreError
from backend.session_core_v2.protocol import SessionProtocolClientV2
from backend.session_core_v2.storage import RuntimeStoreV2


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
        if method in self.failures:
            raise self.failures[method]
        return self.responses.get(method, {})

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.notifications.append((method, params or {}))


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

    assert [method for method, _ in fake_transport.requests] == [
        "initialize",
        "thread/start",
        "thread/resume",
        "thread/list",
        "thread/read",
    ]
    assert fake_transport.notifications == [("initialized", {})]


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


def test_session_v4_contract_conformance_for_phase1_endpoints(client: TestClient) -> None:
    schema_doc = _openapi_schema()
    fake_transport = _FakeTransport(
        responses={
            "initialize": {"serverInfo": {"version": "1.2.3"}},
            "thread/start": {"thread": _fake_thread("thread-start-1"), "modelProvider": "openai"},
            "thread/resume": {"thread": _fake_thread("thread-resume-1"), "modelProvider": "openai"},
            "thread/list": {"data": [_fake_thread("thread-list-1")], "nextCursor": None},
            "thread/read": {"thread": _fake_thread("thread-read-1")},
        }
    )
    _install_fake_manager(client, fake_transport)

    init_payload = client.post(
        "/v4/session/initialize",
        json={"clientInfo": {"name": "PlanningTree", "version": "0.1.0"}},
    ).json()
    status_payload = client.get("/v4/session/status").json()
    start_payload = client.post("/v4/session/threads/start", json={}).json()
    resume_payload = client.post("/v4/session/threads/thread-resume-1/resume", json={}).json()
    list_payload = client.get("/v4/session/threads/list").json()
    read_payload = client.get("/v4/session/threads/thread-read-1/read").json()

    _assert_component(init_payload, "InitializeResponseEnvelope", schema_doc)
    _assert_component(status_payload, "ConnectionStatusEnvelope", schema_doc)
    _assert_component(start_payload, "ThreadConfigEnvelope", schema_doc)
    _assert_component(resume_payload, "ThreadConfigEnvelope", schema_doc)
    _assert_component(list_payload, "ThreadListEnvelope", schema_doc)
    _assert_component(read_payload, "ThreadEnvelope", schema_doc)


def test_session_v4_phase_gated_route_returns_deterministic_501(client: TestClient) -> None:
    response = client.post("/v4/session/threads/thread-1/fork", json={})
    assert response.status_code == 501
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ERR_PHASE_NOT_ENABLED"
