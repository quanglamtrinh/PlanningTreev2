from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.thread_lineage_service import _ROLLOUT_BOOTSTRAP_PROMPT
from backend.tests.conftest import init_git_repo
from backend.tests.integration.test_phase5_execution_audit_rehearsal import (
    _confirm_spec,
    _do_lazy_split,
    _setup_project,
)


class WorkflowV2ReviewContextCodexClient:
    def __init__(self) -> None:
        self.started_threads: list[dict[str, object]] = []
        self.resumed_threads: list[dict[str, object]] = []
        self.forked_threads: list[dict[str, object]] = []
        self.review_calls: list[dict[str, object]] = []

    def start_thread(self, **kwargs: object) -> dict[str, str]:
        thread_id = f"workflow-v2-thread-{len(self.started_threads) + 1}"
        self.started_threads.append({"thread_id": thread_id, **kwargs})
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **kwargs: object) -> dict[str, str]:
        self.resumed_threads.append({"thread_id": thread_id, **kwargs})
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **kwargs: object) -> dict[str, str]:
        thread_id = f"workflow-v2-fork-{len(self.forked_threads) + 1}"
        self.forked_threads.append(
            {"thread_id": thread_id, "source_thread_id": source_thread_id, **kwargs}
        )
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        thread_id = str(kwargs.get("thread_id") or "")
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": thread_id, "turn_status": "completed"}

        cwd = kwargs.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            Path(cwd, "execution-output.txt").write_text("done\n", encoding="utf-8")
        return {"stdout": "Implemented the task.", "thread_id": thread_id, "turn_status": "completed"}

    def start_review_streaming(self, **kwargs: object) -> dict[str, object]:
        self.review_calls.append(dict(kwargs))
        thread_id = str(kwargs.get("thread_id") or "")
        return {
            "review_thread_id": thread_id,
            "review_turn_id": "workflow-v2-review-turn-1",
            "review": "Looks good.",
            "review_disposition": "approved",
            "turn_status": "completed",
        }


def _set_workflow_v2_codex_client(app, codex_client: object) -> None:
    app.state.codex_client = codex_client
    app.state.chat_service._codex_client = codex_client
    app.state.thread_lineage_service._codex_client = codex_client
    app.state.thread_query_service_v2._codex_client = codex_client
    app.state.thread_runtime_service_v2._codex_client = codex_client
    app.state.finish_task_service._codex_client = codex_client
    app.state.review_service._codex_client = codex_client
    app.state.execution_audit_workflow_service_v2._codex_client = codex_client


def _wait_for(predicate, *, timeout_sec: float = 5.0):
    deadline = time.monotonic() + timeout_sec
    last_value = None
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        last_value = value
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for condition. Last value: {last_value!r}")


def _workflow_state(client: TestClient, project_id: str, node_id: str) -> dict[str, object]:
    response = client.get(f"/v2/projects/{project_id}/nodes/{node_id}/workflow-state")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    return payload["data"]


def _persisted_workflow_state(app, project_id: str, node_id: str) -> dict[str, object]:
    state = app.state.storage.workflow_state_store.read_state(project_id, node_id)
    assert isinstance(state, dict)
    return state


