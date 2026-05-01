
from __future__ import annotations

from typing import Any

from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.protocol import SessionProtocolClientV2
from backend.session_core_v2.storage import RuntimeStoreV2
from backend.session_core_v2.thread_store import ThreadMetadataStore, ThreadRolloutRecorder


class _FakeTransport:
    def __init__(self, skill_path: str) -> None:
        self.skill_path = skill_path
        self.notification_handler = None
        self.server_request_handler = None
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def set_notification_handler(self, handler) -> None:  # noqa: ANN001
        self.notification_handler = handler

    def set_server_request_handler(self, handler) -> None:  # noqa: ANN001
        self.server_request_handler = handler

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: int | None = None) -> dict[str, Any]:
        del timeout_sec
        payload = params or {}
        self.requests.append((method, payload))
        if method == "skills/list":
            cwd = payload.get("cwds", [""])[0]
            return {
                "data": [
                    {
                        "cwd": cwd,
                        "skills": [
                            {
                                "name": "planning",
                                "description": "Plan work",
                                "path": self.skill_path,
                                "scope": "repo",
                                "enabled": True,
                                "dependencies": {"tools": []},
                            }
                        ],
                        "errors": [],
                    }
                ]
            }
        if method == "turn/start":
            return {"turn": {"id": "turn-1", "status": "inProgress", "items": [], "error": None}}
        return {}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        del method, params


class _FakeSkillsService:
    def __init__(self, skill_path: str, project_cwd: str) -> None:
        self.skill_path = skill_path
        self.project_cwd = project_cwd

    def prepare_turn_start(self, *, thread_id: str, payload: dict[str, Any], protocol_client: Any) -> dict[str, Any]:
        del thread_id
        protocol_client.skills_list({"cwds": [self.project_cwd], "forceReload": False})
        next_payload = dict(payload)
        next_payload.pop("skillsContext", None)
        next_payload["input"] = list(payload["input"]) + [{"type": "skill", "name": "planning", "path": self.skill_path}]
        metadata = dict(next_payload.get("metadata") or {})
        metadata["skillsCatalogCwd"] = self.project_cwd
        metadata["skillsEffectiveSummary"] = {"skillCount": 1, "skillNames": ["planning"], "skillPaths": [self.skill_path], "warningsCount": 0}
        next_payload["metadata"] = metadata
        return next_payload


def test_session_manager_turn_start_preserves_structured_skill_activation_contract(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    skill_path = str(project_root / ".codex" / "skills" / "planning" / "SKILL.md")
    transport = _FakeTransport(skill_path)
    protocol = SessionProtocolClientV2(transport)  # type: ignore[arg-type]
    state_machine = ConnectionStateMachine()
    state_machine.set_connecting()
    state_machine.set_initialized(client_name="PlanningTree", server_version="1.0.0")
    rollout_root = tmp_path / "rollouts"
    metadata_store = ThreadMetadataStore(db_path=tmp_path / "thread_metadata.sqlite3", rollout_root=rollout_root)
    manager = SessionManagerV2(
        protocol_client=protocol,
        runtime_store=RuntimeStoreV2(),
        connection_state_machine=state_machine,
        thread_rollout_recorder=ThreadRolloutRecorder(metadata_store=metadata_store),
        skills_service=_FakeSkillsService(skill_path, str(project_root.resolve())),
    )

    response = manager.turn_start(
        thread_id="thread-1",
        payload={
            "input": [{"type": "text", "text": "Implement"}],
            "skillsContext": {"projectId": "project-1", "nodeId": "node-1", "role": "execution"},
        },
    )

    assert response["turn"]["metadata"]["skillsEffectiveSummary"]["skillPaths"] == [skill_path]
    assert transport.requests[0] == ("skills/list", {"cwds": [str(project_root.resolve())], "forceReload": False})
    assert transport.requests[1][0] == "turn/start"
    assert transport.requests[1][1]["input"] == [
        {"type": "text", "text": "Implement"},
        {"type": "skill", "name": "planning", "path": skill_path},
    ]
    assert "skillsContext" not in transport.requests[1][1]
    assert "metadata" not in transport.requests[1][1]
