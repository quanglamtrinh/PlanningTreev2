from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.session_core_v2.errors import SessionCoreError
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now

VALID_ROLES = {"ask_planning", "execution", "audit", "package_review"}
VALID_APPROVAL_MODES = {"never", "onRequest", "onFailure", "untrusted"}
logger = logging.getLogger(__name__)


def canonical_effective_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()



class McpIntegrationService:
    def __init__(self, paths: AppPaths, project_cwd_resolver: Callable[[str], str] | None = None) -> None:
        self._paths = paths
        self._project_cwd_resolver = project_cwd_resolver
        self._registry_path = paths.config_root / "mcp_registry.json"
        self._profiles_path = paths.data_root / "mcp_profiles.json"
        self._lock = threading.RLock()
        self._active_runtime_hash: str | None = None
        self._active_turn_hashes: dict[tuple[str, str], str] = {}
        self._last_applied_mcp_config_hash: str | None = None
        self._last_applied_process_generation: int | None = None

    # ------------------------------------------------------------------
    # Global registry
    # ------------------------------------------------------------------
    def list_registry(self) -> dict[str, Any]:
        with self._lock:
            registry = self._load_registry_locked()
            servers = [self._server_with_health(server) for server in registry.get("servers", [])]
            return {"servers": servers, "updatedAt": registry.get("updatedAt")}

    def upsert_registry_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        server = self._validate_registry_server(payload)
        with self._lock:
            registry = self._load_registry_locked()
            servers = [entry for entry in registry.get("servers", []) if entry.get("serverId") != server["serverId"]]
            servers.append(server)
            servers.sort(key=lambda entry: str(entry.get("serverId") or ""))
            registry = {"schemaVersion": 1, "servers": servers, "updatedAt": iso_now()}
            self._write_registry_locked(registry)
            return {"server": self._server_with_health(server)}

    def delete_registry_server(self, server_id: str) -> dict[str, Any]:
        normalized = self._require_id(server_id, "serverId")
        with self._lock:
            registry = self._load_registry_locked()
            servers = [entry for entry in registry.get("servers", []) if entry.get("serverId") != normalized]
            registry = {"schemaVersion": 1, "servers": servers, "updatedAt": iso_now()}
            self._write_registry_locked(registry)
            return {"deleted": True, "serverId": normalized}

    def registry_health(self) -> dict[str, Any]:
        return {"servers": self.list_registry()["servers"]}

    # ------------------------------------------------------------------
    # Thread profiles and effective config
    # ------------------------------------------------------------------
    def read_profile(self, project_id: str, node_id: str, role: str) -> dict[str, Any]:
        key = self._profile_key(project_id, node_id, role)
        with self._lock:
            profiles = self._load_profiles_locked()
            return self._default_profile(project_id, node_id, role) | dict(profiles.get(key, {}))

    def write_profile(self, project_id: str, node_id: str, role: str, patch: dict[str, Any]) -> dict[str, Any]:
        base = self.read_profile(project_id, node_id, role)
        updated = self._validate_profile({**base, **copy.deepcopy(patch)}, project_id, node_id, role)
        key = self._profile_key(project_id, node_id, role)
        with self._lock:
            profiles = self._load_profiles_locked()
            profiles[key] = updated
            self._write_profiles_locked(profiles)
        return {"profile": updated}

    def reset_profile(self, project_id: str, node_id: str, role: str) -> dict[str, Any]:
        key = self._profile_key(project_id, node_id, role)
        with self._lock:
            profiles = self._load_profiles_locked()
            profiles.pop(key, None)
            self._write_profiles_locked(profiles)
        return {"profile": self._default_profile(project_id, node_id, role)}

    def preview_effective_config(
        self,
        project_id: str,
        node_id: str,
        role: str,
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        profile = self.read_profile(project_id, node_id, role)
        project_cwd = self._resolve_project_cwd(project_id)
        with self._lock:
            registry = self._load_registry_locked()
        effective = self._compose_effective_config(registry.get("servers", []), profile, project_cwd=project_cwd)
        mcp_hash = canonical_effective_config_hash(effective)
        return {
            "projectId": project_id,
            "nodeId": node_id,
            "role": role,
            "threadId": thread_id,
            "profile": profile,
            "effectiveConfig": effective,
            "mcpConfigHash": mcp_hash,
            "runtime": self.runtime_state_for_hash(mcp_hash),
        }

    def prepare_turn_start(self, *, thread_id: str, payload: dict[str, Any], protocol_client: Any) -> dict[str, Any]:
        context = payload.get("mcpContext") if isinstance(payload.get("mcpContext"), dict) else None
        if context is None:
            effective = {"mcp_servers": {}}
            mcp_hash = canonical_effective_config_hash(effective)
            preview = {"effectiveConfig": effective, "mcpConfigHash": mcp_hash}
        else:
            project_id = self._require_id(context.get("projectId"), "projectId")
            node_id = self._require_id(context.get("nodeId"), "nodeId")
            role = self._normalize_role(str(context.get("role") or ""))
            preview = self.preview_effective_config(project_id, node_id, role, thread_id=thread_id)
            effective = preview["effectiveConfig"]
            mcp_hash = preview["mcpConfigHash"]

        pending_key = (thread_id, "__pending__")
        self._acquire_runtime_turn(pending_key, mcp_hash)
        try:
            self._apply_effective_config_if_needed(effective, mcp_hash, protocol_client)
        except Exception:
            self.release_runtime_turn(thread_id=thread_id, turn_id="__pending__")
            raise

        next_payload = dict(payload)
        next_payload.pop("mcpContext", None)
        metadata = dict(next_payload.get("metadata")) if isinstance(next_payload.get("metadata"), dict) else {}
        metadata["mcpConfigHash"] = mcp_hash
        metadata["mcpEffectiveConfigSummary"] = self._effective_config_summary(effective)
        next_payload["metadata"] = metadata
        next_payload["_mcpPendingRuntimeHash"] = mcp_hash
        return next_payload

    def commit_runtime_turn(self, *, thread_id: str, turn_id: str, pending_hash: str | None) -> None:
        if not pending_hash:
            return
        with self._lock:
            self._active_turn_hashes.pop((thread_id, "__pending__"), None)
            self._active_turn_hashes[(thread_id, turn_id)] = pending_hash
            self._active_runtime_hash = pending_hash

    def release_runtime_turn(self, *, thread_id: str, turn_id: str) -> None:
        normalized_thread_id = str(thread_id or "").strip()
        normalized_turn_id = str(turn_id or "").strip()
        if not normalized_thread_id or not normalized_turn_id:
            return
        with self._lock:
            self._active_turn_hashes.pop((normalized_thread_id, normalized_turn_id), None)
            if not self._active_turn_hashes:
                self._active_runtime_hash = None

    def runtime_state_for_hash(self, mcp_config_hash: str | None = None) -> dict[str, Any]:
        with self._lock:
            active_turns = [
                {"threadId": thread_id, "turnId": turn_id, "mcpConfigHash": turn_hash}
                for (thread_id, turn_id), turn_hash in sorted(self._active_turn_hashes.items())
            ]
            conflict = bool(
                mcp_config_hash
                and self._active_runtime_hash
                and self._active_turn_hashes
                and self._active_runtime_hash != mcp_config_hash
            )
            return {
                "activeRuntimeMcpConfigHash": self._active_runtime_hash,
                "activeTurns": active_turns,
                "conflict": conflict,
            }


    def _apply_effective_config_if_needed(self, effective: dict[str, Any], mcp_hash: str, protocol_client: Any) -> None:
        generation = self._protocol_process_generation(protocol_client)
        process_running = self._protocol_process_running(protocol_client)
        with self._lock:
            must_apply = (
                not process_running
                or self._last_applied_mcp_config_hash != mcp_hash
                or self._last_applied_process_generation != generation
            )
        if not must_apply:
            return

        batch_payload = {
            "edits": [
                {
                    "keyPath": "mcp_servers",
                    "value": copy.deepcopy(effective.get("mcp_servers") or {}),
                    "mergeStrategy": "replace",
                }
            ],
            "filePath": None,
            "expectedVersion": None,
            "reloadUserConfig": True,
        }
        try:
            protocol_client.config_batch_write(batch_payload)
            protocol_client.mcp_server_refresh()
        except SessionCoreError as exc:
            if exc.details.get("rpcCode") == -32601 or exc.code == "ERR_PROVIDER_METHOD_UNSUPPORTED":
                raise SessionCoreError(
                    code="ERR_MCP_CONFIG_APPLY_UNSUPPORTED",
                    message="MCP effective config apply requires a Codex app-server version that supports config/batchWrite.",
                    status_code=502,
                    details={"method": "config/batchWrite", "cause": exc.details},
                ) from exc
            logger.warning(
                "MCP effective config apply failed; turn start will not continue",
                extra={
                    "mcpConfigHash": mcp_hash,
                    "appServerProcessGeneration": generation,
                    "errorCode": exc.code,
                },
            )
            raise
        except Exception:
            logger.warning(
                "MCP effective config apply failed unexpectedly; turn start will not continue",
                extra={"mcpConfigHash": mcp_hash, "appServerProcessGeneration": generation},
                exc_info=True,
            )
            raise

        applied_generation = self._protocol_process_generation(protocol_client)
        with self._lock:
            self._last_applied_mcp_config_hash = mcp_hash
            self._last_applied_process_generation = applied_generation

    @staticmethod
    def _protocol_process_generation(protocol_client: Any) -> int:
        getter = getattr(protocol_client, "app_server_process_generation", None)
        if callable(getter):
            try:
                return int(getter())
            except Exception:
                return 0
        return 0

    @staticmethod
    def _protocol_process_running(protocol_client: Any) -> bool:
        getter = getattr(protocol_client, "app_server_process_running", None)
        if callable(getter):
            try:
                return bool(getter())
            except Exception:
                return False
        return True

    @staticmethod
    def _effective_config_summary(effective: dict[str, Any]) -> dict[str, Any]:
        servers = effective.get("mcp_servers") if isinstance(effective.get("mcp_servers"), dict) else {}
        return {"serverIds": sorted(str(server_id) for server_id in servers), "serverCount": len(servers)}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _acquire_runtime_turn(self, key: tuple[str, str], mcp_config_hash: str) -> None:
        with self._lock:
            if self._active_turn_hashes and self._active_runtime_hash and self._active_runtime_hash != mcp_config_hash:
                raise SessionCoreError(
                    code="ERR_MCP_CONFIG_CONFLICT",
                    message="Another active turn is using a different effective MCP config.",
                    status_code=409,
                    details={
                        "activeRuntimeMcpConfigHash": self._active_runtime_hash,
                        "requestedMcpConfigHash": mcp_config_hash,
                        "activeTurns": [
                            {"threadId": thread_id, "turnId": turn_id, "mcpConfigHash": turn_hash}
                            for (thread_id, turn_id), turn_hash in sorted(self._active_turn_hashes.items())
                        ],
                    },
                )
            self._active_runtime_hash = mcp_config_hash
            self._active_turn_hashes[key] = mcp_config_hash

    def _compose_effective_config(
        self,
        servers: list[dict[str, Any]],
        profile: dict[str, Any],
        *,
        project_cwd: str | None = None,
    ) -> dict[str, Any]:
        if not profile.get("mcpEnabled", False):
            return {"mcp_servers": {}}
        profile_servers = profile.get("servers") if isinstance(profile.get("servers"), dict) else {}
        effective_servers: dict[str, Any] = {}
        for server in servers:
            server_id = str(server.get("serverId") or "").strip()
            if not server_id:
                continue
            thread_settings = profile_servers.get(server_id) if isinstance(profile_servers.get(server_id), dict) else {}
            if not thread_settings.get("enabled", False):
                continue
            effective = self._registry_server_to_codex_config(server)
            if project_cwd and self._is_stdio_server(server):
                effective["cwd"] = project_cwd
                if self._is_filesystem_server(server, effective):
                    effective["args"] = self._filesystem_args_for_project(effective.get("args"), project_cwd)
            enabled_tools = thread_settings.get("enabledTools")
            disabled_tools = thread_settings.get("disabledTools")
            if isinstance(enabled_tools, list) and enabled_tools:
                effective["enabled_tools"] = [str(tool) for tool in enabled_tools if str(tool).strip()]
            if isinstance(disabled_tools, list) and disabled_tools:
                effective["disabled_tools"] = [str(tool) for tool in disabled_tools if str(tool).strip()]
            approval_mode = _codex_tool_approval_mode(thread_settings.get("approvalMode") or profile.get("approvalMode"))
            if approval_mode:
                effective["default_tools_approval_mode"] = approval_mode
            effective_servers[server_id] = effective
        return {"mcp_servers": effective_servers}


    def _resolve_project_cwd(self, project_id: str) -> str | None:
        if self._project_cwd_resolver is None:
            return None
        try:
            raw_path = self._project_cwd_resolver(project_id)
        except Exception as exc:
            raise SessionCoreError(
                code="ERR_MCP_PROJECT_CWD_UNAVAILABLE",
                message="Unable to resolve project workspace folder for MCP server access.",
                status_code=404,
                details={"projectId": project_id},
            ) from exc
        normalized = str(raw_path or "").strip()
        if not normalized:
            raise SessionCoreError(
                code="ERR_MCP_PROJECT_CWD_UNAVAILABLE",
                message="Project workspace folder is empty; MCP server access cannot be scoped.",
                status_code=404,
                details={"projectId": project_id},
            )
        path = Path(normalized).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise SessionCoreError(
                code="ERR_MCP_PROJECT_CWD_UNAVAILABLE",
                message="Project workspace folder does not exist; MCP server access cannot be scoped.",
                status_code=404,
                details={"projectId": project_id, "cwd": str(path)},
            )
        return str(path)

    @staticmethod
    def _is_stdio_server(server: dict[str, Any]) -> bool:
        transport = server.get("transport") if isinstance(server.get("transport"), dict) else {}
        return transport.get("type") == "stdio"

    @staticmethod
    def _is_filesystem_server(server: dict[str, Any], effective: dict[str, Any]) -> bool:
        transport = server.get("transport") if isinstance(server.get("transport"), dict) else {}
        tokens = [
            str(server.get("serverId") or ""),
            str(server.get("name") or ""),
            str(transport.get("command") or effective.get("command") or ""),
            *[str(arg) for arg in effective.get("args", []) if arg is not None],
        ]
        haystack = " ".join(tokens).lower()
        return "server-filesystem" in haystack or "filesystem" in haystack

    @staticmethod
    def _filesystem_args_for_project(raw_args: Any, project_cwd: str) -> list[str]:
        args = [str(arg) for arg in raw_args] if isinstance(raw_args, list) else []
        package_index = next(
            (idx for idx, arg in enumerate(args) if "server-filesystem" in arg.lower()),
            None,
        )
        if package_index is not None:
            return args[: package_index + 1] + [project_cwd]
        return [project_cwd]

    def _registry_server_to_codex_config(self, server: dict[str, Any]) -> dict[str, Any]:
        transport = server.get("transport") if isinstance(server.get("transport"), dict) else {}
        transport_type = transport.get("type")
        if transport_type == "stdio":
            result: dict[str, Any] = {"command": transport.get("command")}
            for key in ("args", "env", "env_vars", "cwd"):
                if transport.get(key) not in (None, [], {}):
                    result[key] = copy.deepcopy(transport[key])
            return result
        if transport_type == "streamable_http":
            result = {"url": transport.get("url")}
            for key in ("bearer_token_env_var", "http_headers", "env_http_headers"):
                if transport.get(key) not in (None, [], {}):
                    result[key] = copy.deepcopy(transport[key])
            return result
        raise SessionCoreError(
            code="ERR_MCP_REGISTRY_INVALID",
            message=f"Unsupported MCP server transport: {transport_type!r}",
            status_code=400,
            details={"serverId": server.get("serverId")},
        )

    def _server_with_health(self, server: dict[str, Any]) -> dict[str, Any]:
        health = self._registry_health_for_server(server)
        next_server = copy.deepcopy(server)
        next_server["health"] = health
        return next_server

    def _registry_health_for_server(self, server: dict[str, Any]) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        transport = server.get("transport") if isinstance(server.get("transport"), dict) else {}
        if transport.get("type") == "stdio":
            command = str(transport.get("command") or "").strip()
            if command and shutil.which(command) is None and not Path(command).exists():
                warnings.append({"code": "COMMAND_MISSING", "message": f"Command not found: {command}"})
        elif transport.get("type") == "streamable_http":
            for key in ("bearer_token_env_var",):
                env_name = str(transport.get(key) or "").strip()
                if env_name and os.environ.get(env_name) is None:
                    warnings.append({"code": "ENV_MISSING", "message": f"Environment variable is not set: {env_name}"})
            env_headers = transport.get("env_http_headers") if isinstance(transport.get("env_http_headers"), dict) else {}
            for env_name in env_headers.values():
                name = str(env_name or "").strip()
                if name and os.environ.get(name) is None:
                    warnings.append({"code": "ENV_MISSING", "message": f"Environment variable is not set: {name}"})
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "installStatus": server.get("installStatus") or "unknown",
            "trustStatus": server.get("trustStatus") or "untrusted",
        }

    def _validate_registry_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        server_id = self._require_id(payload.get("serverId"), "serverId")
        name = str(payload.get("name") or server_id).strip() or server_id
        transport = payload.get("transport") if isinstance(payload.get("transport"), dict) else None
        if transport is None:
            raise self._validation_error("transport is required", "transport")
        transport_type = str(transport.get("type") or "").strip()
        if transport_type not in {"stdio", "streamable_http"}:
            raise self._validation_error("transport.type must be stdio or streamable_http", "transport.type")
        if "bearer_token" in transport:
            raise self._validation_error("inline bearer_token is not allowed; use bearer_token_env_var", "transport.bearer_token")
        allowed_common = {"type"}
        if transport_type == "stdio":
            allowed = allowed_common | {"command", "args", "env", "env_vars", "cwd"}
            unknown = sorted(set(transport) - allowed)
            if unknown:
                raise self._validation_error("stdio transport contains unsupported HTTP fields", "transport")
            if not str(transport.get("command") or "").strip():
                raise self._validation_error("stdio command is required", "transport.command")
        else:
            allowed = allowed_common | {"url", "bearer_token_env_var", "http_headers", "env_http_headers"}
            unknown = sorted(set(transport) - allowed)
            if unknown:
                raise self._validation_error("streamable_http transport contains unsupported stdio fields", "transport")
            url = str(transport.get("url") or "").strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                raise self._validation_error("streamable_http url must start with http:// or https://", "transport.url")
        return {
            "serverId": server_id,
            "name": name,
            "description": str(payload.get("description") or ""),
            "transport": copy.deepcopy(transport),
            "installStatus": str(payload.get("installStatus") or "unknown"),
            "trustStatus": str(payload.get("trustStatus") or "untrusted"),
            "metadata": copy.deepcopy(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
            "updatedAt": iso_now(),
        }

    def _validate_profile(self, profile: dict[str, Any], project_id: str, node_id: str, role: str) -> dict[str, Any]:
        normalized = self._default_profile(project_id, node_id, role)
        normalized["mcpEnabled"] = bool(profile.get("mcpEnabled", False))
        approval_mode = str(profile.get("approvalMode") or "never")
        if approval_mode not in VALID_APPROVAL_MODES:
            raise self._validation_error("unsupported approvalMode", "approvalMode")
        normalized["approvalMode"] = approval_mode
        servers = profile.get("servers") if isinstance(profile.get("servers"), dict) else {}
        next_servers: dict[str, Any] = {}
        for server_id, settings in servers.items():
            if not isinstance(settings, dict):
                continue
            sid = self._require_id(server_id, "serverId")
            next_servers[sid] = {
                "enabled": bool(settings.get("enabled", False)),
                "enabledTools": self._string_list(settings.get("enabledTools")),
                "disabledTools": self._string_list(settings.get("disabledTools")),
                "approvalMode": str(settings.get("approvalMode") or approval_mode),
                "toolApproval": copy.deepcopy(settings.get("toolApproval") if isinstance(settings.get("toolApproval"), dict) else {}),
            }
        normalized["servers"] = next_servers
        normalized["policyOverrides"] = copy.deepcopy(
            profile.get("policyOverrides") if isinstance(profile.get("policyOverrides"), dict) else {}
        )
        normalized["updatedAt"] = iso_now()
        return normalized

    def _default_profile(self, project_id: str, node_id: str, role: str) -> dict[str, Any]:
        return {
            "projectId": self._require_id(project_id, "projectId"),
            "nodeId": self._require_id(node_id, "nodeId"),
            "role": self._normalize_role(role),
            "mcpEnabled": False,
            "approvalMode": "never",
            "servers": {},
            "policyOverrides": {},
            "updatedAt": None,
        }

    def _load_registry_locked(self) -> dict[str, Any]:
        if not self._registry_path.exists():
            return {"schemaVersion": 1, "servers": [], "updatedAt": None}
        payload = self._load_json_file_locked(self._registry_path, default={"schemaVersion": 1, "servers": [], "updatedAt": None})
        if not isinstance(payload, dict):
            return {"schemaVersion": 1, "servers": [], "updatedAt": None}
        servers = payload.get("servers") if isinstance(payload.get("servers"), list) else []
        return {"schemaVersion": 1, "servers": [entry for entry in servers if isinstance(entry, dict)], "updatedAt": payload.get("updatedAt")}

    def _write_registry_locked(self, registry: dict[str, Any]) -> None:
        ensure_dir(self._paths.config_root)
        atomic_write_json(self._registry_path, registry)

    def _load_json_file_locked(self, path: Path, *, default: Any) -> Any:
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._quarantine_corrupt_json_locked(path, exc)
            return copy.deepcopy(default)

    @staticmethod
    def _quarantine_corrupt_json_locked(path: Path, exc: Exception) -> None:
        logger.warning("MCP JSON store is corrupt; using empty defaults", extra={"path": str(path), "reason": str(exc)})
        try:
            quarantine = path.with_name(f"{path.name}.corrupt.{iso_now().replace(':', '-')}")
            path.replace(quarantine)
        except OSError:
            logger.warning("Failed to quarantine corrupt MCP JSON store", extra={"path": str(path)}, exc_info=True)

    def _load_profiles_locked(self) -> dict[str, Any]:
        if not self._profiles_path.exists():
            return {}
        payload = self._load_json_file_locked(self._profiles_path, default={})
        return payload if isinstance(payload, dict) else {}

    def _write_profiles_locked(self, profiles: dict[str, Any]) -> None:
        ensure_dir(self._profiles_path.parent)
        atomic_write_json(self._profiles_path, profiles)

    def _profile_key(self, project_id: str, node_id: str, role: str) -> str:
        return "::".join(
            [self._require_id(project_id, "projectId"), self._require_id(node_id, "nodeId"), self._normalize_role(role)]
        )

    def _normalize_role(self, role: str) -> str:
        normalized = str(role or "").strip()
        if normalized == "ask":
            normalized = "ask_planning"
        if normalized not in VALID_ROLES:
            raise self._validation_error("unsupported thread role", "role")
        return normalized

    @staticmethod
    def _require_id(value: Any, field: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise SessionCoreError(
                code="ERR_MCP_INVALID_REQUEST",
                message=f"{field} is required.",
                status_code=400,
                details={"field": field},
            )
        return normalized

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(entry).strip() for entry in value if str(entry).strip()]

    @staticmethod
    def _validation_error(message: str, field: str) -> SessionCoreError:
        return SessionCoreError(
            code="ERR_MCP_REGISTRY_INVALID",
            message=message,
            status_code=400,
            details={"field": field},
        )


def _codex_tool_approval_mode(value: Any) -> str | None:
    normalized = str(value or "").strip()
    if normalized == "onRequest":
        return "prompt"
    if normalized == "never":
        return "auto"
    return None
