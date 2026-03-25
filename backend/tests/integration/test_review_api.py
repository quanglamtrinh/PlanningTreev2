from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.ai.codex_client import CodexTransportError
from backend.services import planningtree_workspace


class ReviewCodexClient:
    """Fake Codex client for review integration tests."""

    def __init__(self, *, response_text: str = "Execution complete") -> None:
        self.response_text = response_text
        self.started_threads: list[str] = []
        self.prompts: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"review-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        thread_id = f"review-fork-thread-{len(self.started_threads) + 1}"
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        self.prompts.append(prompt)
        thread_id = str(kwargs.get("thread_id", ""))
        cwd = kwargs.get("cwd")
        if isinstance(cwd, str) and cwd:
            Path(cwd, "execution-output.txt").write_text("done\n", encoding="utf-8")
        return {"stdout": self.response_text, "thread_id": thread_id}


class IntegrationRollupCodexClient:
    """Fake Codex client that returns a JSON summary for integration rollup."""

    def __init__(self, *, summary: str = "Integration complete") -> None:
        self.summary = summary
        self.started_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"integration-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        payload = json.dumps({"summary": self.summary})
        on_delta = kwargs.get("on_delta")
        if callable(on_delta):
            on_delta(payload)
        return {"stdout": payload, "thread_id": str(kwargs.get("thread_id") or "")}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(client: TestClient, workspace_root) -> tuple[str, str]:
    resp = client.post("/v1/projects/attach", json={"folder_path": str(workspace_root)})
    assert resp.status_code == 200
    snap = resp.json()
    project_id = snap["project"]["id"]
    root_id = snap["tree_state"]["root_node_id"]
    return project_id, root_id


def _add_child(
    client: TestClient,
    project_id: str,
    parent_id: str,
    *,
    node_id: str,
    title: str,
    description: str = "",
    status: str = "ready",
) -> None:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    node_index = snapshot["tree_state"]["node_index"]
    parent = node_index[parent_id]
    child_ids = [*parent.get("child_ids", []), node_id]
    parent["child_ids"] = child_ids
    node_index[node_id] = {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,
        "description": description,
        "status": status,
        "node_kind": "original",
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": len(child_ids) - 1,
        "hierarchical_number": f"{parent.get('hierarchical_number', '1')}.{len(child_ids)}",
        "created_at": "2026-01-01T00:00:00Z",
    }
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)


def _add_review_node(client: TestClient, project_id: str, parent_id: str) -> str:
    review_id = "review-001"
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][review_id] = {
        "node_id": review_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Review",
        "description": "",
        "status": "ready",
        "node_kind": "review",
        "depth": 1,
        "display_order": 99,
        "hierarchical_number": "1.R",
        "created_at": "2026-01-01T00:00:00Z",
    }
    snapshot["tree_state"]["node_index"][parent_id]["review_node_id"] = review_id
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)
    return review_id


def _write_confirmed_frame(client: TestClient, project_id: str, node_id: str, content: str) -> None:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    project_path = Path(snapshot["project"]["project_path"])
    node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
    assert node_dir is not None
    (node_dir / "frame.meta.json").write_text(
        json.dumps(
            {
                "confirmed_revision": 1,
                "confirmed_at": "2026-01-01T00:00:00Z",
                "confirmed_content": content,
            }
        ),
        encoding="utf-8",
    )


def _setup_node_with_execution_completed(
    client: TestClient,
    workspace_root,
    *,
    codex_client=None,
) -> tuple[str, str]:
    """Set up a project with a leaf node that has completed execution."""
    if codex_client is None:
        codex_client = ReviewCodexClient()
    client.app.state.finish_task_service._codex_client = codex_client
    client.app.state.thread_lineage_service._codex_client = codex_client

    project_id, root_id = _setup_project(client, workspace_root)

    # Write confirmed frame + spec so finish-task is allowed
    frame_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/frame",
        json={"content": "# Task Title\nTask\n\n# Objective\nDo it\n"},
    )
    assert frame_resp.status_code == 200
    assert client.post(f"/v1/projects/{project_id}/nodes/{root_id}/confirm-frame").status_code == 200

    spec_resp = client.put(
        f"/v1/projects/{project_id}/nodes/{root_id}/documents/spec",
        json={"content": "# Spec\nImplement it\n"},
    )
    assert spec_resp.status_code == 200
    assert client.post(f"/v1/projects/{project_id}/nodes/{root_id}/confirm-spec").status_code == 200

    # Force status to ready for finish-task
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][root_id]["status"] = "ready"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    # Finish task → starts execution
    finish_resp = client.post(f"/v1/projects/{project_id}/nodes/{root_id}/finish-task")
    assert finish_resp.status_code == 200

    # Wait for execution to complete
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        exec_state = client.app.state.storage.execution_state_store.read_state(
            project_id, root_id
        )
        if exec_state and exec_state.get("status") == "completed":
            break
        time.sleep(0.02)

    exec_state = client.app.state.storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "completed"

    return project_id, root_id


