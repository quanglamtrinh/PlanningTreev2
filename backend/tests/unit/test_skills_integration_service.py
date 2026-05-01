
from __future__ import annotations

import pytest

from backend.config.app_config import build_app_paths
from backend.session_core_v2.errors import SessionCoreError
from backend.skills import SkillIntegrationService


class FakeProtocol:
    def __init__(self, data: list[dict] | None = None) -> None:
        self.requests: list[dict] = []
        self.data = data or []
        self.config_writes: list[dict] = []

    def skills_list(self, params: dict) -> dict:
        self.requests.append(params)
        return {"data": self.data}

    def config_batch_write(self, params: dict) -> dict:
        self.config_writes.append(params)
        return {}


def skill(path: str, *, name: str = "planning-brief", enabled: bool = True, scope: str = "repo") -> dict:
    return {
        "name": name,
        "description": "Plan work",
        "path": path,
        "scope": scope,
        "enabled": enabled,
        "dependencies": {"tools": []},
    }


def test_profile_persistence_and_exact_skill_path_validation(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    service = SkillIntegrationService(build_app_paths(tmp_path / "appdata"), project_cwd_resolver=lambda _project_id: str(project_root))
    skill_path = str(project_root / ".codex" / "skills" / "planning" / "SKILL.md")

    response = service.write_profile(
        "project-1",
        "node-1",
        "root",
        {
            "skillsEnabled": True,
            "skills": {
                skill_path: {
                    "enabled": True,
                    "activationMode": "alwaysOnForRole",
                    "name": "planning",
                    "scope": "repo",
                }
            },
        },
    )

    assert response["profile"]["role"] == "root"
    assert response["profile"]["skillsEnabled"] is True
    assert skill_path in response["profile"]["skills"]
    reopened = SkillIntegrationService(build_app_paths(tmp_path / "appdata"), project_cwd_resolver=lambda _project_id: str(project_root))
    assert reopened.read_profile("project-1", "node-1", "root")["skills"][skill_path]["name"] == "planning"

    with pytest.raises(SessionCoreError) as exc:
        service.write_profile("project-1", "node-1", "root", {"skills": {str(project_root / ".codex" / "skills" / "planning"): {}}})
    assert exc.value.code == "ERR_SKILLS_INVALID_REQUEST"


def test_registry_uses_explicit_project_cwd(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    protocol = FakeProtocol(data=[{"cwd": str(project_root), "skills": [], "errors": []}])
    service = SkillIntegrationService(build_app_paths(tmp_path / "appdata"), project_cwd_resolver=lambda _project_id: str(project_root))

    response = service.list_registry("project-1", force_reload=True, protocol_client=protocol)

    assert response["catalogCwd"] == str(project_root.resolve())
    assert protocol.requests == [{"cwds": [str(project_root.resolve())], "forceReload": True}]


def test_effective_skills_classifies_active_disabled_missing_and_manual(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    active_path = str(project_root / ".codex" / "skills" / "active" / "SKILL.md")
    disabled_path = str(project_root / ".codex" / "skills" / "disabled" / "SKILL.md")
    missing_path = str(project_root / ".codex" / "skills" / "missing" / "SKILL.md")
    manual_path = str(project_root / ".codex" / "skills" / "manual" / "SKILL.md")
    protocol = FakeProtocol(
        data=[
            {
                "cwd": str(project_root.resolve()),
                "skills": [skill(active_path, name="active"), skill(disabled_path, name="disabled", enabled=False), skill(manual_path, name="manual")],
                "errors": [],
            }
        ]
    )
    service = SkillIntegrationService(build_app_paths(tmp_path / "appdata"), project_cwd_resolver=lambda _project_id: str(project_root))
    service.write_profile(
        "project-1",
        "node-1",
        "execution",
        {
            "skillsEnabled": True,
            "skills": {
                active_path: {"enabled": True, "activationMode": "alwaysOnForRole", "name": "active"},
                disabled_path: {"enabled": True, "activationMode": "alwaysOnForRole", "name": "disabled"},
                missing_path: {"enabled": True, "activationMode": "alwaysOnForRole", "name": "missing"},
                manual_path: {"enabled": True, "activationMode": "manual", "name": "manual"},
            },
        },
    )

    preview = service.preview_effective_skills("project-1", "node-1", "execution", protocol_client=protocol)

    effective = preview["effectiveSkills"]
    assert [entry["name"] for entry in effective["active"]] == ["active"]
    assert effective["blocked"] == [{"skillPath": disabled_path, "name": "disabled", "reason": "disabledByCodexConfig"}]
    assert effective["missing"] == [{"skillPath": missing_path, "name": "missing", "reason": "missingFromCatalog"}]
    assert effective["skipped"] == [{"skillPath": manual_path, "name": "manual", "reason": "manual"}]


def test_prepare_turn_start_appends_skill_items_and_never_writes_config(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    skill_path = str(project_root / ".codex" / "skills" / "planning" / "SKILL.md")
    protocol = FakeProtocol(data=[{"cwd": str(project_root.resolve()), "skills": [skill(skill_path, name="planning")], "errors": []}])
    service = SkillIntegrationService(build_app_paths(tmp_path / "appdata"), project_cwd_resolver=lambda _project_id: str(project_root))
    service.write_profile(
        "project-1",
        "node-1",
        "execution",
        {"skillsEnabled": True, "skills": {skill_path: {"enabled": True, "activationMode": "alwaysOnForRole", "name": "planning"}}},
    )

    prepared = service.prepare_turn_start(
        thread_id="thread-1",
        payload={
            "input": [{"type": "text", "text": "Implement"}],
            "skillsContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"},
        },
        protocol_client=protocol,
    )

    assert prepared["input"] == [
        {"type": "text", "text": "Implement"},
        {"type": "skill", "name": "planning", "path": skill_path},
    ]
    assert "skillsContext" not in prepared
    assert prepared["metadata"]["skillsEffectiveSummary"]["skillPaths"] == [skill_path]
    assert protocol.config_writes == []


def test_prepare_turn_start_rejects_cwd_mismatch(tmp_path) -> None:
    project_root = tmp_path / "project"
    other_root = tmp_path / "other"
    project_root.mkdir()
    other_root.mkdir()
    service = SkillIntegrationService(build_app_paths(tmp_path / "appdata"), project_cwd_resolver=lambda _project_id: str(project_root))

    with pytest.raises(SessionCoreError) as exc:
        service.prepare_turn_start(
            thread_id="thread-1",
            payload={
                "cwd": str(other_root),
                "input": [],
                "skillsContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"},
            },
            protocol_client=FakeProtocol(),
        )
    assert exc.value.code == "ERR_SKILLS_CWD_MISMATCH"
