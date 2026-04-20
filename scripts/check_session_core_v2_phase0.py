from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs" / "remodel" / "contracts" / "session-core-v2"
CODEX_SCHEMA = (
    Path.home()
    / "codex"
    / "codex-rs"
    / "app-server-protocol"
    / "schema"
    / "json"
    / "codex_app_server_protocol.v2.schemas.json"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    required_files = [
        "README.md",
        "s0-codex-parity-method-map-v1.md",
        "s1-jsonrpc-lifecycle-contract-v1.md",
        "s2-core-primitives-v1.schema.json",
        "s3-session-http-api-v1.openapi.yaml",
        "s4-event-envelope-v1.schema.json",
        "s4-event-stream-contract-v1.md",
        "s4-server-request-envelope-v1.schema.json",
        "s5-durability-replay-contract-v1.md",
        "s6-idempotency-contract-v1.md",
        "s7-turn-state-machine-contract-v1.md",
        "s8-session-binding-contract-v1.md",
        "phase-0-gate-report-v1.md",
    ]
    errors: list[str] = []

    for rel in required_files:
        if not (BASE / rel).exists():
            errors.append(f"missing file: {rel}")

    json_files = [
        "s2-core-primitives-v1.schema.json",
        "s4-event-envelope-v1.schema.json",
        "s4-server-request-envelope-v1.schema.json",
        "fixtures/s4-event-valid-v1.json",
        "fixtures/s4-event-invalid-missing-event-seq-v1.json",
        "fixtures/s4-server-request-valid-v1.json",
        "fixtures/s4-server-request-invalid-method-v1.json",
    ]
    for rel in json_files:
        try:
            read_json(BASE / rel)
        except Exception as exc:
            errors.append(f"invalid json {rel}: {exc}")

    # YAML parse check is optional but useful.
    try:
        import yaml

        yaml.safe_load((BASE / "s3-session-http-api-v1.openapi.yaml").read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid openapi yaml: {exc}")

    event_schema = read_json(BASE / "s4-event-envelope-v1.schema.json")
    request_schema = read_json(BASE / "s4-server-request-envelope-v1.schema.json")
    valid_event = read_json(BASE / "fixtures/s4-event-valid-v1.json")
    invalid_event = read_json(BASE / "fixtures/s4-event-invalid-missing-event-seq-v1.json")
    valid_request = read_json(BASE / "fixtures/s4-server-request-valid-v1.json")
    invalid_request = read_json(BASE / "fixtures/s4-server-request-invalid-method-v1.json")

    required_event_fields = set(event_schema["required"])
    if not required_event_fields.issubset(valid_event.keys()):
        errors.append("valid event fixture missing required fields")
    if "eventSeq" in invalid_event:
        errors.append("invalid event fixture unexpectedly contains eventSeq")

    request_methods = set(request_schema["properties"]["method"]["enum"])
    if valid_request.get("method") not in request_methods:
        errors.append("valid request fixture method is not allowed")
    if invalid_request.get("method") in request_methods:
        errors.append("invalid request fixture method is unexpectedly allowed")

    if not CODEX_SCHEMA.exists():
        errors.append(f"missing codex schema: {CODEX_SCHEMA}")
    else:
        codex = read_json(CODEX_SCHEMA)
        client_methods: set[str] = set()
        for entry in codex["definitions"]["ClientRequest"]["oneOf"]:
            methods = (((entry.get("properties") or {}).get("method") or {}).get("enum") or [])
            if methods:
                client_methods.add(methods[0])
        expected_methods = {
            "thread/start",
            "thread/resume",
            "thread/fork",
            "thread/list",
            "thread/read",
            "thread/turns/list",
            "thread/loaded/list",
            "thread/unsubscribe",
            "thread/archive",
            "thread/unarchive",
            "thread/name/set",
            "thread/metadata/update",
            "thread/rollback",
            "thread/compact/start",
            "thread/inject_items",
            "turn/start",
            "turn/steer",
            "turn/interrupt",
        }
        missing = sorted(expected_methods - client_methods)
        if missing:
            errors.append(f"codex schema missing expected methods: {', '.join(missing)}")

    openapi_text = (BASE / "s3-session-http-api-v1.openapi.yaml").read_text(encoding="utf-8")
    if "required: [clientActionId, expectedTurnId, input]" not in openapi_text:
        errors.append("turn steer precondition contract not frozen")
    if "originUrl" not in openapi_text:
        errors.append("thread metadata gitInfo.originUrl is missing")

    if errors:
        print("PHASE0_CONTRACT_CHECK=FAIL")
        for err in errors:
            print("-", err)
        return 1

    print("PHASE0_CONTRACT_CHECK=PASS")
    print(f"checked_files={len(required_files)}")
    print("codex_methods_verified=18")
    print("fixtures_checked=4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