def _wait_for_integration_terminal(
    client: TestClient, project_id: str, review_node_id: str, *, timeout_sec: float = 2.0
) -> dict:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        session = client.app.state.storage.chat_state_store.read_session(
            project_id, review_node_id, thread_role="integration"
        )
        if not session.get("active_turn_id"):
            messages = session.get("messages", [])
            assistant = next(
                (
                    m for m in reversed(messages)
                    if isinstance(m, dict) and m.get("role") == "assistant"
                ),
                None,
            )
            if assistant is not None and assistant.get("status") in {"completed", "error"}:
                return session
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for integration completion.")


# ---------------------------------------------------------------------------
# Tests: accept-local-review route
# ---------------------------------------------------------------------------


def test_accept_local_review_route_happy_path(client: TestClient, workspace_root):
    project_id, node_id = _setup_node_with_execution_completed(client, workspace_root)

    # Transition to review_pending first
    client.app.state.review_service.start_local_review(project_id, node_id)

    resp = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/accept-local-review",
        json={"summary": "Looks good, task completed correctly."},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["node_id"] == node_id
    assert payload["status"] == "review_accepted"

    # Verify node is done
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    node = snapshot["tree_state"]["node_index"][node_id]
    assert node["status"] == "done"

    # Verify execution state
    exec_state = client.app.state.storage.execution_state_store.read_state(project_id, node_id)
    assert exec_state["status"] == "review_accepted"


def test_get_review_state_route_returns_default_state(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    review_id = _add_review_node(client, project_id, root_id)

    resp = client.get(f"/v1/projects/{project_id}/nodes/{review_id}/review-state")
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["checkpoints"] == []
    assert payload["pending_siblings"] == []
    assert payload["sibling_manifest"] == []
    assert payload["rollup"]["status"] == "pending"
    assert payload["rollup"]["summary"] is None
    assert payload["rollup"]["sha"] is None
    assert payload["rollup"]["accepted_at"] is None
    assert payload["rollup"]["draft"] == {
        "summary": None,
        "sha": None,
        "generated_at": None,
    }


def test_get_review_state_route_returns_rollup_draft_and_progress(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    _add_child(client, project_id, root_id, node_id="child-1", title="Accepted child")
    review_id = _add_review_node(client, project_id, root_id)
    client.app.state.storage.review_state_store.write_state(
        project_id,
        review_id,
        {
            "checkpoints": [
                {
                    "label": "K0",
                    "sha": "sha256:baseline",
                    "summary": None,
                    "source_node_id": None,
                    "accepted_at": "2026-01-01T00:00:00Z",
                },
                {
                    "label": "K1",
                    "sha": "sha256:checkpoint",
                    "summary": "Accepted child implementation",
                    "source_node_id": "child-1",
                    "accepted_at": "2026-01-01T00:00:00Z",
                }
            ],
            "rollup": {
                "status": "ready",
                "summary": None,
                "sha": None,
                "accepted_at": None,
                "draft": {
                    "summary": "Integrated child work into a coherent package.",
                    "sha": "sha256:rollupdraft",
                    "generated_at": "2026-01-01T00:05:00Z",
                },
            },
            "pending_siblings": [
                {
                    "index": 2,
                    "title": "Follow-up child",
                    "objective": "Handle the remaining package work",
                    "materialized_node_id": "child-2",
                }
            ],
        },
    )

    resp = client.get(f"/v1/projects/{project_id}/nodes/{review_id}/review-state")
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["checkpoints"][1]["label"] == "K1"
    assert payload["checkpoints"][1]["summary"] == "Accepted child implementation"
    assert payload["rollup"]["status"] == "ready"
    assert payload["rollup"]["draft"]["summary"] == "Integrated child work into a coherent package."
    assert payload["rollup"]["draft"]["sha"] == "sha256:rollupdraft"
    assert payload["pending_siblings"][0]["materialized_node_id"] == "child-2"
    assert payload["sibling_manifest"] == [
        {
            "index": 1,
            "title": "Accepted child",
            "objective": None,
            "materialized_node_id": "child-1",
            "status": "completed",
            "checkpoint_label": "K1",
        },
        {
            "index": 2,
            "title": "Follow-up child",
            "objective": "Handle the remaining package work",
            "materialized_node_id": "child-2",
            "status": "active",
            "checkpoint_label": None,
        },
    ]


def test_accept_local_review_route_rejects_empty_summary(client: TestClient, workspace_root):
    project_id, node_id = _setup_node_with_execution_completed(client, workspace_root)
    client.app.state.review_service.start_local_review(project_id, node_id)

    resp = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/accept-local-review",
        json={"summary": ""},
    )
    assert resp.status_code == 422


def test_accept_local_review_route_rejects_wrong_status(client: TestClient, workspace_root):
    project_id, node_id = _setup_node_with_execution_completed(client, workspace_root)
    # Still in 'completed', not 'review_pending'
    resp = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/accept-local-review",
        json={"summary": "Some summary"},
    )
    assert resp.status_code in {400, 409}


