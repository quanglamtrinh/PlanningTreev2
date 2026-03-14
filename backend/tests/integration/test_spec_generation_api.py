from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError


class FakeCodexClient:
    def __init__(self, generation_outcomes: list[object] | None = None) -> None:
        self.available_threads: set[str] = set()
        self._planning_counter = 0
        self._execution_counter = 0
        self.generation_outcomes = list(generation_outcomes or [])

    def start_planning_thread(
        self,
        *,
        base_instructions: str,
        dynamic_tools,
        cwd: str | None = None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        self._planning_counter += 1
        thread_id = f"planning_{self._planning_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        writable_roots: list[str] | None = None,
    ) -> dict[str, object]:
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        return {"thread_id": thread_id}

    def fork_thread(
        self,
        source_thread_id: str,
        *,
        cwd: str | None = None,
        base_instructions: str | None = None,
        dynamic_tools=None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        if source_thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {source_thread_id}", "rpc_error")
        self._execution_counter += 1
        thread_id = f"execution_{self._execution_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(
        self,
        prompt: str,
        *,
        thread_id: str,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
        on_tool_call=None,
    ) -> dict[str, object]:
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        return {"stdout": "ok", "thread_id": thread_id, "tool_calls": []}

    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
        on_tool_call=None,
    ) -> dict[str, object]:
        if "locked PlanningTree Brief" in prompt:
            payload = {
                "node_snapshot": {
                    "node_summary": "Spec Project",
                    "why_this_node_exists_now": "Ship phase 5",
                    "current_focus": "Review the generated spec.",
                },
                "active_inherited_context": {
                    "active_goals_from_parent": [],
                    "active_constraints_from_parent": [],
                    "active_decisions_in_force": [],
                },
                "accepted_upstream_facts": {
                    "accepted_outputs": [],
                    "available_artifacts": [],
                    "confirmed_dependencies": [],
                },
                "runtime_state": {
                    "status": "ready",
                    "completed_so_far": [],
                    "current_blockers": [],
                    "next_best_action": "Review the generated spec.",
                },
                "pending_escalations": {
                    "open_risks": [],
                    "pending_user_decisions": [],
                    "fallback_direction_if_unanswered": "",
                },
            }
            return {"stdout": json.dumps(payload), "thread_id": thread_id or "brief_thread_1"}

        if "PlanningTree spec draft for a single node" in prompt or "updating a PlanningTree Spec after a planning session" in prompt:
            if self.generation_outcomes:
                outcome = self.generation_outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                if isinstance(outcome, dict):
                    stdout = json.dumps(outcome)
                else:
                    stdout = str(outcome)
                return {"stdout": stdout, "thread_id": thread_id or "spec_thread_1"}

            payload = {
                "mission": {
                    "goal": "Ship phase 5",
                    "success_outcome": "Execution contract is ready.",
                    "implementation_level": "working",
                },
                "scope": {
                    "must_do": ["Deliver the approved node outcome"],
                    "must_not_do": [],
                    "deferred_work": [],
                },
                "constraints": {
                    "hard_constraints": [],
                    "change_budget": "",
                    "touch_boundaries": [],
                    "external_dependencies": [],
                },
                "autonomy": {
                    "allowed_decisions": [],
                    "requires_confirmation": [],
                    "default_policy_when_unclear": "ask_user",
                },
                "verification": {
                    "acceptance_checks": ["Outcome verified"],
                    "definition_of_done": "",
                    "evidence_expected": [],
                },
                "execution_controls": {
                    "quality_profile": "standard",
                    "tooling_limits": [],
                    "output_expectation": "",
                    "conflict_policy": "reopen_spec",
                    "missing_decision_policy": "reopen_spec",
                },
                "assumptions": {
                    "assumptions_in_force": [],
                },
            }
            return {"stdout": json.dumps(payload), "thread_id": thread_id or "spec_thread_1"}

        raise AssertionError(f"Unexpected prompt: {prompt[:80]}")


def attach_fake_client(client: TestClient, fake_client: FakeCodexClient) -> None:
    client.app.state.thread_service._codex_client = fake_client
    client.app.state.chat_service._client = fake_client
    client.app.state.ask_service._client = fake_client
    client.app.state.brief_generation_service._client = fake_client
    client.app.state.spec_generation_service._client = fake_client


def create_project(
    client: TestClient,
    workspace_root: str,
    fake_client: FakeCodexClient,
) -> tuple[str, str]:
    attach_fake_client(client, fake_client)
    workspace_response = client.patch(
        "/v1/settings/workspace",
        json={"base_workspace_root": workspace_root},
    )
    assert workspace_response.status_code == 200
    snapshot = client.post(
        "/v1/projects",
        json={"name": "Spec Project", "root_goal": "Ship phase 5"},
    ).json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def wait_for_node_state(client: TestClient, project_id: str, node_id: str, predicate, *, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    last_state: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/documents/state")
        assert response.status_code == 200
        last_state = response.json()["state"]
        if predicate(last_state):
            return last_state
        time.sleep(0.02)
    raise AssertionError(f"node state did not reach the expected value for {node_id}: {last_state}")


def advance_node_to_spec_review(client: TestClient, project_id: str, node_id: str) -> None:
    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-task")
    assert response.status_code == 202
    wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["phase"] == "spec_review"
        and state["brief_generation_status"] == "ready"
        and state["spec_generation_status"] == "idle"
        and (state["spec_initialized"] or state["spec_generated"]),
    )


