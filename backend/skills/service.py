
from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.config.app_config import AppPaths
from backend.session_core_v2.errors import SessionCoreError
from backend.storage.file_utils import atomic_write_json, ensure_dir, iso_now

VALID_ROLES = {"ask_planning", "execution", "audit", "package_review", "root"}
VALID_ACTIVATION_MODES = {"alwaysOnForRole", "manual"}
logger = logging.getLogger(__name__)


def canonical_skills_config_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SkillIntegrationService:
    def __init__(self, paths: AppPaths, project_cwd_resolver: Callable[[str], str] | None = None) -> None:
        self._paths = paths
        self._project_cwd_resolver = project_cwd_resolver
        self._profiles_path = paths.data_root / "skills_profiles.json"
        self._lock = threading.RLock()

    def list_registry(self, project_id: str, *, force_reload: bool = False, protocol_client: Any) -> dict[str, Any]:
        project_cwd = self._resolve_project_cwd(project_id)
        response = self._skills_list(protocol_client, project_cwd=project_cwd, force_reload=force_reload)
        return {"projectId": project_id, "catalogCwd": project_cwd, "data": response.get("data", [])}

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

    def preview_effective_skills(
        self,
        project_id: str,
        node_id: str,
        role: str,
        *,
        thread_id: str | None = None,
        protocol_client: Any,
    ) -> dict[str, Any]:
        profile = self.read_profile(project_id, node_id, role)
        project_cwd = self._resolve_project_cwd(project_id)
        registry = self._skills_list(protocol_client, project_cwd=project_cwd, force_reload=False)
        effective = self._effective_skills(profile, registry, project_cwd=project_cwd)
        skills_hash = canonical_skills_config_hash(effective)
        return {
            "projectId": project_id,
            "nodeId": node_id,
            "role": self._normalize_role(role),
            "threadId": thread_id,
            "profile": profile,
            "skillsConfigHash": skills_hash,
            "effectiveSkills": effective,
        }

    def prepare_turn_start(self, *, thread_id: str, payload: dict[str, Any], protocol_client: Any) -> dict[str, Any]:
        context = payload.get("skillsContext") if isinstance(payload.get("skillsContext"), dict) else None
        if context is None:
            return dict(payload)
        project_id = self._require_id(context.get("projectId"), "projectId")
        node_id = self._require_id(context.get("nodeId"), "nodeId")
        role = self._normalize_role(str(context.get("role") or ""))
        project_cwd = self._resolve_project_cwd(project_id)
        explicit_cwd = str(payload.get("cwd") or "").strip()
        if explicit_cwd:
            try:
                explicit_resolved = str(Path(explicit_cwd).expanduser().resolve())
            except OSError:
                explicit_resolved = explicit_cwd
            if explicit_resolved != project_cwd:
                raise SessionCoreError(
                    code="ERR_SKILLS_CWD_MISMATCH",
                    message="skillsContext requires turn cwd to match the project workspace folder.",
                    status_code=400,
                    details={"threadId": thread_id, "projectId": project_id, "cwd": explicit_resolved, "projectCwd": project_cwd},
                )
        profile = self.read_profile(project_id, node_id, role)
        next_payload = dict(payload)
        next_payload.pop("skillsContext", None)
        if not profile.get("skillsEnabled", False):
            metadata = dict(next_payload.get("metadata")) if isinstance(next_payload.get("metadata"), dict) else {}
            metadata["skillsCatalogCwd"] = project_cwd
            metadata["skillsEffectiveSummary"] = {"skillCount": 0, "skillNames": [], "skillPaths": [], "warningsCount": 0}
            metadata["skillsConfigHash"] = canonical_skills_config_hash({"catalogCwd": project_cwd, "active": []})
            next_payload["metadata"] = metadata
            return next_payload
        registry = self._skills_list(protocol_client, project_cwd=project_cwd, force_reload=False)
        effective = self._effective_skills(profile, registry, project_cwd=project_cwd)
        active = effective["active"]
        existing_paths = {
            str(item.get("path") or "")
            for item in next_payload.get("input", [])
            if isinstance(item, dict) and item.get("type") == "skill"
        }
        input_items = list(next_payload.get("input") if isinstance(next_payload.get("input"), list) else [])
        for skill in active:
            path = str(skill.get("path") or "")
            if not path or path in existing_paths:
                continue
            input_items.append({"type": "skill", "name": str(skill.get("name") or ""), "path": path})
            existing_paths.add(path)
        next_payload["input"] = input_items
        metadata = dict(next_payload.get("metadata")) if isinstance(next_payload.get("metadata"), dict) else {}
        warnings_count = len(effective["blocked"]) + len(effective["missing"])
        metadata["skillsCatalogCwd"] = project_cwd
        metadata["skillsEffectiveSummary"] = {
            "skillCount": len(active),
            "skillNames": [str(skill.get("name") or "") for skill in active],
            "skillPaths": [str(skill.get("path") or "") for skill in active],
            "warningsCount": warnings_count,
        }
        metadata["skillsConfigHash"] = canonical_skills_config_hash(effective)
        next_payload["metadata"] = metadata
        return next_payload

    def _skills_list(self, protocol_client: Any, *, project_cwd: str, force_reload: bool) -> dict[str, Any]:
        method = getattr(protocol_client, "skills_list", None)
        if not callable(method):
            raise SessionCoreError(
                code="ERR_SKILLS_LIST_UNSUPPORTED",
                message="Skills registry requires a Codex app-server version that supports skills/list.",
                status_code=502,
                details={"method": "skills/list"},
            )
        response = method({"cwds": [project_cwd], "forceReload": bool(force_reload)})
        if not isinstance(response, dict):
            return {"data": []}
        data = response.get("data") if isinstance(response.get("data"), list) else []
        return {"data": [entry for entry in data if isinstance(entry, dict)]}

    def _effective_skills(self, profile: dict[str, Any], registry: dict[str, Any], *, project_cwd: str) -> dict[str, Any]:
        catalog = self._catalog_by_path(registry)
        active: list[dict[str, Any]] = []
        blocked: list[dict[str, str]] = []
        missing: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        profile_skills = profile.get("skills") if isinstance(profile.get("skills"), dict) else {}
        seen_paths: set[str] = set()
        for skill_path, settings in sorted(profile_skills.items(), key=lambda entry: str(entry[0])):
            path = self._require_skill_path(skill_path)
            if path in seen_paths:
                continue
            seen_paths.add(path)
            item = settings if isinstance(settings, dict) else {}
            name = str(item.get("name") or "")
            if not item.get("enabled", False):
                skipped.append({"skillPath": path, "name": name, "reason": "profileDisabled"})
                continue
            if item.get("activationMode") != "alwaysOnForRole":
                skipped.append({"skillPath": path, "name": name, "reason": "manual"})
                continue
            metadata = catalog.get(path)
            if metadata is None:
                missing.append({"skillPath": path, "name": name, "reason": "missingFromCatalog"})
                continue
            if metadata.get("enabled") is False:
                blocked.append({"skillPath": path, "name": str(metadata.get("name") or name), "reason": "disabledByCodexConfig"})
                continue
            active.append(copy.deepcopy(metadata))
        return {"catalogCwd": project_cwd, "active": active, "blocked": blocked, "missing": missing, "skipped": skipped}

    @staticmethod
    def _catalog_by_path(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for entry in registry.get("data", []):
            if not isinstance(entry, dict):
                continue
            skills = entry.get("skills") if isinstance(entry.get("skills"), list) else []
            for skill in skills:
                if not isinstance(skill, dict):
                    continue
                path = str(skill.get("path") or "").strip()
                if path and path not in result:
                    result[path] = skill
        return result

    def _validate_profile(self, profile: dict[str, Any], project_id: str, node_id: str, role: str) -> dict[str, Any]:
        normalized = self._default_profile(project_id, node_id, role)
        normalized["skillsEnabled"] = bool(profile.get("skillsEnabled", False))
        skills = profile.get("skills") if isinstance(profile.get("skills"), dict) else {}
        next_skills: dict[str, Any] = {}
        for raw_path, settings in skills.items():
            skill_path = self._require_skill_path(raw_path)
            item = settings if isinstance(settings, dict) else {}
            activation_mode = str(item.get("activationMode") or "alwaysOnForRole")
            if activation_mode not in VALID_ACTIVATION_MODES:
                raise self._validation_error("unsupported activationMode", "activationMode")
            next_skills[skill_path] = {
                "enabled": bool(item.get("enabled", False)),
                "activationMode": activation_mode,
                "name": str(item.get("name") or ""),
                "scope": str(item.get("scope") or "") or None,
                "updatedAt": str(item.get("updatedAt") or iso_now()),
            }
        normalized["skills"] = next_skills
        normalized["updatedAt"] = iso_now()
        return normalized

    def _default_profile(self, project_id: str, node_id: str, role: str) -> dict[str, Any]:
        return {
            "projectId": self._require_id(project_id, "projectId"),
            "nodeId": self._require_id(node_id, "nodeId"),
            "role": self._normalize_role(role),
            "skillsEnabled": False,
            "skills": {},
            "updatedAt": None,
        }

    def _resolve_project_cwd(self, project_id: str) -> str:
        if self._project_cwd_resolver is None:
            raise SessionCoreError(
                code="ERR_SKILLS_PROJECT_CWD_UNAVAILABLE",
                message="Unable to resolve project workspace folder for skills.",
                status_code=404,
                details={"projectId": project_id},
            )
        try:
            raw_path = self._project_cwd_resolver(project_id)
        except Exception as exc:
            raise SessionCoreError(
                code="ERR_SKILLS_PROJECT_CWD_UNAVAILABLE",
                message="Unable to resolve project workspace folder for skills.",
                status_code=404,
                details={"projectId": project_id},
            ) from exc
        normalized = str(raw_path or "").strip()
        if not normalized:
            raise SessionCoreError(
                code="ERR_SKILLS_PROJECT_CWD_UNAVAILABLE",
                message="Project workspace folder is empty; skills cannot be scoped.",
                status_code=404,
                details={"projectId": project_id},
            )
        path = Path(normalized).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise SessionCoreError(
                code="ERR_SKILLS_PROJECT_CWD_UNAVAILABLE",
                message="Project workspace folder does not exist; skills cannot be scoped.",
                status_code=404,
                details={"projectId": project_id, "cwd": str(path)},
            )
        return str(path)

    def _load_profiles_locked(self) -> dict[str, Any]:
        if not self._profiles_path.exists():
            return {}
        try:
            with self._profiles_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._quarantine_corrupt_json_locked(self._profiles_path, exc)
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_profiles_locked(self, profiles: dict[str, Any]) -> None:
        ensure_dir(self._profiles_path.parent)
        atomic_write_json(self._profiles_path, profiles)

    @staticmethod
    def _quarantine_corrupt_json_locked(path: Path, exc: Exception) -> None:
        logger.warning("Skills JSON store is corrupt; using empty defaults", extra={"path": str(path), "reason": str(exc)})
        try:
            quarantine = path.with_name(f"{path.name}.corrupt.{iso_now().replace(':', '-')}")
            path.replace(quarantine)
        except OSError:
            logger.warning("Failed to quarantine corrupt skills JSON store", extra={"path": str(path)}, exc_info=True)

    def _profile_key(self, project_id: str, node_id: str, role: str) -> str:
        return "::".join([self._require_id(project_id, "projectId"), self._require_id(node_id, "nodeId"), self._normalize_role(role)])

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
                code="ERR_SKILLS_INVALID_REQUEST",
                message=f"{field} is required.",
                status_code=400,
                details={"field": field},
            )
        return normalized

    @staticmethod
    def _require_skill_path(value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise SessionCoreError(
                code="ERR_SKILLS_INVALID_REQUEST",
                message="skillPath is required.",
                status_code=400,
                details={"field": "skillPath"},
            )
        path = Path(normalized)
        if not path.is_absolute():
            raise SessionCoreError(
                code="ERR_SKILLS_INVALID_REQUEST",
                message="skillPath must be an absolute path to SKILL.md.",
                status_code=400,
                details={"field": "skillPath", "skillPath": normalized},
            )
        if path.name.lower() != "skill.md":
            raise SessionCoreError(
                code="ERR_SKILLS_INVALID_REQUEST",
                message="skillPath must point to SKILL.md, not the skill folder.",
                status_code=400,
                details={"field": "skillPath", "skillPath": normalized},
            )
        return normalized

    @staticmethod
    def _validation_error(message: str, field: str) -> SessionCoreError:
        return SessionCoreError(
            code="ERR_SKILLS_INVALID_REQUEST",
            message=message,
            status_code=400,
            details={"field": field},
        )