def test_detail_state_returns_can_accept_local_review(client: TestClient, workspace_root):
    project_id, node_id = _setup_node_with_execution_completed(client, workspace_root)

    detail_before = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/detail-state").json()
    assert detail_before["can_accept_local_review"] is False

    client.app.state.review_service.start_local_review(project_id, node_id)

    detail_after = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/detail-state").json()
    assert detail_after["can_accept_local_review"] is True


# ---------------------------------------------------------------------------
# Tests: auto-trigger start_local_review on first audit write
# ---------------------------------------------------------------------------


def test_first_audit_write_triggers_start_local_review(client: TestClient, workspace_root):
    codex = ReviewCodexClient()
    project_id, node_id = _setup_node_with_execution_completed(
        client, workspace_root, codex_client=codex,
    )

    # Execution is completed — audit should be writable
    exec_state = client.app.state.storage.execution_state_store.read_state(project_id, node_id)
    assert exec_state["status"] == "completed"

    # Swap codex for chat turns
    client.app.state.chat_service._codex_client = codex
    client.app.state.thread_lineage_service._codex_client = codex

    # Send first audit message
    resp = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "Reviewing the execution output."},
    )
    assert resp.status_code == 200

    # The auto-trigger should have moved status to review_pending
    exec_state = client.app.state.storage.execution_state_store.read_state(project_id, node_id)
    assert exec_state["status"] == "review_pending"

    detail = client.get(f"/v1/projects/{project_id}/nodes/{node_id}/detail-state").json()
    assert detail["can_accept_local_review"] is True


def test_first_audit_write_injects_local_review_prompt_once(client: TestClient, workspace_root):
    codex = ReviewCodexClient(response_text="Audit review complete")
    project_id, node_id = _setup_node_with_execution_completed(
        client, workspace_root, codex_client=codex,
    )

    client.app.state.chat_service._codex_client = codex
    client.app.state.thread_lineage_service._codex_client = codex

    first = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "Review the execution output."},
    )
    assert first.status_code == 200

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        session = client.app.state.storage.chat_state_store.read_session(
            project_id, node_id, thread_role="audit"
        )
        if not session.get("active_turn_id"):
            break
        time.sleep(0.02)

    assert "Confirmed frame" in codex.prompts[-1]
    assert "Confirmed spec" in codex.prompts[-1]
    assert "Head SHA:" in codex.prompts[-1]

    second = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "Second audit follow-up."},
    )
    assert second.status_code == 200

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        session = client.app.state.storage.chat_state_store.read_session(
            project_id, node_id, thread_role="audit"
        )
        if not session.get("active_turn_id"):
            break
        time.sleep(0.02)

    assert "Confirmed frame" not in codex.prompts[-1]
    assert "Confirmed spec" not in codex.prompts[-1]


