from __future__ import annotations

import json
import time

import pytest

from backend.ai.codex_client import CodexTransportError
from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


class FakeCodexClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "prompt": prompt,
                "thread_id": thread_id,
                "timeout_sec": timeout_sec,
            }
        )
        if not self.outcomes:
            raise AssertionError("No fake Codex outcomes remaining")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        if isinstance(outcome, dict):
            response = dict(outcome)
        else:
            raw_text = str(outcome)
            response = {"stdout": raw_text}
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                response["stdout"] = ""
                response["tool_calls"] = [
                    {
                        "tool_name": "emit_render_data",
                        "arguments": {
                            "kind": "split_result",
                            "payload": payload,
                        },
                    }
                ]
            else:
                response["tool_calls"] = []

        response.setdefault("stdout", "")
        response.setdefault("tool_calls", [])
        response.setdefault("thread_id", thread_id)

        if callable(on_tool_call):
            for tool_call in response["tool_calls"]:
                arguments = tool_call.get("arguments")
                if isinstance(arguments, dict):
                    on_tool_call(str(tool_call.get("tool_name") or ""), arguments)
        return response

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
                    "node_summary": "Split Project",
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


def create_project(client, workspace_root: str) -> tuple[str, str]:
    install_fake_thread_service(client)
    bootstrap_client = FakeCodexClient([])
    client.app.state.brief_generation_service._client = bootstrap_client
    client.app.state.spec_generation_service._client = bootstrap_client
    response = client.patch("/v1/settings/workspace", json={"base_workspace_root": workspace_root})
    assert response.status_code == 200
    snapshot = client.post("/v1/projects", json={"name": "Split Project", "root_goal": "Ship phase 5"}).json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def wait_for_split_completion(client, project_id: str, node_id: str, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        planning = client.app.state.storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
        if planning.get("active_turn_id") is None and str(planning.get("status") or "") != "active":
            response = client.get(f"/v1/projects/{project_id}/snapshot")
            assert response.status_code == 200
            return response.json()
        time.sleep(0.02)
    raise AssertionError(f"split did not complete for {node_id}")


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


def canonical_payload(mode: str, *, title_prefix: str | None = None) -> dict[str, object]:
    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]  # type: ignore[index]
    prefix = title_prefix or mode
    subtasks = []
    for index in range(1, spec["min_items"] + 1):
        subtasks.append(
            {
                "id": f"S{index}",
                "title": f"{prefix} step {index}",
                "objective": f"Objective {index} for {prefix}",
                "why_now": f"Reason {index} for {prefix}",
            }
        )
    return {"subtasks": subtasks}


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


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_split_api_returns_snapshot_with_new_children_for_each_canonical_mode(
    client,
    workspace_root,
    mode: str,
) -> None:
    project_id, root_id = create_project(client, str(workspace_root))
    fake_client = FakeCodexClient(
        [
            json.dumps(canonical_payload(mode, title_prefix=mode)),
        ]
    )
    client.app.state.split_service._codex_client = fake_client

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": mode},
    )

    assert response.status_code == 202
    payload = wait_for_split_completion(client, project_id, root_id)
    nodes = {node["node_id"]: node for node in payload["tree_state"]["node_registry"]}
    root = nodes[root_id]
    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]
    created_child_ids = root["split_metadata"]["created_child_ids"]
    created_children = [nodes[node_id] for node_id in created_child_ids]

    assert fake_client.calls
    assert f"Decompose this node using {spec['label'].lower()} mode." in str(fake_client.calls[0]["prompt"])
    assert root["planning_mode"] == mode
    assert root["split_metadata"]["mode"] == mode
    assert root["split_metadata"]["output_family"] == "flat_subtasks_v1"
    assert root["split_metadata"]["source"] == "ai"
    assert len(created_child_ids) == spec["min_items"]
    assert len(root["split_metadata"]["materialized"]["subtasks"]) == spec["min_items"]
    assert created_children[0]["title"] == f"{mode} step 1"
    assert f"Objective 1 for {mode}" in created_children[0]["description"]
    assert f"Why now: Reason 1 for {mode}" in created_children[0]["description"]
    assert payload["tree_state"]["active_node_id"] == created_child_ids[0]


