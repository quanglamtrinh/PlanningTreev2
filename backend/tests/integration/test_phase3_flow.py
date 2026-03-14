from __future__ import annotations

import time


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


class FakeGenerationClient:
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
                    "why_this_node_exists_now": "Ship phase 3",
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
                    "next_best_action": "Review the generated spec.",
                },
                "pending_escalations": {
                    "open_risks": [],
                    "pending_user_decisions": [],
                    "fallback_direction_if_unanswered": "",
                },
            }
            return {"stdout": __import__("json").dumps(payload), "thread_id": thread_id or "brief_thread_1"}
        if "PlanningTree spec draft for a single node" in prompt or "updating a PlanningTree Spec after a planning session" in prompt:
            payload = {
                "mission": {
                    "goal": "Ship phase 3",
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
            return {"stdout": __import__("json").dumps(payload), "thread_id": thread_id or "spec_thread_1"}
        raise AssertionError(f"Unexpected prompt: {prompt[:80]}")


def install_fake_thread_service(client) -> None:
    storage = client.app.state.storage
    thread_service = client.app.state.thread_service

    def initialize_root_planning_thread(project_id: str) -> dict:
        snapshot = storage.project_store.load_snapshot(project_id)
        root_id = str(snapshot["tree_state"]["root_node_id"])
        root = internal_nodes(snapshot)[root_id]
        root["planning_thread_id"] = "planning_root"
        root["planning_thread_forked_from_node"] = None
        root["planning_thread_bootstrapped_at"] = None
        storage.project_store.save_snapshot(project_id, snapshot)
        state = storage.node_store.load_state(project_id, root_id)
        state["planning_thread_id"] = "planning_root"
        storage.node_store.save_state(project_id, root_id, state)
        storage.thread_store.set_planning_status(
            project_id,
            root_id,
            thread_id="planning_root",
            forked_from_node=None,
            status="idle",
            active_turn_id=None,
        )
        return snapshot

    def ensure_planning_thread(project_id: str, node_id: str, *, source_node_id: str | None = None) -> str:
        snapshot = storage.project_store.load_snapshot(project_id)
        node = internal_nodes(snapshot)[node_id]
        thread_id = str(node.get("planning_thread_id") or f"planning_{node_id[:8]}")
        node["planning_thread_id"] = thread_id
        node["planning_thread_forked_from_node"] = source_node_id
        storage.project_store.save_snapshot(project_id, snapshot)
        state = storage.node_store.load_state(project_id, node_id)
        state["planning_thread_id"] = thread_id
        state["planning_thread_forked_from_node"] = source_node_id or ""
        storage.node_store.save_state(project_id, node_id, state)
        storage.thread_store.set_planning_status(
            project_id,
            node_id,
            thread_id=thread_id,
            forked_from_node=source_node_id,
            status="idle",
            active_turn_id=None,
        )
        return thread_id

    def fork_planning_thread(project_id: str, source_node_id: str, target_node_id: str) -> str:
        return ensure_planning_thread(project_id, target_node_id, source_node_id=source_node_id)

    thread_service.initialize_root_planning_thread = initialize_root_planning_thread
    thread_service.ensure_planning_thread = ensure_planning_thread
    thread_service.fork_planning_thread = fork_planning_thread
    generation_client = FakeGenerationClient()
    client.app.state.brief_generation_service._client = generation_client
    client.app.state.spec_generation_service._client = generation_client


def advance_node_to_ready_for_execution(
    client,
    project_id: str,
    node_id: str,
    *,
    title: str,
    purpose: str,
) -> None:
    update = client.patch(
        f"/v1/projects/{project_id}/nodes/{node_id}",
        json={"title": title, "description": purpose},
    )
    assert update.status_code == 200
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
    confirm_spec = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-spec")
    assert confirm_spec.status_code == 200


def wait_for_node_state(client, project_id: str, node_id: str, predicate, *, timeout: float = 3.0) -> dict:
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


def test_phase3_api_flow(client, workspace_root) -> None:
    install_fake_thread_service(client)
    bootstrap = client.get("/v1/bootstrap/status")
    assert bootstrap.status_code == 200
    assert bootstrap.json() == {"ready": False, "workspace_configured": False}

    blocked = client.post("/v1/projects", json={"name": "Alpha", "root_goal": "Ship phase 3"})
    assert blocked.status_code == 412

    workspace_response = client.patch(
        "/v1/settings/workspace",
        json={"base_workspace_root": str(workspace_root)},
    )
    assert workspace_response.status_code == 200
    assert workspace_response.json()["base_workspace_root"] == str(workspace_root.resolve())

    settings = client.get("/v1/settings/workspace")
    assert settings.status_code == 200
    assert settings.json()["base_workspace_root"] == str(workspace_root.resolve())

    create_project = client.post(
        "/v1/projects",
        json={"name": "Alpha", "root_goal": "Ship phase 3"},
    )
    assert create_project.status_code == 200
    snapshot = create_project.json()
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]

    list_projects = client.get("/v1/projects")
    assert list_projects.status_code == 200
    assert list_projects.json()[0]["id"] == project_id

    first_child = client.post(
        f"/v1/projects/{project_id}/nodes",
        json={"parent_id": root_id},
    )
    assert first_child.status_code == 200
    first_snapshot = first_child.json()
    first_child_id = first_snapshot["tree_state"]["active_node_id"]

    second_child = client.post(
        f"/v1/projects/{project_id}/nodes",
        json={"parent_id": root_id},
    )
    assert second_child.status_code == 200
    second_snapshot = second_child.json()
    second_child_id = second_snapshot["tree_state"]["active_node_id"]

    advance_node_to_ready_for_execution(
        client,
        project_id,
        first_child_id,
        title="Implement graph",
        purpose="Port the legacy shell.",
    )
    advance_node_to_ready_for_execution(
        client,
        project_id,
        second_child_id,
        title="Harden graph",
        purpose="Lock down the sibling flow.",
    )

    active = client.patch(
        f"/v1/projects/{project_id}/active-node",
        json={"active_node_id": first_child_id},
    )
    assert active.status_code == 200
    assert active.json()["tree_state"]["active_node_id"] == first_child_id

    first_complete = client.post(f"/v1/projects/{project_id}/nodes/{first_child_id}/complete")
    assert first_complete.status_code == 200
    first_complete_snapshot = first_complete.json()
    first_complete_children = {
        node["node_id"]: node
        for node in first_complete_snapshot["tree_state"]["node_registry"]
        if node["parent_id"] == root_id
    }
    assert first_complete_snapshot["tree_state"]["active_node_id"] == second_child_id
    assert first_complete_children[first_child_id]["status"] == "done"
    assert first_complete_children[second_child_id]["status"] == "ready"

    second_complete = client.post(f"/v1/projects/{project_id}/nodes/{second_child_id}/complete")
    assert second_complete.status_code == 200
    second_complete_snapshot = second_complete.json()
    root_node = next(
        node
        for node in second_complete_snapshot["tree_state"]["node_registry"]
        if node["node_id"] == root_id
    )
    assert root_node["status"] == "done"

    reloaded = client.get(f"/v1/projects/{project_id}/snapshot")
    assert reloaded.status_code == 200
    assert reloaded.json()["tree_state"] == second_complete_snapshot["tree_state"]
