from __future__ import annotations

import pytest

from backend.config.app_config import build_app_paths
from backend.mcp import McpIntegrationService
from backend.session_core_v2.errors import SessionCoreError


class FakeProtocol:
    def __init__(self) -> None:
        self.refresh_count = 0

    def mcp_server_refresh(self) -> dict:
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
