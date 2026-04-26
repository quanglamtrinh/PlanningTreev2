from __future__ import annotations

from typing import Any

from backend.business.workflow_v2.artifact_turn_runner import WorkflowArtifactTurnRunnerV2


class FakeBindingService:
    def __init__(self) -> None:
        self.ensures: list[dict[str, Any]] = []

    def ensure_thread(self, **kwargs: Any) -> dict[str, Any]:
        self.ensures.append(dict(kwargs))
        return {"binding": {"threadId": "v2-ask-thread"}}


class FakeSessionManager:
    def __init__(self) -> None:
        self.resumes: list[dict[str, Any]] = []
        self.starts: list[dict[str, Any]] = []

    def thread_resume(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.resumes.append({"threadId": thread_id, "payload": dict(payload)})
        return {"thread": {"id": thread_id}}

    def turn_start(self, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.starts.append({"threadId": thread_id, "payload": dict(payload)})
        return {"turn": {"id": "turn-1", "status": "inProgress", "items": []}}

    def get_runtime_turn(self, *, thread_id: str, turn_id: str) -> dict[str, Any]:
        return {
            "id": turn_id,
            "threadId": thread_id,
            "status": "completed",
            "items": [
                {
                    "id": "item-user",
                    "type": "userMessage",
                    "content": [{"type": "text", "text": "Generate frame prompt that is not JSON"}],
                },
                {
                    "id": "item-reasoning",
                    "type": "reasoning",
                    "content": [{"type": "text", "text": "Internal reasoning that should be ignored"}],
                },
                {
                    "id": "item-1",
                    "type": "agentMessage",
                    "text": '{"content":"Generated frame"}',
                }
            ],
            "metadata": {
                "workflowInternal": True,
                "artifactKind": "frame",
            },
        }


def test_artifact_turn_runner_uses_v2_ask_thread_and_internal_metadata() -> None:
    binding = FakeBindingService()
    session = FakeSessionManager()
    runner = WorkflowArtifactTurnRunnerV2(
        thread_binding_service=binding,  # type: ignore[arg-type]
        session_manager=session,
        timeout_sec=5,
    )

    thread_id = runner.ensure_ask_thread(
        project_id="project-1",
        node_id="node-1",
        workspace_root="/tmp/project",
        artifact_kind="frame",
    )
    result = runner.run_prompt(
        project_id="project-1",
        node_id="node-1",
        thread_id=thread_id,
        prompt="Generate frame",
        artifact_kind="frame",
        cwd="/tmp/project",
        output_schema={"type": "object"},
    )

    assert thread_id == "v2-ask-thread"
    assert binding.ensures[0]["role"] == "ask_planning"
    assert session.starts[0]["threadId"] == "v2-ask-thread"
    payload = session.starts[0]["payload"]
    assert payload["metadata"]["workflowInternal"] is True
    assert payload["metadata"]["artifactKind"] == "frame"
    assert payload["outputSchema"] == {"type": "object"}
    assert result["stdout"] == '{"content":"Generated frame"}'