def test_split_api_allows_locked_node_and_keeps_new_children_locked(client, workspace_root) -> None:
    project_id, root_id = create_project(client, str(workspace_root))
    storage = client.app.state.storage
    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["status"] = "locked"
    storage.project_store.save_snapshot(project_id, snapshot)
    client.app.state.split_service._codex_client = FakeCodexClient(
        [
            json.dumps(canonical_payload("workflow", title_prefix="locked workflow")),
        ]
    )

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": "workflow"},
    )

    assert response.status_code == 202
    payload = wait_for_split_completion(client, project_id, root_id)
    nodes = {node["node_id"]: node for node in payload["tree_state"]["node_registry"]}
    root = nodes[root_id]
    children = [nodes[node_id] for node_id in root["split_metadata"]["created_child_ids"]]
    assert root["status"] == "locked"
    assert [child["status"] for child in children] == ["locked", "locked", "locked"]
    assert payload["tree_state"]["active_node_id"] == children[0]["node_id"]


@pytest.mark.parametrize("mode", ["walking_skeleton", "slice"])
def test_split_api_returns_400_for_legacy_public_modes(client, workspace_root, mode: str) -> None:
    project_id, root_id = create_project(client, str(workspace_root))

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": mode},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


def test_split_api_returns_400_for_invalid_mode(client, workspace_root) -> None:
    project_id, root_id = create_project(client, str(workspace_root))

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": "bad-mode"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_split_api_accepts_canonical_modes_at_route(
    client,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    project_id, root_id = create_project(client, str(workspace_root))
    calls: list[tuple[str, str, str, bool]] = []

    def fake_split_node(project_id_arg: str, node_id_arg: str, mode_arg: str, confirm_replace_arg: bool):
        calls.append((project_id_arg, node_id_arg, mode_arg, confirm_replace_arg))
        return {
            "status": "accepted",
            "node_id": node_id_arg,
            "mode": mode_arg,
            "planning_status": "active",
        }

    monkeypatch.setattr(client.app.state.split_service, "split_node", fake_split_node)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": mode},
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "node_id": root_id,
        "mode": mode,
        "planning_status": "active",
    }
    assert calls == [(project_id, root_id, mode, False)]


def test_split_api_returns_404_for_missing_node(client, workspace_root) -> None:
    project_id, _ = create_project(client, str(workspace_root))

    response = client.post(
        f"/v1/projects/{project_id}/nodes/missing/split",
        json={"mode": "workflow"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "node_not_found"


def test_split_api_requires_confirmation_for_resplit(client, workspace_root) -> None:
    project_id, root_id = create_project(client, str(workspace_root))
    client.app.state.split_service._codex_client = FakeCodexClient(
        [
            json.dumps(canonical_payload("workflow", title_prefix="first workflow")),
        ]
    )
    first = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/split", json={"mode": "workflow"})
    assert first.status_code == 202
    wait_for_split_completion(client, project_id, root_id)

    second = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/split", json={"mode": "workflow"})

    assert second.status_code == 409
    assert second.json()["code"] == "split_not_allowed"


def test_split_api_confirmed_resplit_supersedes_old_children(client, workspace_root) -> None:
    project_id, root_id = create_project(client, str(workspace_root))
    client.app.state.split_service._codex_client = FakeCodexClient(
        [
            json.dumps(canonical_payload("workflow", title_prefix="first workflow")),
            json.dumps(canonical_payload("workflow", title_prefix="second workflow")),
        ]
    )
    first = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/split", json={"mode": "workflow"})
    assert first.status_code == 202
    first_payload = wait_for_split_completion(client, project_id, root_id)
    first_root = next(node for node in first_payload["tree_state"]["node_registry"] if node["node_id"] == root_id)
    first_child_ids = first_root["split_metadata"]["created_child_ids"]

    second = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": "workflow", "confirm_replace": True},
    )

    assert second.status_code == 202
    second_payload = wait_for_split_completion(client, project_id, root_id)
    second_root = next(node for node in second_payload["tree_state"]["node_registry"] if node["node_id"] == root_id)
    second_nodes = {node["node_id"]: node for node in second_payload["tree_state"]["node_registry"]}
    assert second_root["split_metadata"]["revision"] == 2
    assert second_root["split_metadata"]["replaced_child_ids"] == first_child_ids
    assert all(second_nodes[child_id]["is_superseded"] for child_id in first_child_ids)


def test_split_api_marks_failure_when_codex_transport_fails(client, workspace_root) -> None:
    project_id, root_id = create_project(client, str(workspace_root))
    client.app.state.split_service._codex_client = FakeCodexClient(
        [
            CodexTransportError("boom", "rpc_error"),
            CodexTransportError("boom", "rpc_error"),
            CodexTransportError("boom", "rpc_error"),
        ]
    )

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{root_id}/split",
        json={"mode": "workflow"},
    )

    assert response.status_code == 202
    payload = wait_for_split_completion(client, project_id, root_id)
    root = next(node for node in payload["tree_state"]["node_registry"] if node["node_id"] == root_id)
    assert root["split_metadata"] is None