def _detail_state(client: TestClient, project_id: str, node_id: str) -> dict[str, object]:
    response = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/detail-state")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def test_first_review_cycle_uses_detached_thread_with_project_workspace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    init_git_repo(workspace_root)

    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)
    monkeypatch.delenv("PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "1")

    app = create_app(data_root=tmp_path / "appdata")
    codex_client = WorkflowV2ReviewContextCodexClient()
    _set_workflow_v2_codex_client(app, codex_client)

    with TestClient(app) as client:
        project_id, root_id = _setup_project(client, workspace_root)
        child_id, _ = _do_lazy_split(app.state.storage, project_id, root_id)
        _confirm_spec(app.state.storage, project_id, child_id)

        finish_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/finish-task",
            json={"idempotencyKey": "finish-task-test"},
        )
        assert finish_response.status_code == 200

        execution_state = _wait_for(
            lambda: next(
                (
                    state
                    for state in [_workflow_state(client, project_id, child_id)]
                    if state.get("workflowPhase") == "execution_decision_pending"
                ),
                None,
            )
        )
        execution_decision = execution_state.get("currentExecutionDecision")
        assert isinstance(execution_decision, dict)
        candidate_workspace_hash = str(execution_decision.get("candidateWorkspaceHash") or "")
        assert candidate_workspace_hash

        review_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/review-in-audit",
            json={
                "idempotencyKey": "review-in-audit-test",
                "expectedWorkspaceHash": candidate_workspace_hash,
            },
        )
        assert review_response.status_code == 200
        review_payload = review_response.json()
        assert review_payload["ok"] is True

        audit_state = _wait_for(
            lambda: next(
                (
                    state
                    for state in [_workflow_state(client, project_id, child_id)]
                    if state.get("workflowPhase") == "audit_decision_pending"
                ),
                None,
            )
        )

        review_cycles = app.state.storage.review_cycle_store.read_cycles(project_id, child_id)
        assert len(review_cycles) == 1
        review_cycle = review_cycles[0]
        assert review_cycle["deliveryKind"] == "detached"
        persisted_workflow_state = _persisted_workflow_state(app, project_id, child_id)
        latest_commit = persisted_workflow_state.get("latestCommit")
        assert isinstance(latest_commit, dict)
        assert latest_commit["sourceAction"] == "review_in_audit"
        assert latest_commit["headSha"] == review_cycle["reviewCommitSha"]
        assert isinstance(latest_commit["commitMessage"], str) and latest_commit["commitMessage"]
        assert isinstance(latest_commit["committed"], bool)
        assert isinstance(latest_commit["recordedAt"], str) and latest_commit["recordedAt"]
        first_latest_commit = dict(latest_commit)
        detail_after_review = _detail_state(client, project_id, child_id)
        assert detail_after_review["initial_sha"] == first_latest_commit["initialSha"]
        assert detail_after_review["head_sha"] == first_latest_commit["headSha"]
        assert detail_after_review["commit_message"] == first_latest_commit["commitMessage"]

        retry_review_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/review-in-audit",
            json={
                "idempotencyKey": "review-in-audit-test",
                "expectedWorkspaceHash": candidate_workspace_hash,
            },
        )
        assert retry_review_response.status_code == 200
        retry_payload = retry_review_response.json()
        assert retry_payload["ok"] is True
        assert retry_payload["data"]["reviewCycleId"] == review_payload["data"]["reviewCycleId"]
        assert len(app.state.storage.review_cycle_store.read_cycles(project_id, child_id)) == 1
        persisted_after_retry = _persisted_workflow_state(app, project_id, child_id)
        assert persisted_after_retry.get("latestCommit") == first_latest_commit
        detail_after_retry = _detail_state(client, project_id, child_id)
        assert detail_after_retry["initial_sha"] == first_latest_commit["initialSha"]
        assert detail_after_retry["head_sha"] == first_latest_commit["headSha"]
        assert detail_after_retry["commit_message"] == first_latest_commit["commitMessage"]

        assert len(codex_client.review_calls) == 1
        review_call = codex_client.review_calls[0]
        assert len(codex_client.forked_threads) >= 2
        review_fork = codex_client.forked_threads[-1]

        assert review_fork["source_thread_id"] == audit_state["auditLineageThreadId"]
        assert review_fork["cwd"] == str(workspace_root)
        assert review_call["thread_id"] == review_fork["thread_id"]
        assert review_call["thread_id"] != audit_state["auditLineageThreadId"]
        assert review_call["delivery"] is None
        assert review_call["cwd"] == str(workspace_root)
        assert review_call["target_sha"] == review_cycle["reviewCommitSha"]
        assert review_cycle["reviewThreadId"] == review_fork["thread_id"]
        assert audit_state["reviewThreadId"] == review_fork["thread_id"]

        audit_snapshot = app.state.storage.thread_snapshot_store_v2.read_snapshot(
            project_id,
            child_id,
            "audit",
        )
        guidance_item = next(
            item
            for item in audit_snapshot.get("items", [])
            if str(item.get("id") or "") == "review-context:instructions"
        )
        assert "Do not recursively scan `.planningtree` before reviewing." in str(
            guidance_item.get("text") or ""
        )


def test_mark_done_from_execution_persists_latest_commit_and_idempotency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    init_git_repo(workspace_root)

    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)
    monkeypatch.delenv("PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "1")

    app = create_app(data_root=tmp_path / "appdata")
    codex_client = WorkflowV2ReviewContextCodexClient()
    _set_workflow_v2_codex_client(app, codex_client)

    with TestClient(app) as client:
        project_id, root_id = _setup_project(client, workspace_root)
        child_id, _ = _do_lazy_split(app.state.storage, project_id, root_id)
        _confirm_spec(app.state.storage, project_id, child_id)

        finish_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/finish-task",
            json={"idempotencyKey": "finish-task-mark-done-test"},
        )
        assert finish_response.status_code == 200

        execution_state = _wait_for(
            lambda: next(
                (
                    state
                    for state in [_workflow_state(client, project_id, child_id)]
                    if state.get("workflowPhase") == "execution_decision_pending"
                ),
                None,
            )
        )
        execution_decision = execution_state.get("currentExecutionDecision")
        assert isinstance(execution_decision, dict)
        candidate_workspace_hash = str(execution_decision.get("candidateWorkspaceHash") or "")
        assert candidate_workspace_hash

        mark_done_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/mark-done-from-execution",
            json={
                "idempotencyKey": "mark-done-from-execution-test",
                "expectedWorkspaceHash": candidate_workspace_hash,
            },
        )
        assert mark_done_response.status_code == 200
        mark_done_payload = mark_done_response.json()
        assert mark_done_payload["ok"] is True
        assert mark_done_payload["data"]["workflowPhase"] == "done"
        accepted_sha = str(mark_done_payload["data"].get("acceptedSha") or "")
        assert accepted_sha

        persisted_workflow_state = _persisted_workflow_state(app, project_id, child_id)
        latest_commit = persisted_workflow_state.get("latestCommit")
        assert isinstance(latest_commit, dict)
        assert latest_commit["sourceAction"] == "mark_done_from_execution"
        assert latest_commit["headSha"] == accepted_sha
        assert isinstance(latest_commit["commitMessage"], str) and latest_commit["commitMessage"]
        assert isinstance(latest_commit["committed"], bool)
        assert isinstance(latest_commit["recordedAt"], str) and latest_commit["recordedAt"]
        first_latest_commit = dict(latest_commit)
        detail_after_mark_done = _detail_state(client, project_id, child_id)
        assert detail_after_mark_done["initial_sha"] == first_latest_commit["initialSha"]
        assert detail_after_mark_done["head_sha"] == first_latest_commit["headSha"]
        assert detail_after_mark_done["commit_message"] == first_latest_commit["commitMessage"]

        retry_mark_done_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/mark-done-from-execution",
            json={
                "idempotencyKey": "mark-done-from-execution-test",
                "expectedWorkspaceHash": candidate_workspace_hash,
            },
        )
        assert retry_mark_done_response.status_code == 200
        retry_payload = retry_mark_done_response.json()
        assert retry_payload["ok"] is True
        assert str(retry_payload["data"].get("acceptedSha") or "") == accepted_sha
        persisted_after_retry = _persisted_workflow_state(app, project_id, child_id)
        assert persisted_after_retry.get("latestCommit") == first_latest_commit
        detail_after_retry = _detail_state(client, project_id, child_id)
        assert detail_after_retry["initial_sha"] == first_latest_commit["initialSha"]
        assert detail_after_retry["head_sha"] == first_latest_commit["headSha"]
        assert detail_after_retry["commit_message"] == first_latest_commit["commitMessage"]