def advance_node_to_ready_for_execution(client: TestClient, project_id: str, node_id: str) -> None:
    advance_node_to_spec_review(client, project_id, node_id)
    confirm_spec = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-spec")
    assert confirm_spec.status_code == 200


def test_generate_spec_api_persists_spec_and_state(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_spec_review(client, project_id, node_id)
    fake_client.generation_outcomes.append(
        {
            "mission": {
                "goal": "Generated goal",
                "success_outcome": "Generated outcome",
                "implementation_level": "working",
            },
            "scope": {
                "must_do": ["Generated task"],
                "must_not_do": [],
                "deferred_work": [],
            },
            "constraints": {
                "hard_constraints": [],
                "change_budget": "",
                "touch_boundaries": [],
                "external_dependencies": [],
            },
            "autonomy": {
                "allowed_decisions": [],
                "requires_confirmation": [],
                "default_policy_when_unclear": "ask_user",
            },
            "verification": {
                "acceptance_checks": ["Generated check"],
                "definition_of_done": "",
                "evidence_expected": [],
            },
            "execution_controls": {
                "quality_profile": "standard",
                "tooling_limits": [],
                "output_expectation": "",
                "conflict_policy": "reopen_spec",
                "missing_decision_policy": "reopen_spec",
            },
            "assumptions": {
                "assumptions_in_force": ["Generated assumption"],
            },
        }
    )

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/generate-spec")

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "accepted"
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["spec_generation_status"] == "idle" and state["phase"] == "spec_review",
    )
    assert final_state["spec_generated"] is True
    assert final_state["spec_generation_status"] == "idle"
    persisted_spec = client.app.state.storage.node_store.load_spec(project_id, node_id)
    assert persisted_spec["mission"]["goal"] == "Generated goal"
    assert persisted_spec["verification"]["acceptance_checks"] == ["Generated check"]


def test_generate_spec_api_from_ready_for_execution_steps_back_and_can_reconfirm(
    client: TestClient,
    workspace_root,
) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_ready_for_execution(client, project_id, node_id)
    fake_client.generation_outcomes.append(
        {
            "mission": {
                "goal": "Refreshed goal",
                "success_outcome": "Refreshed outcome",
                "implementation_level": "working",
            },
            "scope": {
                "must_do": ["Refreshed task"],
                "must_not_do": [],
                "deferred_work": [],
            },
            "constraints": {
                "hard_constraints": [],
                "change_budget": "",
                "touch_boundaries": [],
                "external_dependencies": [],
            },
            "autonomy": {
                "allowed_decisions": [],
                "requires_confirmation": [],
                "default_policy_when_unclear": "ask_user",
            },
            "verification": {
                "acceptance_checks": ["Refreshed check"],
                "definition_of_done": "",
                "evidence_expected": [],
            },
            "execution_controls": {
                "quality_profile": "standard",
                "tooling_limits": [],
                "output_expectation": "",
                "conflict_policy": "reopen_spec",
                "missing_decision_policy": "reopen_spec",
            },
            "assumptions": {
                "assumptions_in_force": ["Refreshed assumption"],
            },
        }
    )

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/generate-spec")

    assert response.status_code == 202
    refreshed_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["phase"] == "spec_review"
        and state["spec_generation_status"] == "idle"
        and state["spec_confirmed"] is False,
    )
    assert refreshed_state["phase"] == "spec_review"
    assert refreshed_state["spec_confirmed"] is False

    reconfirm = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-spec")
    assert reconfirm.status_code == 200
    assert reconfirm.json()["state"]["phase"] == "ready_for_execution"


def test_generate_spec_api_rejects_planning_active(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient(
        [
            {
                "business_contract": "unused",
                "technical_contract": "unused",
                "delivery_acceptance": "unused",
                "assumptions": "unused",
            }
        ]
    )
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_spec_review(client, project_id, node_id)
    client.app.state.storage.thread_store.set_planning_status(
        project_id,
        node_id,
        status="active",
        active_turn_id="planturn_1",
    )

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/generate-spec")

    assert response.status_code == 409
    assert response.json()["code"] == "spec_generation_not_allowed"


def test_generate_spec_api_returns_502_for_invalid_model_output(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_spec_review(client, project_id, node_id)
    fake_client.generation_outcomes.extend(["not json", "still not json"])

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/generate-spec")

    assert response.status_code == 202
    state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda current: current["spec_generation_status"] == "failed",
    )
    assert state["spec_generation_status"] == "failed"
    assert state["last_agent_failure"]["operation"] == "generate_spec"
