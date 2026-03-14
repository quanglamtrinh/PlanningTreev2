from __future__ import annotations

import asyncio
import json
import os
import threading
import time

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError
from backend.routes.agent import stream_agent_events


class FakeCodexClient:
    def __init__(
        self,
        generation_outcomes: list[object] | None = None,
        brief_generation_outcomes: list[object] | None = None,
    ) -> None:
        self.available_threads: set[str] = set()
        self._planning_counter = 0
        self._execution_counter = 0
        self.generation_outcomes = list(generation_outcomes or [])
        self.brief_generation_outcomes = list(brief_generation_outcomes or [])

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
            if self.brief_generation_outcomes:
                outcome = self.brief_generation_outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                stdout = json.dumps(outcome) if isinstance(outcome, dict) else str(outcome)
                return {"stdout": stdout, "thread_id": thread_id or "brief_thread_1"}

            payload = {
                "node_snapshot": {
                    "node_summary": "Agent Project",
                    "why_this_node_exists_now": "Ship async UX",
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
                stdout = json.dumps(outcome) if isinstance(outcome, dict) else str(outcome)
                return {"stdout": stdout, "thread_id": thread_id or "spec_thread_1"}

            payload = {
                "mission": {
                    "goal": "Ship async UX",
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
        json={"name": "Agent Project", "root_goal": "Ship async UX"},
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


class _FakeStreamRequest:
    def __init__(self, app) -> None:
        self.app = app
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected


def _start_action_thread(action):
    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["response"] = action()
        except BaseException as exc:  # pragma: no cover - surfaced in caller
            error["exc"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread, result, error


async def _collect_agent_events(client: TestClient, project_id: str, node_id: str, action, terminal_types: set[str]) -> tuple[object, list[dict[str, object]]]:
    broker = client.app.state.agent_event_broker
    queue = broker.subscribe(project_id, node_id)
    thread, result, error = _start_action_thread(action)
    events: list[dict[str, object]] = []
    try:
        deadline = time.time() + 3
        while time.time() < deadline:
            event = await asyncio.wait_for(queue.get(), timeout=max(0.01, deadline - time.time()))
            events.append(event)
            if str(event.get("type") or "") in terminal_types:
                break
    finally:
        broker.unsubscribe(project_id, node_id, queue)

    thread.join(timeout=1)
    if thread.is_alive():
        raise AssertionError("Agent operation request did not finish in time.")
    if "exc" in error:
        raise error["exc"]
    return result.get("response"), events


def test_agent_events_stream_sends_sse_payload(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root), FakeCodexClient())
    broker = client.app.state.agent_event_broker
    payload = {
        "type": "operation_progress",
        "event_seq": 2,
        "node_id": node_id,
        "operation": "brief_pipeline",
        "stage": "generating_brief",
        "message": "Generating Brief.",
        "timestamp": "2026-03-08T00:00:00Z",
    }
    request = _FakeStreamRequest(client.app)

    async def collect_chunk() -> tuple[object, str]:
        response = await stream_agent_events(project_id, node_id, request)
        chunk_task = asyncio.create_task(anext(response.body_iterator))

        deadline = time.time() + 1
        while time.time() < deadline:
            if broker._queues.get((project_id, node_id), set()):
                break
            await asyncio.sleep(0.01)

        broker.publish(project_id, node_id, payload)
        chunk = await asyncio.wait_for(chunk_task, timeout=1)
        request._disconnected = True
        await response.body_iterator.aclose()
        return response, chunk

    response, chunk = asyncio.run(collect_chunk())

    assert response.status_code == 200
    assert "event: message" in chunk
    assert f"data: {json.dumps(payload, ensure_ascii=True)}" in chunk


def test_confirm_task_publishes_agent_started_progress_completed_events(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    response, events = asyncio.run(
        _collect_agent_events(
            client,
            project_id,
            node_id,
            lambda: client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-task"),
            {"operation_completed"},
        )
    )

    assert response is not None
    assert response.status_code == 202
    assert [event["type"] for event in events] == [
        "operation_started",
        "operation_progress",
        "operation_progress",
        "operation_completed",
    ]
    assert [event["stage"] for event in events] == [
        "preparing",
        "generating_brief",
        "drafting_spec",
        "completed",
    ]
    assert all(event["operation"] == "brief_pipeline" for event in events)
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["phase"] == "spec_review" and state["spec_generation_status"] == "idle",
    )
    assert final_state["last_agent_failure"] is None


def test_confirm_task_can_retry_after_brief_generation_failure(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient(brief_generation_outcomes=["not json", "still not json"])
    project_id, node_id = create_project(client, str(workspace_root), fake_client)

    first_response, first_events = asyncio.run(
        _collect_agent_events(
            client,
            project_id,
            node_id,
            lambda: client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-task"),
            {"operation_failed"},
        )
    )

    assert first_response is not None
    assert first_response.status_code == 202
    assert [event["type"] for event in first_events] == [
        "operation_started",
        "operation_progress",
        "operation_failed",
    ]
    failed_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["phase"] == "awaiting_brief" and state["brief_generation_status"] == "failed",
    )
    assert failed_state["task_confirmed"] is True
    assert failed_state["last_agent_failure"]["operation"] == "brief_pipeline"

    retry_response, retry_events = asyncio.run(
        _collect_agent_events(
            client,
            project_id,
            node_id,
            lambda: client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-task"),
            {"operation_completed"},
        )
    )

    assert retry_response is not None
    assert retry_response.status_code == 202
    assert [event["type"] for event in retry_events] == [
        "operation_started",
        "operation_progress",
        "operation_progress",
        "operation_completed",
    ]
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["phase"] == "spec_review" and state["brief_generation_status"] == "ready",
    )
    assert final_state["last_agent_failure"] is None


def test_get_state_recovers_orphaned_brief_generation_without_started_at(
    client: TestClient,
    workspace_root,
) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    storage = client.app.state.storage

    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["phase"] = "awaiting_brief"
    storage.project_store.save_snapshot(project_id, snapshot)

    state = storage.node_store.load_state(project_id, node_id)
    state["task_confirmed"] = True
    state["phase"] = "awaiting_brief"
    state["brief_generation_status"] = "generating"
    state["brief_generation_started_at"] = ""
    state["last_agent_failure"] = None
    storage.node_store.save_state(project_id, node_id, state)

    state_path = storage.node_store.node_dir(project_id, node_id) / "state.yaml"
    stale_age_sec = client.app.state.brief_generation_service._timeout_sec + 45
    stale_mtime = time.time() - stale_age_sec
    os.utime(state_path, (stale_mtime, stale_mtime))

    response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/documents/state")

    assert response.status_code == 200
    recovered_state = response.json()["state"]
    assert recovered_state["brief_generation_status"] == "failed"
    assert recovered_state["phase"] == "awaiting_brief"
    assert recovered_state["last_agent_failure"]["operation"] == "brief_pipeline"


def test_confirm_task_retries_orphaned_brief_generation(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    storage = client.app.state.storage

    snapshot = storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["phase"] = "awaiting_brief"
    storage.project_store.save_snapshot(project_id, snapshot)

    state = storage.node_store.load_state(project_id, node_id)
    state["task_confirmed"] = True
    state["phase"] = "awaiting_brief"
    state["brief_generation_status"] = "generating"
    state["brief_generation_started_at"] = "2026-03-13T00:00:00+00:00"
    state["last_agent_failure"] = None
    storage.node_store.save_state(project_id, node_id, state)

    response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-task")

    assert response.status_code == 202
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda current: current["phase"] == "spec_review"
        and current["brief_generation_status"] == "ready"
        and current["spec_generation_status"] == "idle",
    )
    assert final_state["last_agent_failure"] is None


def test_generate_spec_publishes_agent_failed_event(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_spec_review(client, project_id, node_id)
    fake_client.generation_outcomes.extend(["not json", "still not json"])

    response, events = asyncio.run(
        _collect_agent_events(
            client,
            project_id,
            node_id,
            lambda: client.post(f"/v1/projects/{project_id}/nodes/{node_id}/generate-spec"),
            {"operation_failed"},
        )
    )

    assert response is not None
    assert response.status_code == 202
    assert [event["type"] for event in events] == [
        "operation_started",
        "operation_progress",
        "operation_failed",
    ]
    assert [event["stage"] for event in events] == [
        "preparing",
        "drafting_spec",
        "failed",
    ]
    assert all(event["operation"] == "generate_spec" for event in events)
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["spec_generation_status"] == "failed",
    )
    assert final_state["last_agent_failure"]["operation"] == "generate_spec"
