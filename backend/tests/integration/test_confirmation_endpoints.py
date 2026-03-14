from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError


class FakeCodexClient:
    def __init__(self) -> None:
        self.available_threads: set[str] = set()
        self._planning_counter = 0
        self._execution_counter = 0

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
        if "status, assistant_markdown, questions, plan_markdown" in prompt:
            payload = {
                "status": "plan_ready",
                "assistant_markdown": "The plan is ready.",
                "questions": [],
                "plan_markdown": "1. Execute the approved work.\n2. Verify the outcome.",
            }
            return {"stdout": __import__("json").dumps(payload), "thread_id": thread_id, "tool_calls": []}
        if "status, assistant_summary" in prompt:
            payload = {
                "status": "completed",
                "assistant_summary": "Executed the current plan.",
            }
            return {"stdout": __import__("json").dumps(payload), "thread_id": thread_id, "tool_calls": []}
        return {"stdout": "ok", "thread_id": thread_id, "tool_calls": []}

    def send_prompt_streaming(
        self,
        prompt: str,
        thread_id: str | None = None,
        timeout_sec: int = 120,
        cwd: str | None = None,
        writable_roots: list[str] | None = None,
        on_delta=None,
    ) -> dict[str, object]:
        if "locked PlanningTree Brief" in prompt:
            payload = {
                "node_snapshot": {
                    "node_summary": "Alpha",
                    "why_this_node_exists_now": "Ship phase 5",
                    "current_focus": "Prepare the node handoff.",
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
                    "next_best_action": "Review and confirm the agent-recommended Spec draft.",
                },
                "pending_escalations": {
                    "open_risks": [],
                    "pending_user_decisions": [],
                    "fallback_direction_if_unanswered": "",
                },
            }
            return {"stdout": __import__("json").dumps(payload), "thread_id": thread_id or "thread_1"}
        if "PlanningTree spec draft for a single node" in prompt or "updating a PlanningTree Spec after a planning session" in prompt:
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
            return {"stdout": __import__("json").dumps(payload), "thread_id": thread_id or "thread_1"}
        if callable(on_delta):
            on_delta("hello world")
        return {"stdout": "hello world", "thread_id": thread_id or "thread_1"}


def attach_fake_client(client: TestClient, fake_client: FakeCodexClient) -> None:
    client.app.state.thread_service._codex_client = fake_client
    client.app.state.chat_service._client = fake_client
    client.app.state.brief_generation_service._client = fake_client
    client.app.state.spec_generation_service._client = fake_client


def confirmable_spec_payload() -> dict[str, object]:
    return {
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


def create_project(client: TestClient, workspace_root: str) -> tuple[str, str]:
    attach_fake_client(client, FakeCodexClient())
    workspace_response = client.patch(
        "/v1/settings/workspace",
        json={"base_workspace_root": workspace_root},
    )
    assert workspace_response.status_code == 200
    snapshot = client.post(
        "/v1/projects",
        json={"name": "Confirm Project", "root_goal": "Ship phase 5"},
    ).json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def wait_for_node_state(
    client: TestClient,
    project_id: str,
    node_id: str,
    predicate,
    *,
    timeout: float = 3.0,
) -> dict:
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


def advance_node_to_ready_for_execution(client: TestClient, project_id: str, node_id: str) -> None:
    confirm_task = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-task")
    assert confirm_task.status_code == 202
    wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["phase"] == "spec_review"
        and state["brief_generation_status"] == "ready"
        and state["spec_generation_status"] == "idle"
        and (state["spec_initialized"] or state["spec_generated"]),
    )
    spec_update = client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/spec",
        json=confirmable_spec_payload(),
    )
    assert spec_update.status_code == 200
    confirm_spec = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-spec")
    assert confirm_spec.status_code == 200


def test_confirm_endpoints_advance_phase_in_state_and_snapshot(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    task_response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-task")
    assert task_response.status_code == 202
    assert task_response.json()["state"]["phase"] == "awaiting_brief"
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["phase"] == "spec_review"
        and state["brief_generation_status"] == "ready"
        and state["spec_generation_status"] == "idle"
        and (state["spec_initialized"] or state["spec_generated"]),
    )
    assert final_state["phase"] == "spec_review"

    spec_update = client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/spec",
        json=confirmable_spec_payload(),
    )
    assert spec_update.status_code == 200

    spec_response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-spec")
    assert spec_response.status_code == 200
    assert spec_response.json()["state"]["phase"] == "ready_for_execution"

    snapshot = client.get(f"/v1/projects/{project_id}/snapshot").json()
    root = next(node for node in snapshot["tree_state"]["node_registry"] if node["node_id"] == node_id)
    assert root["phase"] == "ready_for_execution"


def test_execute_rejects_before_ready_for_execution(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/execute")

    assert response.status_code == 409
    assert response.json()["code"] == "plan_execute_not_allowed"


def test_plan_then_execute_succeeds_from_ready_for_execution(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    advance_node_to_ready_for_execution(client, project_id, node_id)

    plan_response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/plan/start")
    assert plan_response.status_code == 202
    assert plan_response.json()["status"] == "accepted"
    wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["plan_status"] == "ready" and state["run_status"] == "idle",
    )

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/execute")

    assert response.status_code == 200
    snapshot = client.get(f"/v1/projects/{project_id}/snapshot").json()
    root = next(node for node in snapshot["tree_state"]["node_registry"] if node["node_id"] == node_id)
    assert root["phase"] == "executing"


def test_chat_messages_cannot_bypass_execution_guard(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "node_update_not_allowed"


def test_complete_rejects_before_lifecycle_readiness(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    storage = client.app.state.storage
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = "ready"
    storage.project_store.save_snapshot(project_id, snapshot)

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/complete")

    assert response.status_code == 409
    assert response.json()["code"] == "complete_not_allowed"


def test_complete_rejects_locked_node(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    storage = client.app.state.storage
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = "locked"
    storage.project_store.save_snapshot(project_id, snapshot)

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/complete")

    assert response.status_code == 409
    assert response.json()["code"] == "complete_not_allowed"
