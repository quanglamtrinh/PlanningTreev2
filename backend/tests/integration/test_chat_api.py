from __future__ import annotations

import asyncio
import json
import threading
import time

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError, RuntimeRequestRecord
from backend.routes.chat import stream_chat_events


class FakeCodexClient:
    def __init__(self, *, block_event: threading.Event | None = None) -> None:
        self.block_event = block_event
        self.started = threading.Event()
        self.available_threads: set[str] = set()
        self._planning_counter = 0
        self._execution_counter = 0
        self._plan_turn_counter = 0
        self._pending_requests: dict[str, dict[str, object]] = {}
        self._request_answers: dict[str, dict[str, object]] = {}

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
        on_plan_delta=None,
        on_request_user_input=None,
        on_request_resolved=None,
        on_thread_status=None,
        output_schema=None,
    ) -> dict[str, object]:
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        if "You are the PlanningTree planner for a single node." in prompt:
            self._plan_turn_counter += 1
            turn_id = f"turn_plan_{self._plan_turn_counter}"
            payload = {
                "kind": "plan_ready",
                "assistant_summary": "The plan is ready.",
            }
            return {
                "stdout": json.dumps(payload),
                "thread_id": thread_id,
                "tool_calls": [],
                "turn_id": turn_id,
                "turn_status": "completed",
                "final_plan_item": {
                    "id": f"plan_item_{turn_id}",
                    "text": "1. Execute the approved work.\n2. Verify the outcome.",
                    "turn_id": turn_id,
                    "thread_id": thread_id,
                },
                "runtime_request_ids": [],
            }
        if "status, assistant_summary" in prompt:
            payload = {
                "status": "completed",
                "assistant_summary": "Executed the current plan.",
            }
            return {"stdout": json.dumps(payload), "thread_id": thread_id, "tool_calls": []}
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
                    "why_this_node_exists_now": "Ship phase 4",
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
            return {"stdout": json.dumps(payload), "thread_id": thread_id or "thread_1"}
        if "PlanningTree spec draft for a single node" in prompt or "updating a PlanningTree Spec after a planning session" in prompt:
            payload = {
                "mission": {
                    "goal": "Ship phase 4",
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
            return {"stdout": json.dumps(payload), "thread_id": thread_id or "thread_1"}
        if callable(on_delta):
            on_delta("hello ")
        self.started.set()
        if self.block_event is not None:
            self.block_event.wait(timeout=5)
        if callable(on_delta):
            on_delta("world")
        return {"stdout": "hello world", "thread_id": thread_id or "thread_1"}

    def list_loaded_threads(self, *, timeout_sec: int = 30, limit: int | None = None) -> dict[str, object]:
        data = sorted(self.available_threads)
        if limit is not None:
          data = data[:limit]
        return {"data": data, "nextCursor": None}

    def read_thread(
        self,
        thread_id: str,
        *,
        include_turns: bool = False,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        status = {"type": "idle" if thread_id in self.available_threads else "notLoaded"}
        return {"thread": {"id": thread_id, "status": status, "turns": []}}

    def resolve_runtime_request_user_input(
        self,
        request_id: str,
        *,
        answers: dict[str, object],
    ) -> RuntimeRequestRecord | None:
        pending = self._pending_requests.get(request_id)
        if pending is None:
            return None
        self._request_answers[request_id] = {"answers": answers}
        event = pending["event"]
        if isinstance(event, threading.Event):
            event.set()
        return RuntimeRequestRecord(
            request_id=request_id,
            rpc_request_id=request_id,
            thread_id=str(pending["thread_id"]),
            turn_id=str(pending["turn_id"]),
            node_id=None,
            item_id=str(pending["item_id"]),
            prompt_payload={},
            status="resolved",
        )


class StreamingPlanCodexClient(FakeCodexClient):
    def __init__(
        self,
        *,
        block_event: threading.Event | None = None,
        plan_outcomes: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(block_event=block_event)
        self.plan_outcomes = list(plan_outcomes or [])

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
        on_plan_delta=None,
        on_request_user_input=None,
        on_request_resolved=None,
        on_thread_status=None,
        output_schema=None,
    ) -> dict[str, object]:
        if "You are the PlanningTree planner for a single node." not in prompt:
            return super().run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=timeout_sec,
                cwd=cwd,
                writable_roots=writable_roots,
                on_delta=on_delta,
                on_tool_call=on_tool_call,
                on_plan_delta=on_plan_delta,
                on_request_user_input=on_request_user_input,
                on_request_resolved=on_request_resolved,
                on_thread_status=on_thread_status,
                output_schema=output_schema,
            )
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        self._plan_turn_counter += 1
        turn_id = f"turn_plan_{self._plan_turn_counter}"
        outcome = self.plan_outcomes.pop(0) if self.plan_outcomes else {
            "final_result": {
                "kind": "plan_ready",
                "assistant_summary": "The plan is ready.",
            },
            "final_plan_text": "1. Execute the approved work.\n2. Verify the outcome.",
        }
        runtime_request_ids: list[str] = []
        if isinstance(outcome, dict) and isinstance(outcome.get("request"), dict):
            request = outcome["request"]
            request_id = str(request.get("request_id") or f"req_{turn_id}")
            runtime_request_ids.append(request_id)
            wait_event = threading.Event()
            self._pending_requests[request_id] = {
                "thread_id": thread_id,
                "turn_id": turn_id,
                "item_id": str(request.get("item_id") or f"item_{turn_id}"),
                "event": wait_event,
            }
            if callable(on_request_user_input):
                on_request_user_input(
                    {
                        "request_id": request_id,
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "item_id": str(request.get("item_id") or f"item_{turn_id}"),
                        "questions": list(request.get("questions") or []),
                        "status": "pending",
                        "created_at": "2026-03-13T20:00:00Z",
                    }
                )
            wait_event.wait(timeout=5)
            if callable(on_request_resolved):
                on_request_resolved(
                    {
                        "request_id": request_id,
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "status": "resolved" if request_id in self._request_answers else "stale",
                        "resolved_at": "2026-03-13T20:00:05Z",
                    }
                )
        final_result = (
            outcome.get("final_result")
            if isinstance(outcome, dict) and isinstance(outcome.get("final_result"), dict)
            else {
                "kind": "plan_ready",
                "assistant_summary": "The plan is ready.",
            }
        )
        final_plan_text = (
            str(outcome.get("final_plan_text") or "").strip()
            if isinstance(outcome, dict)
            else ""
        )
        if not final_plan_text and final_result.get("kind") == "plan_ready":
            final_plan_text = "1. Execute the approved work.\n2. Verify the outcome."
        return {
            "stdout": json.dumps(final_result),
            "thread_id": thread_id,
            "tool_calls": [],
            "turn_id": turn_id,
            "turn_status": "completed",
            "final_plan_item": (
                {
                    "id": f"plan_item_{turn_id}",
                    "text": final_plan_text,
                    "turn_id": turn_id,
                    "thread_id": thread_id,
                }
                if final_result.get("kind") == "plan_ready"
                else None
            ),
            "runtime_request_ids": runtime_request_ids,
        }


def attach_fake_client(client: TestClient, fake_client: FakeCodexClient) -> None:
    client.app.state.chat_service._client = fake_client
    client.app.state.thread_service._codex_client = fake_client
    client.app.state.brief_generation_service._client = fake_client
    client.app.state.spec_generation_service._client = fake_client


def confirmable_spec_payload() -> dict[str, object]:
    return {
        "mission": {
            "goal": "Ship phase 4",
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


def create_project(
    client: TestClient,
    workspace_root: str,
    fake_client: FakeCodexClient | None = None,
) -> tuple[str, str]:
    attach_fake_client(client, fake_client or FakeCodexClient())
    response = client.patch(
        "/v1/settings/workspace",
        json={"base_workspace_root": workspace_root},
    )
    assert response.status_code == 200
    snapshot = client.post(
        "/v1/projects",
        json={"name": "Chat Project", "root_goal": "Ship phase 4"},
    ).json()
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def wait_for_idle(client: TestClient, project_id: str, node_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/chat/session")
        assert response.status_code == 200
        session = response.json()["session"]
        if session["active_turn_id"] is None:
            return session
        time.sleep(0.02)
    raise AssertionError(f"chat session did not become idle for {node_id}")


def wait_for_node_state(client: TestClient, project_id: str, node_id: str, predicate, timeout: float = 3.0) -> dict:
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


def _start_request_thread(action):
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


async def _collect_chat_events(client: TestClient, project_id: str, node_id: str, action, terminal_types: set[str]) -> tuple[object, list[dict[str, object]]]:
    broker = client.app.state.chat_event_broker
    queue = broker.subscribe(project_id, node_id)
    thread, result, error = _start_request_thread(action)
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
        raise AssertionError("Chat request did not finish in time.")
    if "exc" in error:
        raise error["exc"]
    return result.get("response"), events


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


def advance_node_to_executing(client: TestClient, project_id: str, node_id: str) -> None:
    advance_node_to_ready_for_execution(client, project_id, node_id)
    client.app.state.node_service.advance_to_executing(project_id, node_id)


def test_get_chat_session_returns_normalized_empty_state(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))

    response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/chat/session")

    assert response.status_code == 200
    payload = response.json()["session"]
    assert payload["project_id"] == project_id
    assert payload["node_id"] == node_id
    assert payload["event_seq"] == 0
    assert payload["messages"] == []


def test_send_message_and_reset_flow(client: TestClient, workspace_root) -> None:
    fake_client = FakeCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_executing(client, project_id, node_id)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 200
    session = wait_for_idle(client, project_id, node_id)
    assert session["event_seq"] == 4
    assert session["messages"][-1]["status"] == "completed"
    assert "thread_id" not in session

    reset = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/chat/reset")
    assert reset.status_code == 200
    assert reset.json()["session"]["event_seq"] == 5
    assert reset.json()["session"]["messages"] == []
    assert "thread_id" not in reset.json()["session"]


def test_get_chat_session_keeps_live_turn_active(client: TestClient, workspace_root) -> None:
    release = threading.Event()
    fake_client = FakeCodexClient(block_event=release)
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_executing(client, project_id, node_id)

    response = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 200
    assert fake_client.started.wait(timeout=1)

    session_response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/chat/session")
    assert session_response.status_code == 200
    session = session_response.json()["session"]
    assert session["active_turn_id"] is not None
    assert session["messages"][-1]["status"] in {"pending", "streaming"}
    assert session["messages"][-1]["error"] is None

    release.set()
    completed = wait_for_idle(client, project_id, node_id)
    assert completed["messages"][-1]["status"] == "completed"
    assert completed["messages"][-1]["content"] == "hello world"


class _FakeStreamRequest:
    def __init__(self, app) -> None:
        self.app = app
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected


def test_chat_events_stream_sends_sse_payload(client: TestClient, workspace_root) -> None:
    project_id, node_id = create_project(client, str(workspace_root))
    broker = client.app.state.chat_event_broker
    payload = {
        "type": "assistant_delta",
        "event_seq": 4,
        "message_id": "msg_1",
        "delta": "hi",
        "content": "hi",
        "updated_at": "2026-03-08T00:00:00Z",
    }
    request = _FakeStreamRequest(client.app)

    async def collect_chunk() -> tuple[object, str]:
        response = await stream_chat_events(project_id, node_id, request)
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


def test_plan_start_emits_message_created_then_completed(client: TestClient, workspace_root) -> None:
    fake_client = StreamingPlanCodexClient()
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_ready_for_execution(client, project_id, node_id)

    response, events = asyncio.run(
        _collect_chat_events(
            client,
            project_id,
            node_id,
            lambda: client.post(f"/v1/projects/{project_id}/nodes/{node_id}/plan/start"),
            {"assistant_completed"},
        )
    )

    assert response is not None
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert events[0]["type"] == "message_created"
    assert events[-1]["type"] == "assistant_completed"
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["plan_status"] == "ready" and state["run_status"] == "idle",
    )
    assert final_state["last_agent_failure"] is None


def test_plan_message_returns_accepted_and_streams_follow_up_delta(client: TestClient, workspace_root) -> None:
    fake_client = StreamingPlanCodexClient(
        plan_outcomes=[
            {
                "request": {
                    "request_id": "req_brand_direction",
                    "item_id": "item_brand_direction",
                    "questions": [
                        {
                            "id": "brand_direction",
                            "header": "Brand direction",
                            "question": (
                                "What visual style or brand direction should the site shell follow? "
                                "This is not a minor preference: it would materially change layout, typography, "
                                "navigation emphasis, and the kind of result the user expects. "
                                "Assuming wrong would likely create rework and user dissatisfaction."
                            ),
                            "isOther": False,
                            "isSecret": False,
                            "options": [
                                {
                                    "label": "Warm bistro",
                                    "description": "Inviting, understated, and neighborhood-focused.",
                                }
                            ],
                        }
                    ],
                },
                "final_result": {
                    "kind": "plan_ready",
                    "assistant_summary": "The plan is ready.",
                },
                "final_plan_text": "1. Execute the approved work.\n2. Verify the outcome.",
            },
        ]
    )
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_ready_for_execution(client, project_id, node_id)

    start_response = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/plan/start")
    assert start_response.status_code == 202
    wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["plan_status"] == "waiting_on_input"
        and state["run_status"] == "planning",
    )
    session_payload = client.get(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/session"
    ).json()["session"]
    pending_request = session_payload["pending_input_request"]
    assert pending_request["questions"][0]["header"] == "Brand direction"
    assert "materially change" in pending_request["questions"][0]["question"]

    response, events = asyncio.run(
        _collect_chat_events(
            client,
            project_id,
            node_id,
            lambda: client.post(
                f"/v1/projects/{project_id}/nodes/{node_id}/plan/input/{pending_request['request_id']}/resolve",
                json={
                    "thread_id": pending_request["thread_id"],
                    "turn_id": pending_request["turn_id"],
                    "answers": {
                        "brand_direction": {
                            "answers": [
                                "Use a warm, modern neighborhood bistro style with understated typography."
                            ]
                        }
                    },
                },
            ),
            {"assistant_completed"},
        )
    )

    assert response is not None
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert events[0]["type"] == "plan_input_resolved"
    assert events[-1]["type"] == "assistant_completed"
    final_state = wait_for_node_state(
        client,
        project_id,
        node_id,
        lambda state: state["plan_status"] == "ready"
        and state["run_status"] == "idle"
        and state["bound_plan_input_version"] == state["active_plan_input_version"],
    )
    assert final_state["last_agent_failure"] is None


def test_chat_route_returns_404_for_missing_node(client: TestClient, workspace_root) -> None:
    project_id, _ = create_project(client, str(workspace_root))

    response = client.get(f"/v1/projects/{project_id}/nodes/missing/chat/session")

    assert response.status_code == 404
    assert response.json()["code"] == "node_not_found"


def test_invalid_project_id_returns_structured_400(client: TestClient) -> None:
    response = client.get("/v1/projects/not-a-project-id/snapshot")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_project_id"


def test_chat_rejects_concurrent_turns(client: TestClient, workspace_root) -> None:
    release = threading.Event()
    fake_client = FakeCodexClient(block_event=release)
    project_id, node_id = create_project(client, str(workspace_root), fake_client)
    advance_node_to_executing(client, project_id, node_id)

    first = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/messages",
        json={"content": "hello"},
    )
    assert first.status_code == 200
    assert fake_client.started.wait(timeout=1)

    second = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/messages",
        json={"content": "again"},
    )

    assert second.status_code == 409
    assert second.json()["code"] == "chat_turn_already_active"

    release.set()
    wait_for_idle(client, project_id, node_id)
