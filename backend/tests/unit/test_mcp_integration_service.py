from __future__ import annotations

import pytest

from backend.config.app_config import build_app_paths
from backend.mcp import McpIntegrationService
from backend.session_core_v2.errors import SessionCoreError


class FakeProtocol:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.batch_writes: list[dict] = []
        self.generation = 1
        self.running = True
        self.fail_batch: Exception | None = None
        self.fail_refresh: Exception | None = None

    def app_server_process_generation(self) -> int:
        return self.generation

    def app_server_process_running(self) -> bool:
        return self.running

    def config_batch_write(self, params: dict) -> dict:
        if self.fail_batch is not None:
            raise self.fail_batch
        self.batch_writes.append(params)
        return {}

    def mcp_server_refresh(self) -> dict:
        if self.fail_refresh is not None:
            raise self.fail_refresh
        self.refresh_count += 1
        return {}


def test_registry_profile_effective_config_hash_and_secret_rejection(tmp_path) -> None:
    service = McpIntegrationService(build_app_paths(tmp_path))

    with pytest.raises(SessionCoreError) as exc:
        service.upsert_registry_server(
            {
                "serverId": "bad",
                "transport": {
                    "type": "streamable_http",
                    "url": "https://example.test/mcp",
                    "bearer_token": "secret",
                },
            }
        )
    assert exc.value.code == "ERR_MCP_REGISTRY_INVALID"

    service.upsert_registry_server(
        {
            "serverId": "fs",
            "name": "Filesystem",
            "transport": {"type": "stdio", "command": "python", "args": ["echo.py"]},
        }
    )
    service.write_profile(
        "project-1",
        "node-1",
        "execution",
        {
            "mcpEnabled": True,
            "servers": {
                "fs": {
                    "enabled": True,
                    "enabledTools": ["read_file"],
                    "disabledTools": [],
                    "approvalMode": "onRequest",
                }
            },
        },
    )

    preview = service.preview_effective_config("project-1", "node-1", "execution")
    assert preview["effectiveConfig"] == {
        "mcp_servers": {
            "fs": {
                "command": "python",
                "args": ["echo.py"],
                "enabled_tools": ["read_file"],
                "default_tools_approval_mode": "prompt",
            }
        }
    }
    assert preview["mcpConfigHash"].startswith("sha256:")


def test_runtime_conflict_guard_rejects_different_active_hash(tmp_path) -> None:
    service = McpIntegrationService(build_app_paths(tmp_path))
    protocol = FakeProtocol()
    service.upsert_registry_server({"serverId": "a", "transport": {"type": "stdio", "command": "python"}})
    service.upsert_registry_server({"serverId": "b", "transport": {"type": "stdio", "command": "node"}})
    service.write_profile(
        "project-1",
        "node-1",
        "execution",
        {"mcpEnabled": True, "servers": {"a": {"enabled": True}}},
    )
    service.write_profile(
        "project-1",
        "node-2",
        "execution",
        {"mcpEnabled": True, "servers": {"b": {"enabled": True}}},
    )

    prepared = service.prepare_turn_start(
        thread_id="thread-a",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        protocol_client=protocol,
    )
    service.commit_runtime_turn(
        thread_id="thread-a",
        turn_id="turn-a",
        pending_hash=prepared["_mcpPendingRuntimeHash"],
    )

    with pytest.raises(SessionCoreError) as exc:
        service.prepare_turn_start(
            thread_id="thread-b",
            payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-2", "role": "execution"}},
            protocol_client=protocol,
        )
    assert exc.value.code == "ERR_MCP_CONFIG_CONFLICT"

    service.release_runtime_turn(thread_id="thread-a", turn_id="turn-a")
    service.prepare_turn_start(
        thread_id="thread-b",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-2", "role": "execution"}},
        protocol_client=protocol,
    )



def test_prepare_turn_start_applies_config_and_redacts_metadata(tmp_path) -> None:
    service = McpIntegrationService(build_app_paths(tmp_path))
    protocol = FakeProtocol()
    service.upsert_registry_server(
        {
            "serverId": "fs",
            "name": "Filesystem",
            "transport": {"type": "stdio", "command": "python", "args": ["echo.py"], "env": {"TOKEN": "secret"}},
        }
    )
    service.write_profile(
        "project-1",
        "node-1",
        "execution",
        {"mcpEnabled": True, "servers": {"fs": {"enabled": True, "enabledTools": ["read_file"]}}},
    )

    prepared = service.prepare_turn_start(
        thread_id="thread-1",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        protocol_client=protocol,
    )

    assert protocol.refresh_count == 1
    assert protocol.batch_writes == [
        {
            "edits": [
                {
                    "keyPath": "mcp_servers",
                    "value": {
                        "fs": {
                            "command": "python",
                            "args": ["echo.py"],
                            "env": {"TOKEN": "secret"},
                            "enabled_tools": ["read_file"],
                            "default_tools_approval_mode": "auto",
                        }
                    },
                    "mergeStrategy": "replace",
                }
            ],
            "filePath": None,
            "expectedVersion": None,
            "reloadUserConfig": True,
        }
    ]
    assert "mcpConfigHash" in prepared["metadata"]
    assert prepared["metadata"]["mcpEffectiveConfigSummary"] == {"serverIds": ["fs"], "serverCount": 1}
    assert "mcpEffectiveConfig" not in prepared["metadata"]

    # Same hash and process generation should dedupe the config write.
    service.release_runtime_turn(thread_id="thread-1", turn_id="__pending__")
    service.prepare_turn_start(
        thread_id="thread-1",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        protocol_client=protocol,
    )
    assert len(protocol.batch_writes) == 1

    # A restarted app-server forces reapply even when the hash is unchanged.
    service.release_runtime_turn(thread_id="thread-1", turn_id="__pending__")
    protocol.generation = 2
    service.prepare_turn_start(
        thread_id="thread-1",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        protocol_client=protocol,
    )
    assert len(protocol.batch_writes) == 2


