from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from backend.business.workflow_v2.thread_binding import ThreadBindingServiceV2

_TERMINAL_TURN_STATUSES = {"completed", "failed", "interrupted"}


class WorkflowArtifactTurnError(RuntimeError):
    pass


class WorkflowArtifactTurnRunnerV2:
    def __init__(
        self,
        *,
        thread_binding_service: ThreadBindingServiceV2,
        session_manager: Any,
        timeout_sec: int,
    ) -> None:
        self._thread_binding_service = thread_binding_service
        self._session_manager = session_manager
        self._timeout_sec = int(timeout_sec)

    def ensure_ask_thread(
        self,
        *,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
        artifact_kind: str,
    ) -> str:
        response = self._thread_binding_service.ensure_thread(
            project_id=project_id,
            node_id=node_id,
            role="ask_planning",
            idempotency_key=f"artifact:{artifact_kind}:ensure-ask:{uuid4().hex}",
        )
        thread_id = _thread_id_from_ensure_response(response)
        if not thread_id:
            raise WorkflowArtifactTurnError("Workflow V2 ask thread binding did not return a thread id.")
        if workspace_root:
            try:
                self._session_manager.thread_resume(thread_id=thread_id, payload={"cwd": workspace_root})
            except Exception:
                # ensure_thread already validates/creates the binding. Resume is best-effort hydration.
                pass
        return thread_id

    def refresh_ask_context(
        self,
        *,
        project_id: str,
        node_id: str,
        artifact_kind: str,
    ) -> None:
        self._thread_binding_service.ensure_thread(
            project_id=project_id,
            node_id=node_id,
            role="ask_planning",
            idempotency_key=f"artifact:{artifact_kind}:context-refresh:{uuid4().hex}",
        )

    def run_prompt(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        prompt: str,
        artifact_kind: str,
        cwd: str | None,
        output_schema: dict[str, Any] | None = None,
        sandbox_policy: str | dict[str, Any] | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        client_action_id = f"artifact:{artifact_kind}:turn:{uuid4().hex}"
        payload: dict[str, Any] = {
            "clientActionId": client_action_id,
            "input": [{"type": "text", "text": prompt}],
            "metadata": {
                "workflowInternal": True,
                "workflowInternalKind": "artifact_generation",
                "artifactKind": artifact_kind,
                "projectId": project_id,
                "nodeId": node_id,
            },
        }
        if cwd:
            payload["cwd"] = cwd
        if output_schema is not None:
            payload["outputSchema"] = output_schema
        if sandbox_policy is not None:
            payload["sandboxPolicy"] = sandbox_policy

        response = self._session_manager.turn_start(thread_id=thread_id, payload=payload)
        turn = response.get("turn") if isinstance(response, dict) else None
        turn_id = str(turn.get("id") or "").strip() if isinstance(turn, dict) else ""
        if not turn_id:
            raise WorkflowArtifactTurnError("Session Core V2 did not return an artifact generation turn id.")

        completed_turn = self._wait_for_terminal_turn(
            thread_id=thread_id,
            turn_id=turn_id,
            timeout_sec=timeout_sec if timeout_sec is not None else self._timeout_sec,
        )
        status = str(completed_turn.get("status") or "")
        if status != "completed":
            error = completed_turn.get("error")
            raise WorkflowArtifactTurnError(f"Artifact generation turn ended with status {status!r}: {error!r}")
        return _result_from_turn(completed_turn)

    def _wait_for_terminal_turn(self, *, thread_id: str, turn_id: str, timeout_sec: int) -> dict[str, Any]:
        deadline = time.monotonic() + max(1, timeout_sec)
        last_turn: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            turn = self._session_manager.get_runtime_turn(thread_id=thread_id, turn_id=turn_id)
            if isinstance(turn, dict):
                last_turn = turn
                if str(turn.get("status") or "") in _TERMINAL_TURN_STATUSES:
                    return turn
            time.sleep(0.2)
        raise WorkflowArtifactTurnError(f"Timed out waiting for artifact generation turn {turn_id!r}: {last_turn!r}")


def _thread_id_from_ensure_response(response: dict[str, Any]) -> str | None:
    binding = response.get("binding") if isinstance(response, dict) else None
    if isinstance(binding, dict):
        thread_id = str(binding.get("threadId") or "").strip()
        if thread_id:
            return thread_id
    workflow_state = response.get("workflowState") if isinstance(response, dict) else None
    threads = workflow_state.get("threads") if isinstance(workflow_state, dict) else None
    if isinstance(threads, dict):
        thread_id = str(threads.get("askPlanning") or "").strip()
        if thread_id:
            return thread_id
    return None


def _result_from_turn(turn: dict[str, Any]) -> dict[str, Any]:
    stdout_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in turn.get("items") or []:
        if not isinstance(item, dict):
            continue
        if _is_agent_output_item(item):
            text = _item_text(item)
            if text:
                stdout_parts.append(text)
        for tool_call in _item_tool_calls(item):
            tool_calls.append(tool_call)
    return {
        "stdout": "\n".join(part for part in stdout_parts if part).strip(),
        "tool_calls": tool_calls,
        "turn": turn,
    }


def _item_text(item: dict[str, Any]) -> str:
    for key in ("text", "output", "aggregatedOutput", "stdout"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    content = item.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for entry in content:
            if not isinstance(entry, dict):
                continue
            value = entry.get("text")
            if isinstance(value, str):
                parts.append(value)
        return "\n".join(parts).strip()
    return ""


def _is_agent_output_item(item: dict[str, Any]) -> bool:
    item_type = str(item.get("type") or item.get("kind") or "").strip()
    if item_type in {"agentMessage", "assistantMessage"}:
        return True
    if item_type in {"userMessage", "reasoning", "systemMessage"}:
        return False
    # Legacy/fake transports may omit the type but still expose output fields.
    return any(isinstance(item.get(key), str) and item.get(key).strip() for key in ("text", "output", "aggregatedOutput", "stdout"))


def _item_tool_calls(item: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("tool_calls", "toolCalls"):
        value = item.get(key)
        if isinstance(value, list):
            return [dict(entry) for entry in value if isinstance(entry, dict)]
    return []