def test_second_audit_write_does_not_fail(client: TestClient, workspace_root):
    codex = ReviewCodexClient()
    project_id, node_id = _setup_node_with_execution_completed(
        client, workspace_root, codex_client=codex,
    )
    client.app.state.chat_service._codex_client = codex
    client.app.state.thread_lineage_service._codex_client = codex

    # First audit write triggers review_pending
    resp1 = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "First audit message."},
    )
    assert resp1.status_code == 200

    # Wait for first turn to finish so we can send another
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        session = client.app.state.storage.chat_state_store.read_session(
            project_id, node_id, thread_role="audit"
        )
        if not session.get("active_turn_id"):
            break
        time.sleep(0.02)

    # Second audit write — auto-trigger fires again but is a no-op (already review_pending)
    resp2 = client.post(
        f"/v1/projects/{project_id}/nodes/{node_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "Second audit message."},
    )
    assert resp2.status_code == 200

    exec_state = client.app.state.storage.execution_state_store.read_state(project_id, node_id)
    assert exec_state["status"] == "review_pending"


# ---------------------------------------------------------------------------
# Tests: accept-rollup-review route
# ---------------------------------------------------------------------------


def test_accept_rollup_review_route_happy_path(client: TestClient, workspace_root):
    rollup_codex = IntegrationRollupCodexClient(summary="All subtasks integrated successfully")
    project_id, root_id = _setup_project(client, workspace_root)

    # Create parent with one child + review node
    child_id = "child-001"
    _add_child(client, project_id, root_id, node_id=child_id, title="Subtask 1")
    review_id = _add_review_node(client, project_id, root_id)

    # Set up review state with K0 checkpoint and rollup ready
    client.app.state.storage.review_state_store.write_state(project_id, review_id, {
        "checkpoints": [
            {"sha": "sha256:abc", "summary": "Subtask 1 done", "source_node_id": child_id,
             "created_at": "2026-01-01T00:00:00Z"},
        ],
        "pending_siblings": [],
        "rollup": {"status": "ready", "summary": None, "sha": None,
                   "draft": {"summary": None, "sha": None, "generated_at": None}},
    })

    # Set child to review_accepted
    client.app.state.storage.execution_state_store.write_state(project_id, child_id, {
        "status": "review_accepted",
        "head_sha": "sha256:abc",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:00Z",
    })
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][child_id]["status"] = "done"
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)

    # Wire rollup codex and start integration
    client.app.state.review_service._codex_client = rollup_codex
    client.app.state.review_service.start_integration_rollup(project_id, review_id)

    # Wait for integration to finish and produce a draft
    _wait_for_integration_terminal(client, project_id, review_id)

    # Verify draft is populated
    review_state = client.app.state.storage.review_state_store.read_state(project_id, review_id)
    draft = review_state["rollup"]["draft"]
    assert draft["summary"] is not None

    # Accept rollup via route
    resp = client.post(
        f"/v1/projects/{project_id}/nodes/{review_id}/accept-rollup-review",
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["rollup_status"] == "accepted"
    assert payload["summary"] == "All subtasks integrated successfully"

    # Verify rollup package appended to parent audit
    audit_session = client.app.state.storage.chat_state_store.read_session(
        project_id, root_id, thread_role="audit"
    )
    system_messages = [
        m for m in audit_session.get("messages", [])
        if m.get("role") == "system" and "Rollup Package" in m.get("content", "")
    ]
    assert len(system_messages) == 1


def test_accept_rollup_review_rejects_non_ready(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    review_id = _add_review_node(client, project_id, root_id)

    # Default rollup status is "pending", not "ready"
    client.app.state.storage.review_state_store.write_state(project_id, review_id, {
        "checkpoints": [],
        "pending_siblings": [],
        "rollup": {"status": "pending", "summary": None, "sha": None,
                   "draft": {"summary": None, "sha": None, "generated_at": None}},
    })

    resp = client.post(
        f"/v1/projects/{project_id}/nodes/{review_id}/accept-rollup-review",
    )
    assert resp.status_code in {400, 409}


# ---------------------------------------------------------------------------
# Tests: snapshot includes review nodes
# ---------------------------------------------------------------------------


def test_snapshot_includes_review_nodes(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    review_id = _add_review_node(client, project_id, root_id)

    resp = client.get(f"/v1/projects/{project_id}/snapshot")
    assert resp.status_code == 200
    snap = resp.json()
    node_registry = snap["tree_state"]["node_registry"]
    review_nodes = [n for n in node_registry if n["node_id"] == review_id]
    assert len(review_nodes) == 1

    review_node = review_nodes[0]
    assert review_node["node_kind"] == "review"
    assert review_node.get("workflow") is None