def test_mark_done_from_audit_reuses_existing_latest_commit_without_overwrite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    init_git_repo(workspace_root)

    monkeypatch.delenv("PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL", raising=False)
    monkeypatch.delenv("PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED", "1")

    app = create_app(data_root=tmp_path / "appdata")
    codex_client = WorkflowV2ReviewContextCodexClient()
    _set_workflow_v2_codex_client(app, codex_client)

    with TestClient(app) as client:
        project_id, root_id = _setup_project(client, workspace_root)
        child_id, _ = _do_lazy_split(app.state.storage, project_id, root_id)
        _confirm_spec(app.state.storage, project_id, child_id)

        finish_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/finish-task",
            json={"idempotencyKey": "finish-task-mark-done-audit-test"},
        )
        assert finish_response.status_code == 200

        execution_state = _wait_for(
            lambda: next(
                (
                    state
                    for state in [_workflow_state(client, project_id, child_id)]
                    if state.get("workflowPhase") == "execution_decision_pending"
                ),
                None,
            )
        )
        execution_decision = execution_state.get("currentExecutionDecision")
        assert isinstance(execution_decision, dict)
        candidate_workspace_hash = str(execution_decision.get("candidateWorkspaceHash") or "")
        assert candidate_workspace_hash

        review_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/review-in-audit",
            json={
                "idempotencyKey": "review-before-mark-done-audit-test",
                "expectedWorkspaceHash": candidate_workspace_hash,
            },
        )
        assert review_response.status_code == 200
        review_payload = review_response.json()
        assert review_payload["ok"] is True

        _wait_for(
            lambda: next(
                (
                    state
                    for state in [_workflow_state(client, project_id, child_id)]
                    if state.get("workflowPhase") == "audit_decision_pending"
                ),
                None,
            )
        )
        persisted_after_review = _persisted_workflow_state(app, project_id, child_id)
        latest_commit_after_review = persisted_after_review.get("latestCommit")
        assert isinstance(latest_commit_after_review, dict)
        first_latest_commit = dict(latest_commit_after_review)
        review_cycles = app.state.storage.review_cycle_store.read_cycles(project_id, child_id)
        assert len(review_cycles) == 1
        review_cycle = review_cycles[0]
        expected_review_commit_sha = str(review_cycle.get("reviewCommitSha") or "")
        assert expected_review_commit_sha

        mark_done_audit_response = client.post(
            f"/v2/projects/{project_id}/nodes/{child_id}/workflow/mark-done-from-audit",
            json={
                "idempotencyKey": "mark-done-from-audit-test",
                "expectedReviewCommitSha": expected_review_commit_sha,
            },
        )
        assert mark_done_audit_response.status_code == 200
        mark_done_payload = mark_done_audit_response.json()
        assert mark_done_payload["ok"] is True
        assert mark_done_payload["data"]["workflowPhase"] == "done"
        assert str(mark_done_payload["data"].get("acceptedSha") or "") == expected_review_commit_sha

        persisted_after_mark_done = _persisted_workflow_state(app, project_id, child_id)
        assert persisted_after_mark_done.get("latestCommit") == first_latest_commit
        detail_after_mark_done = _detail_state(client, project_id, child_id)
        assert detail_after_mark_done["initial_sha"] == first_latest_commit["initialSha"]
        assert detail_after_mark_done["head_sha"] == first_latest_commit["headSha"]
        assert detail_after_mark_done["commit_message"] == first_latest_commit["commitMessage"]
