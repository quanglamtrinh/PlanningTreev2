"""End-to-end lifecycle tests for Phase 8.

Covers:
  1. Lazy lifecycle: shape -> split -> finish task -> execute -> audit ->
     accept local review -> next sibling materializes -> rollup -> package audit
  2. Legacy eager lifecycle: locked sibling -> finish task -> local review
     accept -> next sibling unlocks
  3. Package audit lifecycle: rollup accepted -> parent audit becomes writable
     with package record present
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.services import planningtree_workspace
from backend.tests.conftest import init_git_repo


# ---------------------------------------------------------------------------
# Fake Codex clients
# ---------------------------------------------------------------------------


class _FakeCodex:
    """Codex client that writes a marker file and returns immediately."""

    def __init__(self) -> None:
        self.started_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        tid = f"fake-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(tid)
        return {"thread_id": tid}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        del source_thread_id
        tid = f"fake-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(tid)
        return {"thread_id": tid}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        del prompt
        thread_id = str(kwargs.get("thread_id", ""))
        cwd = kwargs.get("cwd")
        if isinstance(cwd, str) and cwd:
            Path(cwd, "execution-output.txt").write_text("done\n", encoding="utf-8")
        return {"stdout": "Execution complete", "thread_id": thread_id}


class _IntegrationCodex:
    """Codex client that produces a JSON rollup summary."""

    def __init__(self, summary: str = "All subtasks integrated") -> None:
        self.summary = summary
        self.started_threads: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        tid = f"integration-{len(self.started_threads) + 1}"
        self.started_threads.append(tid)
        return {"thread_id": tid}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        del source_thread_id
        tid = f"integration-{len(self.started_threads) + 1}"
        self.started_threads.append(tid)
        return {"thread_id": tid}

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
    return snap["project"]["id"], snap["tree_state"]["root_node_id"]


def _confirm_frame_and_spec(client: TestClient, project_id: str, node_id: str) -> None:
    client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/frame",
        json={"content": "# Task Title\nTask\n\n# Objective\nDo it\n"},
    )
    client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-frame")
    client.put(
        f"/v1/projects/{project_id}/nodes/{node_id}/documents/spec",
        json={"content": "# Spec\nImplement it\n"},
    )
    client.post(f"/v1/projects/{project_id}/nodes/{node_id}/confirm-spec")


def _force_status(client: TestClient, project_id: str, node_id: str, status: str) -> None:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    snapshot["tree_state"]["node_index"][node_id]["status"] = status
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)


def _add_child_directly(
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
    idx = snapshot["tree_state"]["node_index"]
    parent = idx[parent_id]
    parent.setdefault("child_ids", []).append(node_id)
    idx[node_id] = {
        "node_id": node_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,
        "description": description,
        "status": status,
        "node_kind": "original",
        "depth": int(parent.get("depth", 0) or 0) + 1,
        "display_order": len(parent["child_ids"]) - 1,
        "hierarchical_number": f"{parent.get('hierarchical_number', '1')}.{len(parent['child_ids'])}",
        "created_at": "2026-01-01T00:00:00Z",
    }
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)


def _add_review_node(client: TestClient, project_id: str, parent_id: str, review_id: str = "review-001") -> str:
    snapshot = client.app.state.storage.project_store.load_snapshot(project_id)
    idx = snapshot["tree_state"]["node_index"]
    idx[review_id] = {
        "node_id": review_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Review",
        "description": "",
        "status": "ready",
        "node_kind": "review",
        "depth": int(idx[parent_id].get("depth", 0) or 0) + 1,
        "display_order": 99,
        "hierarchical_number": f"{idx[parent_id].get('hierarchical_number', '1')}.R",
        "created_at": "2026-01-01T00:00:00Z",
    }
    idx[parent_id]["review_node_id"] = review_id
    client.app.state.storage.project_store.save_snapshot(project_id, snapshot)
    return review_id


def _finish_and_wait_execution(client: TestClient, project_id: str, node_id: str) -> None:
    resp = client.post(f"/v1/projects/{project_id}/nodes/{node_id}/finish-task")
    assert resp.status_code == 200
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        es = client.app.state.storage.execution_state_store.read_state(project_id, node_id)
        if es and es.get("status") == "completed":
            return
        time.sleep(0.02)
    raise AssertionError(f"Execution for {node_id} did not complete in time.")


def _wait_integration_done(client: TestClient, project_id: str, review_node_id: str) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        session = client.app.state.storage.chat_state_store.read_session(
            project_id, review_node_id, thread_role="audit"
        )
        if not session.get("active_turn_id"):
            msgs = session.get("messages", [])
            assistant = next(
                (m for m in reversed(msgs) if isinstance(m, dict) and m.get("role") == "assistant"),
                None,
            )
            if assistant and assistant.get("status") in {"completed", "error"}:
                return
        time.sleep(0.02)
    raise AssertionError("Integration rollup did not complete in time.")


# ---------------------------------------------------------------------------
# Test 1: Lazy lifecycle (full chain)
#
# shape -> split (1 child + review + manifest) -> finish task -> execute ->
# audit write (triggers review_pending) -> accept local review ->
# next sibling materializes -> (repeat for sibling B) -> rollup ready ->
# integration rollup -> accept rollup -> package audit on parent
# ---------------------------------------------------------------------------


def test_lazy_lifecycle_end_to_end(client: TestClient, workspace_root):
    codex = _FakeCodex()
    client.app.state.finish_task_service._codex_client = codex
    client.app.state.chat_service._codex_client = codex
    client.app.state.thread_lineage_service._codex_client = codex

    # Initialize git repo so git guardrails pass
    init_git_repo(workspace_root)

    project_id, root_id = _setup_project(client, workspace_root)

    # --- Set up a lazy split manually (1 materialized child + review + manifest) ---
    child_a_id = "child-a"
    _add_child_directly(
        client,
        project_id,
        root_id,
        node_id=child_a_id,
        title="Subtask A",
        description="Do part A",
    )
    review_id = _add_review_node(client, project_id, root_id)

    # Write review state with K0 checkpoint + one pending sibling B.
    # Raw lazy manifests only persist later siblings (index >= 2).
    client.app.state.storage.review_state_store.write_state(project_id, review_id, {
        "checkpoints": [
            {"label": "K0", "sha": "sha256:initial", "summary": None,
             "source_node_id": None, "accepted_at": "2026-01-01T00:00:00Z"},
        ],
        "pending_siblings": [
            {"index": 2, "title": "Subtask B", "objective": "Do part B",
             "materialized_node_id": None},
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None,
                    "draft": {"summary": None, "sha": None, "generated_at": None}},
    })

    initial_review_state = client.get(
        f"/v1/projects/{project_id}/nodes/{review_id}/review-state"
    ).json()
    assert initial_review_state["sibling_manifest"] == [
        {
            "index": 1,
            "title": "Subtask A",
            "objective": "Do part A",
            "materialized_node_id": child_a_id,
            "status": "active",
            "checkpoint_label": None,
        },
        {
            "index": 2,
            "title": "Subtask B",
            "objective": "Do part B",
            "materialized_node_id": None,
            "status": "pending",
            "checkpoint_label": None,
        },
    ]

    # Write confirmed frame+spec for child A so finish-task works
    _confirm_frame_and_spec(client, project_id, child_a_id)
    _force_status(client, project_id, child_a_id, "ready")

    # --- Finish task on child A -> execution completes ---
    _finish_and_wait_execution(client, project_id, child_a_id)

    exec_state_a = client.app.state.storage.execution_state_store.read_state(project_id, child_a_id)
    assert exec_state_a["status"] == "completed"

    # --- Send audit write -> triggers start_local_review (completed -> review_pending) ---
    audit_resp = client.post(
        f"/v1/projects/{project_id}/nodes/{child_a_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "Reviewed subtask A output — looks good."},
    )
    assert audit_resp.status_code == 200

    exec_state_a = client.app.state.storage.execution_state_store.read_state(project_id, child_a_id)
    assert exec_state_a["status"] == "review_pending"

    # --- Accept local review for child A (already review_pending from audit auto-trigger) ---
    accept_resp = client.post(
        f"/v1/projects/{project_id}/nodes/{child_a_id}/accept-local-review",
        json={"summary": "Subtask A is correct and complete."},
    )
    assert accept_resp.status_code == 200
    payload = accept_resp.json()
    assert payload["status"] == "review_accepted"

    # Child A should be done
    snap = client.get(f"/v1/projects/{project_id}/snapshot").json()
    child_a_node = next(n for n in snap["tree_state"]["node_registry"] if n["node_id"] == child_a_id)
    assert child_a_node["status"] == "done"

    # --- Next sibling B should be materialized ---
    activated_id = payload.get("activated_sibling_id")
    assert activated_id is not None, "Sibling B should have been activated"

    # Verify sibling B exists in snapshot
    snap2 = client.get(f"/v1/projects/{project_id}/snapshot").json()
    child_b_node = next(
        (n for n in snap2["tree_state"]["node_registry"] if n["node_id"] == activated_id), None
    )
    assert child_b_node is not None, "Sibling B should appear in snapshot"
    assert child_b_node["title"] == "Subtask B"
    assert child_b_node["status"] == "ready"

    # Verify review state: sibling B marked materialized, K1 checkpoint added
    review_state = client.app.state.storage.review_state_store.read_state(project_id, review_id)
    assert len(review_state["checkpoints"]) == 2  # K0 + K1
    sib_b = next(s for s in review_state["pending_siblings"] if s["index"] == 2)
    assert sib_b["materialized_node_id"] == activated_id
    public_review_state = client.get(
        f"/v1/projects/{project_id}/nodes/{review_id}/review-state"
    ).json()
    assert public_review_state["sibling_manifest"] == [
        {
            "index": 1,
            "title": "Task",
            "objective": "Do part A",
            "materialized_node_id": child_a_id,
            "status": "completed",
            "checkpoint_label": "K1",
        },
        {
            "index": 2,
            "title": "Subtask B",
            "objective": "Do part B",
            "materialized_node_id": activated_id,
            "status": "active",
            "checkpoint_label": None,
        },
    ]

    # --- Now complete sibling B the same way ---
    _confirm_frame_and_spec(client, project_id, activated_id)
    _force_status(client, project_id, activated_id, "ready")
    _finish_and_wait_execution(client, project_id, activated_id)

    # Audit write -> review_pending
    client.post(
        f"/v1/projects/{project_id}/nodes/{activated_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "Subtask B looks fine."},
    )
    exec_b = client.app.state.storage.execution_state_store.read_state(project_id, activated_id)
    assert exec_b["status"] == "review_pending"

    # Accept local review for sibling B
    accept_b_resp = client.post(
        f"/v1/projects/{project_id}/nodes/{activated_id}/accept-local-review",
        json={"summary": "Subtask B complete."},
    )
    assert accept_b_resp.status_code == 200
    assert accept_b_resp.json()["activated_sibling_id"] is None  # No more siblings

    # Rollup should now be ready (all siblings done, no pending)
    review_state2 = client.app.state.storage.review_state_store.read_state(project_id, review_id)
    assert review_state2["rollup"]["status"] == "ready"
    assert len(review_state2["checkpoints"]) == 3  # K0 + K1 + K2

    # --- Integration rollup ---
    integration_codex = _IntegrationCodex(summary="Both subtasks integrated successfully")
    client.app.state.review_service._codex_client = integration_codex
    client.app.state.thread_lineage_service._codex_client = integration_codex
    client.app.state.review_service.start_integration_rollup(project_id, review_id)
    _wait_integration_done(client, project_id, review_id)

    # Verify draft populated
    review_state3 = client.app.state.storage.review_state_store.read_state(project_id, review_id)
    assert review_state3["rollup"]["draft"]["summary"] is not None

    # --- Accept rollup ---
    rollup_resp = client.post(f"/v1/projects/{project_id}/nodes/{review_id}/accept-rollup-review")
    assert rollup_resp.status_code == 200
    assert rollup_resp.json()["rollup_status"] == "accepted"

    # --- Verify package audit: parent audit has rollup package ---
    audit_session = client.app.state.storage.chat_state_store.read_session(
        project_id, root_id, thread_role="audit"
    )
    system_msgs = [
        m for m in audit_session.get("messages", [])
        if m.get("role") == "system" and "Rollup Package" in m.get("content", "")
    ]
    assert len(system_msgs) == 1, "Rollup package should be appended to parent audit"

    # --- Verify snapshot review_summary includes derived sibling_manifest ---
    final_snap = client.get(f"/v1/projects/{project_id}/snapshot").json()
    review_nodes = [n for n in final_snap["tree_state"]["node_registry"] if n["node_id"] == review_id]
    assert len(review_nodes) == 1
    summary = review_nodes[0].get("review_summary")
    assert summary is not None
    assert summary["pending_sibling_count"] == 0  # All materialized
    assert "pending_siblings" in summary
    assert len(summary["pending_siblings"]) == 1
    assert summary["sibling_manifest"] == [
        {
            "index": 1,
            "title": "Task",
            "objective": "Do part A",
            "materialized_node_id": child_a_id,
            "status": "completed",
            "checkpoint_label": "K1",
        },
        {
            "index": 2,
            "title": "Subtask B",
            "objective": "Do part B",
            "materialized_node_id": activated_id,
            "status": "completed",
            "checkpoint_label": "K2",
        },
    ]


# ---------------------------------------------------------------------------
# Test 2: Legacy eager lifecycle
#
# Parent with 2 children (child-1 ready, child-2 locked, no review node) ->
# finish task on child-1 -> execute -> audit -> accept local review ->
# child-2 unlocks
# ---------------------------------------------------------------------------


def test_legacy_eager_lifecycle(client: TestClient, workspace_root):
    codex = _FakeCodex()
    client.app.state.finish_task_service._codex_client = codex
    client.app.state.chat_service._codex_client = codex
    client.app.state.thread_lineage_service._codex_client = codex

    # Initialize git repo so git guardrails pass
    init_git_repo(workspace_root)

    project_id, root_id = _setup_project(client, workspace_root)

    # Set up eager tree: root has 2 children, second is locked
    child_1_id = "eager-child-1"
    child_2_id = "eager-child-2"
    _add_child_directly(client, project_id, root_id, node_id=child_1_id, title="Eager Child 1", status="ready")
    _add_child_directly(client, project_id, root_id, node_id=child_2_id, title="Eager Child 2", status="locked")

    # NO review node — this is legacy eager

    # Confirm frame+spec for child 1
    _confirm_frame_and_spec(client, project_id, child_1_id)
    _force_status(client, project_id, child_1_id, "ready")

    # Finish task + execution
    _finish_and_wait_execution(client, project_id, child_1_id)

    # Audit write triggers review_pending
    client.post(
        f"/v1/projects/{project_id}/nodes/{child_1_id}/chat/message",
        params={"thread_role": "audit"},
        json={"content": "Execution output looks correct."},
    )
    es = client.app.state.storage.execution_state_store.read_state(project_id, child_1_id)
    assert es["status"] == "review_pending"

    # Accept local review
    accept_resp = client.post(
        f"/v1/projects/{project_id}/nodes/{child_1_id}/accept-local-review",
        json={"summary": "Child 1 complete."},
    )
    assert accept_resp.status_code == 200

    # Child 1 should be done
    snap = client.app.state.storage.project_store.load_snapshot(project_id)
    assert snap["tree_state"]["node_index"][child_1_id]["status"] == "done"

    # Child 2 should now be unlocked (ready)
    assert snap["tree_state"]["node_index"][child_2_id]["status"] == "ready"

    # Active node should be child 2
    assert snap["tree_state"]["active_node_id"] == child_2_id


# ---------------------------------------------------------------------------
# Test 3: Package audit lifecycle
#
# After rollup accepted -> parent audit should contain the rollup package
# as an immutable system message, and parent detail-state should reflect
# package_audit_ready.
# ---------------------------------------------------------------------------


def test_package_audit_lifecycle(client: TestClient, workspace_root):
    integration_codex = _IntegrationCodex(summary="Package integration summary")

    project_id, root_id = _setup_project(client, workspace_root)

    # Set up: parent with 1 done child + review node
    child_id = "pkg-child-1"
    _add_child_directly(client, project_id, root_id, node_id=child_id, title="Done Child", status="done")
    review_id = _add_review_node(client, project_id, root_id)

    # Mark child as review_accepted
    client.app.state.storage.execution_state_store.write_state(project_id, child_id, {
        "status": "review_accepted",
        "head_sha": "sha256:child-head",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:01:00Z",
    })

    # Set up review state: all siblings done, rollup ready
    client.app.state.storage.review_state_store.write_state(project_id, review_id, {
        "checkpoints": [
            {"label": "K0", "sha": "sha256:init", "summary": None,
             "source_node_id": None, "accepted_at": "2026-01-01T00:00:00Z"},
            {"label": "K1", "sha": "sha256:child-head", "summary": "Child done",
             "source_node_id": child_id, "accepted_at": "2026-01-01T00:01:00Z"},
        ],
        "pending_siblings": [
            {"index": 1, "title": "Done Child", "objective": "Do it",
             "materialized_node_id": child_id},
        ],
        "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None,
                    "draft": {"summary": None, "sha": None, "generated_at": None}},
    })

    # Start integration rollup
    client.app.state.review_service._codex_client = integration_codex
    client.app.state.thread_lineage_service._codex_client = integration_codex
    client.app.state.review_service.start_integration_rollup(project_id, review_id)
    _wait_integration_done(client, project_id, review_id)

    # Verify draft is ready
    rs = client.app.state.storage.review_state_store.read_state(project_id, review_id)
    assert rs["rollup"]["draft"]["summary"] is not None

    # Accept rollup
    rollup_resp = client.post(f"/v1/projects/{project_id}/nodes/{review_id}/accept-rollup-review")
    assert rollup_resp.status_code == 200
    assert rollup_resp.json()["rollup_status"] == "accepted"

    # Verify parent audit has rollup package
    audit_session = client.app.state.storage.chat_state_store.read_session(
        project_id, root_id, thread_role="audit"
    )
    package_msgs = [
        m for m in audit_session.get("messages", [])
        if m.get("role") == "system" and "Rollup Package" in m.get("content", "")
    ]
    assert len(package_msgs) == 1
    assert "Package integration summary" in package_msgs[0]["content"]
    assert review_id in package_msgs[0]["content"]

    # Verify parent detail-state shows package_audit_ready
    detail_resp = client.get(f"/v1/projects/{project_id}/nodes/{root_id}/detail-state")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail.get("package_audit_ready") is True

    # Verify rollup state is accepted
    rs2 = client.app.state.storage.review_state_store.read_state(project_id, review_id)
    assert rs2["rollup"]["status"] == "accepted"
    assert rs2["rollup"]["summary"] == "Package integration summary"


# ---------------------------------------------------------------------------
# Test 4: Snapshot review_summary includes derived sibling manifest data
# ---------------------------------------------------------------------------


def test_snapshot_review_summary_includes_sibling_manifest(client: TestClient, workspace_root):
    project_id, root_id = _setup_project(client, workspace_root)
    _add_child_directly(
        client,
        project_id,
        root_id,
        node_id="child-a",
        title="First Child",
        description="Do A",
    )
    review_id = _add_review_node(client, project_id, root_id)

    # Raw lazy manifests only persist later siblings, while derived sibling_manifest
    # exposes the full chain including the active first child.
    client.app.state.storage.review_state_store.write_state(project_id, review_id, {
        "checkpoints": [
            {"label": "K0", "sha": "sha256:init", "summary": None,
             "source_node_id": None, "accepted_at": "2026-01-01T00:00:00Z"},
        ],
        "pending_siblings": [
            {"index": 2, "title": "Second Child", "objective": "Do B",
             "materialized_node_id": None},
            {"index": 3, "title": "Third Child", "objective": "Do C",
             "materialized_node_id": None},
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None,
                    "draft": {"summary": None, "sha": None, "generated_at": None}},
    })

    snap = client.get(f"/v1/projects/{project_id}/snapshot").json()
    review_nodes = [n for n in snap["tree_state"]["node_registry"] if n["node_id"] == review_id]
    assert len(review_nodes) == 1

    summary = review_nodes[0]["review_summary"]
    assert summary["checkpoint_count"] == 1
    assert summary["pending_sibling_count"] == 2  # 2 unmaterialized
    assert summary["rollup_status"] == "pending"

    # Raw persisted pending_siblings still keeps only later siblings for compatibility.
    siblings = summary["pending_siblings"]
    assert len(siblings) == 2
    assert siblings[0]["title"] == "Second Child"
    assert siblings[0]["materialized_node_id"] is None
    assert siblings[1]["title"] == "Third Child"
    assert siblings[1]["materialized_node_id"] is None

    assert summary["sibling_manifest"] == [
        {
            "index": 1,
            "title": "First Child",
            "objective": "Do A",
            "materialized_node_id": "child-a",
            "status": "active",
            "checkpoint_label": None,
        },
        {
            "index": 2,
            "title": "Second Child",
            "objective": "Do B",
            "materialized_node_id": None,
            "status": "pending",
            "checkpoint_label": None,
        },
        {
            "index": 3,
            "title": "Third Child",
            "objective": "Do C",
            "materialized_node_id": None,
            "status": "pending",
            "checkpoint_label": None,
        },
    ]