def test_empty_config_transition_applies_and_refreshes(tmp_path) -> None:
    service = McpIntegrationService(build_app_paths(tmp_path))
    protocol = FakeProtocol()
    service.upsert_registry_server({"serverId": "fs", "transport": {"type": "stdio", "command": "python"}})
    service.write_profile("project-1", "node-1", "execution", {"mcpEnabled": True, "servers": {"fs": {"enabled": True}}})
    prepared = service.prepare_turn_start(
        thread_id="thread-1",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        protocol_client=protocol,
    )
    service.commit_runtime_turn(thread_id="thread-1", turn_id="turn-1", pending_hash=prepared["_mcpPendingRuntimeHash"])
    service.release_runtime_turn(thread_id="thread-1", turn_id="turn-1")

    service.write_profile("project-1", "node-1", "execution", {"mcpEnabled": False, "servers": {"fs": {"enabled": False}}})
    service.prepare_turn_start(
        thread_id="thread-1",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        protocol_client=protocol,
    )

    assert protocol.batch_writes[-1]["edits"][0]["value"] == {}
    assert protocol.refresh_count == 2


def test_apply_failures_release_pending_and_do_not_advance_hash(tmp_path) -> None:
    service = McpIntegrationService(build_app_paths(tmp_path))
    protocol = FakeProtocol()
    service.upsert_registry_server({"serverId": "fs", "transport": {"type": "stdio", "command": "python"}})
    service.write_profile("project-1", "node-1", "execution", {"mcpEnabled": True, "servers": {"fs": {"enabled": True}}})
    protocol.fail_refresh = SessionCoreError(code="ERR_PROVIDER_UNAVAILABLE", message="reload failed", status_code=502)

    with pytest.raises(SessionCoreError):
        service.prepare_turn_start(
            thread_id="thread-1",
            payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
            protocol_client=protocol,
        )
    assert service.runtime_state_for_hash(None)["activeTurns"] == []

    protocol.fail_refresh = None
    service.prepare_turn_start(
        thread_id="thread-1",
        payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
        protocol_client=protocol,
    )
    assert len(protocol.batch_writes) == 2


def test_method_not_found_reports_unsupported_version(tmp_path) -> None:
    service = McpIntegrationService(build_app_paths(tmp_path))
    protocol = FakeProtocol()
    service.upsert_registry_server({"serverId": "fs", "transport": {"type": "stdio", "command": "python"}})
    service.write_profile("project-1", "node-1", "execution", {"mcpEnabled": True, "servers": {"fs": {"enabled": True}}})
    protocol.fail_batch = SessionCoreError(
        code="ERR_PROVIDER_METHOD_UNSUPPORTED",
        message="method not found",
        status_code=502,
        details={"rpcCode": -32601},
    )

    with pytest.raises(SessionCoreError) as exc:
        service.prepare_turn_start(
            thread_id="thread-1",
            payload={"input": [], "mcpContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"}},
            protocol_client=protocol,
        )
    assert exc.value.code == "ERR_MCP_CONFIG_APPLY_UNSUPPORTED"
    assert service.runtime_state_for_hash(None)["activeTurns"] == []


def test_corrupt_registry_and_profile_json_fall_back_to_empty(tmp_path) -> None:
    paths = build_app_paths(tmp_path)
    service = McpIntegrationService(paths)
    paths.config_root.mkdir(parents=True, exist_ok=True)
    paths.data_root.mkdir(parents=True, exist_ok=True)
    (paths.config_root / "mcp_registry.json").write_text("{not-json", encoding="utf-8")
    (paths.data_root / "mcp_profiles.json").write_text("{not-json", encoding="utf-8")

    assert service.list_registry()["servers"] == []
    assert service.read_profile("project-1", "node-1", "execution")["mcpEnabled"] is False
    assert list(paths.config_root.glob("mcp_registry.json.corrupt.*"))
    assert list(paths.data_root.glob("mcp_profiles.json.corrupt.*"))
