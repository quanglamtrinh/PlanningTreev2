from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from backend.ai.codex_client import CodexTransportError
from backend.ai.review_rollup_prompt_builder import build_review_rollup_output_schema
from backend.errors.app_errors import ReviewNotAllowed
from backend.services import planningtree_workspace
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.review_service import ReviewService
from backend.services.thread_lineage_service import (
    ThreadLineageService,
    _ROLLOUT_BOOTSTRAP_PROMPT,
)
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker


class FakeIntegrationCodexClient:
    def __init__(
        self,
        *,
        summary: str = "Integration draft summary",
        fail: bool = False,
        fail_fork: bool = False,
    ) -> None:
        self.summary = summary
        self.fail = fail
        self.fail_fork = fail_fork
        self.started_threads: list[str] = []
        self.forked_threads: list[dict[str, str]] = []
        self.prompts: list[str] = []

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"integration-thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **_: object) -> dict[str, str]:
        if self.fail_fork:
            raise RuntimeError("fork failed")
        thread_id = f"review-fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(
            {
                "thread_id": thread_id,
                "source_thread_id": source_thread_id,
            }
        )
        return {"thread_id": thread_id}

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            return {"stdout": "READY", "thread_id": str(kwargs.get("thread_id") or "")}
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("integration failed")

        payload = json.dumps({"summary": self.summary})
        on_delta = kwargs.get("on_delta")
        if callable(on_delta):
            on_delta(payload)
        return {
            "stdout": payload,
            "thread_id": str(kwargs.get("thread_id") or ""),
        }


class StrictIntegrationCodexClient(FakeIntegrationCodexClient):
    def __init__(self, *, summary: str = "Integration draft summary") -> None:
        super().__init__(summary=summary)
        self.run_kwargs: list[dict[str, object]] = []

    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            if kwargs.get("sandbox_profile") != "read_only":
                raise RuntimeError("missing read_only sandbox_profile")
            return {"stdout": "READY", "thread_id": str(kwargs.get("thread_id") or "")}
        self.run_kwargs.append(dict(kwargs))
        expected_schema = build_review_rollup_output_schema()
        if kwargs.get("sandbox_profile") != "read_only":
            raise RuntimeError("missing read_only sandbox_profile")
        if kwargs.get("writable_roots") is not None:
            raise RuntimeError("review rollup must not set writable_roots")
        if kwargs.get("output_schema") != expected_schema:
            raise RuntimeError("review rollup must pass the expected output_schema")
        return super().run_turn_streaming(prompt, **kwargs)


class ReadOnlyRejectingIntegrationCodexClient(FakeIntegrationCodexClient):
    def run_turn_streaming(self, prompt: str, **kwargs: object) -> dict[str, str]:
        if prompt == _ROLLOUT_BOOTSTRAP_PROMPT:
            if kwargs.get("sandbox_profile") != "read_only":
                raise RuntimeError("missing read_only sandbox_profile")
            return {"stdout": "READY", "thread_id": str(kwargs.get("thread_id") or "")}
        if kwargs.get("sandbox_profile") == "read_only":
            raise CodexTransportError("read_only sandbox rejected", "invalid_sandbox_policy")
        raise RuntimeError("missing read_only sandbox_profile")


# ── Helpers ──────────────────────────────────────────────────────


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


def make_node_split_ready(
    storage: Storage,
    tree_service: TreeService,
    project_id: str,
    node_id: str,
) -> None:
    snapshot = storage.project_store.load_snapshot(project_id)
    title = str(snapshot["tree_state"]["node_index"][node_id]["title"])
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)
    doc_service.put_document(
        project_id,
        node_id,
        "frame",
        (
            f"# Task Title\n{title}\n\n"
            "# Task-Shaping Fields\n"
            "- target platform: web\n"
        ),
    )
    detail_service.bump_frame_revision(project_id, node_id)
    state = detail_service.confirm_frame(project_id, node_id)
    assert state["active_step"] == "spec"


def simulate_execution_completed(
    storage: Storage, project_id: str, node_id: str, head_sha: str = "sha256:abc123"
) -> None:
    """Simulate a node that has gone through Finish Task and completed execution."""
    storage.execution_state_store.write_state(
        project_id,
        node_id,
        {
            "status": "completed",
            "initial_sha": "sha256:initial000",
            "head_sha": head_sha,
            "started_at": iso_now(),
            "completed_at": iso_now(),
        },
    )


def simulate_full_child_lifecycle(
    storage: Storage,
    tree_service: TreeService,
    review_service: ReviewService,
    project_id: str,
    node_id: str,
    summary: str = "Work completed.",
    head_sha: str = "sha256:child_done",
) -> dict:
    """Make node split-ready, simulate execution, start+accept local review."""
    make_node_split_ready(storage, tree_service, project_id, node_id)
    # Simulate spec confirmation
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)
    doc_service.put_document(
        project_id, node_id, "spec", "# Overview\nDo the thing.\n"
    )
    detail_service.confirm_spec(project_id, node_id)
    simulate_execution_completed(storage, project_id, node_id, head_sha)
    review_service.start_local_review(project_id, node_id)
    return review_service.accept_local_review(project_id, node_id, summary)


def make_review_service(
    storage: Storage,
    tree_service: TreeService,
    *,
    codex_client: FakeIntegrationCodexClient | None = None,
) -> ReviewService:
    thread_lineage_service = None
    if codex_client is not None:
        thread_lineage_service = ThreadLineageService(storage, codex_client, tree_service)
    return ReviewService(
        storage,
        tree_service,
        codex_client=codex_client,
        thread_lineage_service=thread_lineage_service,
        chat_event_broker=ChatEventBroker(),
        chat_timeout=5,
    )


def wait_for_rollup_draft(
    storage: Storage,
    project_id: str,
    review_node_id: str,
    *,
    timeout_sec: float = 2.0,
) -> dict:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        state = storage.review_state_store.read_state(project_id, review_node_id)
        if state is not None:
            draft = state.get("rollup", {}).get("draft", {})
            if isinstance(draft, dict) and draft.get("summary") and draft.get("sha"):
                return state
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for rollup draft.")


def wait_for_integration_terminal(
    storage: Storage,
    project_id: str,
    review_node_id: str,
    *,
    timeout_sec: float = 2.0,
) -> dict:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        session = storage.chat_state_store.read_session(
            project_id, review_node_id, thread_role="audit"
        )
        if not session.get("active_turn_id"):
            messages = session.get("messages", [])
            assistant = next(
                (
                    message
                    for message in reversed(messages)
                    if isinstance(message, dict) and message.get("role") == "assistant"
                ),
                None,
            )
            if assistant is not None and assistant.get("status") in {"completed", "error"}:
                return session
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for integration turn to finish.")


# ── Fake split helper ────────────────────────────────────────────


def do_lazy_split(
    storage: Storage,
    tree_service: TreeService,
    project_id: str,
    node_id: str,
    subtask_count: int = 2,
) -> dict:
    """Perform a lazy split by directly writing to storage (no Codex needed)."""
    from uuid import uuid4
    from backend.services.workspace_sha import compute_workspace_sha

    snapshot = storage.project_store.load_snapshot(project_id)
    node_by_id = tree_service.node_index(snapshot)
    parent = node_by_id[node_id]
    now = iso_now()
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)

    subtasks = [
        {"title": f"Subtask {i}", "objective": f"Do subtask {i}.", "why_now": f"Step {i}."}
        for i in range(1, subtask_count + 1)
    ]

    # First child
    first_child_id = uuid4().hex
    first_child = {
        "node_id": first_child_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": subtasks[0]["title"],
        "description": subtasks[0]["objective"],
        "status": "ready",
        "node_kind": "original",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.1",
        "created_at": now,
    }
    parent.setdefault("child_ids", []).append(first_child_id)
    snapshot["tree_state"]["node_index"][first_child_id] = first_child

    # Review node
    review_node_id = uuid4().hex
    review_node = {
        "node_id": review_node_id,
        "parent_id": node_id,
        "child_ids": [],
        "title": "Review",
        "description": f"Review node for {parent_hnum}",
        "status": "ready",
        "node_kind": "review",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.R",
        "created_at": now,
    }
    snapshot["tree_state"]["node_index"][review_node_id] = review_node
    parent["review_node_id"] = review_node_id

    # K0 checkpoint
    workspace_root = str(snapshot["project"]["project_path"])
    k0_sha = compute_workspace_sha(Path(workspace_root))

    pending_siblings = [
        {
            "index": i,
            "title": subtasks[i - 1]["title"],
            "objective": subtasks[i - 1]["objective"],
            "materialized_node_id": None,
        }
        for i in range(2, subtask_count + 1)
    ]

    review_state = {
        "checkpoints": [
            {
                "label": "K0",
                "sha": k0_sha,
                "summary": None,
                "source_node_id": None,
                "accepted_at": now,
            }
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": pending_siblings,
    }
    storage.review_state_store.write_state(project_id, review_node_id, review_state)

    if parent.get("status") in {"ready", "in_progress"}:
        parent["status"] = "draft"
    snapshot["tree_state"]["active_node_id"] = first_child_id
    snapshot["updated_at"] = now
    storage.project_store.save_snapshot(project_id, snapshot)

    # Sync workspace dirs
    planningtree_workspace.sync_snapshot_tree(Path(workspace_root), snapshot)

    return {
        "first_child_id": first_child_id,
        "review_node_id": review_node_id,
        "k0_sha": k0_sha,
    }


# ── Tests: start_local_review ────────────────────────────────────


def test_start_local_review_transitions_completed_to_review_pending(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(storage, tree_service)

    simulate_execution_completed(storage, project_id, root_id)

    result = review_service.start_local_review(project_id, root_id)
    assert result["status"] == "review_pending"
    assert result["local_review_started_at"] is not None
    assert result["local_review_prompt_consumed_at"] is None

    # Verify persisted
    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "review_pending"
    assert exec_state["local_review_started_at"] is not None
    assert exec_state["local_review_prompt_consumed_at"] is None


def test_start_local_review_rejects_non_completed_status(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = make_review_service(storage, TreeService())

    # No execution state at all
    with pytest.raises(ReviewNotAllowed, match="No execution state"):
        review_service.start_local_review(project_id, root_id)

    # Executing (not completed)
    storage.execution_state_store.write_state(
        project_id, root_id, {"status": "executing", "started_at": iso_now()}
    )
    with pytest.raises(ReviewNotAllowed, match="executing"):
        review_service.start_local_review(project_id, root_id)


# ── Tests: accept_local_review ────────────────────────────────────


def test_accept_local_review_transitions_to_review_accepted_and_marks_done(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(storage, tree_service)

    simulate_execution_completed(storage, project_id, root_id)
    review_service.start_local_review(project_id, root_id)

    result = review_service.accept_local_review(project_id, root_id, "Looks good.")
    assert result["status"] == "review_accepted"

    exec_state = storage.execution_state_store.read_state(project_id, root_id)
    assert exec_state is not None
    assert exec_state["status"] == "review_accepted"
    assert exec_state["local_review_started_at"] is not None
    assert exec_state["local_review_prompt_consumed_at"] is not None

    persisted = storage.project_store.load_snapshot(project_id)
    node = persisted["tree_state"]["node_index"][root_id]
    assert node["status"] == "done"


def test_accept_local_review_rejects_empty_summary(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = make_review_service(storage, TreeService())

    simulate_execution_completed(storage, project_id, root_id)
    review_service.start_local_review(project_id, root_id)

    with pytest.raises(ReviewNotAllowed, match="non-empty summary"):
        review_service.accept_local_review(project_id, root_id, "")

    with pytest.raises(ReviewNotAllowed, match="non-empty summary"):
        review_service.accept_local_review(project_id, root_id, "   ")


def test_accept_local_review_rejects_non_review_pending(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = make_review_service(storage, TreeService())

    simulate_execution_completed(storage, project_id, root_id)
    # Status is "completed", not "review_pending"
    with pytest.raises(ReviewNotAllowed, match="completed"):
        review_service.accept_local_review(project_id, root_id, "Summary")


# ── Tests: checkpoint progression ─────────────────────────────────


def test_accept_local_review_appends_checkpoint_to_review_node(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete first child's execution and review
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:child1_head")
    review_service.start_local_review(project_id, first_child_id)
    review_service.accept_local_review(project_id, first_child_id, "First child done.")

    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert len(review_state["checkpoints"]) == 2
    assert review_state["checkpoints"][0]["label"] == "K0"
    assert review_state["checkpoints"][1]["label"] == "K1"
    assert review_state["checkpoints"][1]["sha"] == "sha256:child1_head"
    assert review_state["checkpoints"][1]["summary"] == "First child done."
    assert review_state["checkpoints"][1]["source_node_id"] == first_child_id


# ── Tests: lazy sibling activation ────────────────────────────────


def test_accept_local_review_activates_next_sibling(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=3)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete first child
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:child1_done")
    review_service.start_local_review(project_id, first_child_id)
    result = review_service.accept_local_review(project_id, first_child_id, "Child 1 done.")

    # Should have activated sibling 2
    activated_id = result["activated_sibling_id"]
    assert activated_id is not None

    persisted = storage.project_store.load_snapshot(project_id)
    node_index = persisted["tree_state"]["node_index"]
    parent = node_index[root_id]

    # Parent should have 2 children now
    assert len(parent["child_ids"]) == 2
    assert parent["child_ids"][1] == activated_id

    # Activated sibling should be ready
    sibling = node_index[activated_id]
    assert sibling["status"] == "ready"
    assert sibling["title"] == "Subtask 2"
    assert sibling["hierarchical_number"].endswith(".2")

    # Should be the active node
    assert persisted["tree_state"]["active_node_id"] == activated_id

    # Manifest should show materialized
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    materialized = [
        s for s in review_state["pending_siblings"] if s["materialized_node_id"] is not None
    ]
    assert len(materialized) == 1
    assert materialized[0]["materialized_node_id"] == activated_id


def test_accept_local_review_eager_forks_child_audit_from_review_audit(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    codex_client = FakeIntegrationCodexClient()
    review_service = make_review_service(storage, tree_service, codex_client=codex_client)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=3)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    simulate_execution_completed(storage, project_id, first_child_id, "sha256:child1_done")
    review_service.start_local_review(project_id, first_child_id)
    result = review_service.accept_local_review(project_id, first_child_id, "Child 1 done.")

    activated_id = result["activated_sibling_id"]
    assert activated_id is not None

    review_audit_session = storage.chat_state_store.read_session(
        project_id,
        review_node_id,
        thread_role="audit",
    )
    child_audit_session = storage.chat_state_store.read_session(
        project_id,
        activated_id,
        thread_role="audit",
    )

    assert review_audit_session["thread_id"] is not None
    assert review_audit_session["fork_reason"] == "review_bootstrap"
    assert child_audit_session["thread_id"] is not None
    assert child_audit_session["fork_reason"] == "child_activation"
    assert child_audit_session["forked_from_node_id"] == review_node_id
    assert len(codex_client.forked_threads) >= 2


def test_accept_local_review_keeps_checkpoint_when_child_bootstrap_fails(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(
        storage,
        tree_service,
        codex_client=FakeIntegrationCodexClient(fail_fork=True),
    )

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=3)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    simulate_execution_completed(storage, project_id, first_child_id, "sha256:child1_done")
    review_service.start_local_review(project_id, first_child_id)
    result = review_service.accept_local_review(project_id, first_child_id, "Child 1 done.")

    activated_id = result["activated_sibling_id"]
    assert activated_id is not None

    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["checkpoints"][-1]["summary"] == "Child 1 done."

    persisted = storage.project_store.load_snapshot(project_id)
    assert persisted["tree_state"]["active_node_id"] == activated_id
    child_audit_session = storage.chat_state_store.read_session(
        project_id,
        activated_id,
        thread_role="audit",
    )
    assert child_audit_session["thread_id"] is None


# ── Tests: legacy eager path ─────────────────────────────────────


def test_accept_local_review_unlocks_legacy_eager_sibling(
    storage: Storage, workspace_root,
) -> None:
    """Legacy trees without review_node_id should unlock next locked sibling."""
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(storage, tree_service)

    # Manually create legacy eager children
    persisted = storage.project_store.load_snapshot(project_id)
    node_index = persisted["tree_state"]["node_index"]
    parent = node_index[root_id]
    now = iso_now()

    child_a_id = "legacy_child_a"
    child_b_id = "legacy_child_b"
    node_index[child_a_id] = {
        "node_id": child_a_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Child A",
        "description": "First child",
        "status": "ready",
        "node_kind": "original",
        "depth": 1,
        "display_order": 0,
        "hierarchical_number": "1.1",
        "created_at": now,
    }
    node_index[child_b_id] = {
        "node_id": child_b_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Child B",
        "description": "Second child",
        "status": "locked",
        "node_kind": "original",
        "depth": 1,
        "display_order": 1,
        "hierarchical_number": "1.2",
        "created_at": now,
    }
    parent["child_ids"] = [child_a_id, child_b_id]
    parent["status"] = "draft"
    persisted["tree_state"]["active_node_id"] = child_a_id
    storage.project_store.save_snapshot(project_id, persisted)

    # Complete child A
    simulate_execution_completed(storage, project_id, child_a_id)
    review_service.start_local_review(project_id, child_a_id)
    result = review_service.accept_local_review(project_id, child_a_id, "Legacy child done.")

    # Child B should be unlocked
    persisted = storage.project_store.load_snapshot(project_id)
    child_b = persisted["tree_state"]["node_index"][child_b_id]
    assert child_b["status"] == "ready"
    assert persisted["tree_state"]["active_node_id"] == child_b_id


# ── Tests: rollup readiness ──────────────────────────────────────


def test_rollup_becomes_ready_when_all_siblings_accepted(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    codex_client = FakeIntegrationCodexClient(summary="Integrated successfully.")
    review_service = make_review_service(storage, tree_service, codex_client=codex_client)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete first child -> activates second
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:c1")
    review_service.start_local_review(project_id, first_child_id)
    result1 = review_service.accept_local_review(project_id, first_child_id, "Child 1 done.")
    second_child_id = result1["activated_sibling_id"]
    assert second_child_id is not None

    # Rollup should still be pending
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "pending"

    # Complete second child
    simulate_execution_completed(storage, project_id, second_child_id, "sha256:c2")
    review_service.start_local_review(project_id, second_child_id)
    review_service.accept_local_review(project_id, second_child_id, "Child 2 done.")

    review_state = wait_for_rollup_draft(storage, project_id, review_node_id)
    assert review_state["rollup"]["status"] == "ready"
    assert review_state["rollup"]["draft"]["summary"] == "Integrated successfully."
    assert review_state["rollup"]["draft"]["sha"].startswith("sha256:")
    assert len(codex_client.started_threads) == 1

    # Checkpoint chain: K0, K1, K2
    assert len(review_state["checkpoints"]) == 3
    assert review_state["checkpoints"][2]["label"] == "K2"

    session = wait_for_integration_terminal(storage, project_id, review_node_id)
    assistant = next(
        message for message in reversed(session["messages"]) if message.get("role") == "assistant"
    )
    assert assistant["status"] == "completed"
    assert "Integrated successfully." in assistant["content"]


def test_integration_rollup_uses_read_only_sandbox_and_output_schema(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    codex_client = StrictIntegrationCodexClient(summary="Read-only integration summary.")
    review_service = make_review_service(storage, tree_service, codex_client=codex_client)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=1)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    simulate_execution_completed(storage, project_id, first_child_id, "sha256:only-child")
    review_service.start_local_review(project_id, first_child_id)
    review_service.accept_local_review(project_id, first_child_id, "Only child done.")

    wait_for_rollup_draft(storage, project_id, review_node_id)
    session = wait_for_integration_terminal(storage, project_id, review_node_id)
    assistant = next(
        message for message in reversed(session["messages"]) if message.get("role") == "assistant"
    )

    assert assistant["status"] == "completed"
    assert len(codex_client.run_kwargs) == 1
    assert codex_client.run_kwargs[0]["sandbox_profile"] == "read_only"
    assert codex_client.run_kwargs[0]["writable_roots"] is None
    assert codex_client.run_kwargs[0]["output_schema"] == build_review_rollup_output_schema()


def test_integration_rollup_read_only_sandbox_error_marks_session_failed(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(
        storage,
        tree_service,
        codex_client=ReadOnlyRejectingIntegrationCodexClient(),
    )

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=1)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    simulate_execution_completed(storage, project_id, first_child_id, "sha256:only-child")
    review_service.start_local_review(project_id, first_child_id)
    review_service.accept_local_review(project_id, first_child_id, "Only child done.")

    session = wait_for_integration_terminal(storage, project_id, review_node_id)
    assistant = next(
        message for message in reversed(session["messages"]) if message.get("role") == "assistant"
    )

    assert assistant["status"] == "error"
    assert assistant["error"] == "read_only sandbox rejected"
    assert session.get("active_turn_id") is None
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["draft"] == {
        "summary": None,
        "sha": None,
        "generated_at": None,
    }


def test_integration_rollup_failure_keeps_ready_without_draft_and_marks_session_error(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(
        storage,
        tree_service,
        codex_client=FakeIntegrationCodexClient(fail=True),
    )

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=1)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    simulate_execution_completed(storage, project_id, first_child_id, "sha256:only-child")
    review_service.start_local_review(project_id, first_child_id)
    review_service.accept_local_review(project_id, first_child_id, "Only child done.")

    session = wait_for_integration_terminal(storage, project_id, review_node_id)
    assistant = next(
        message for message in reversed(session["messages"]) if message.get("role") == "assistant"
    )
    assert assistant["status"] == "error"
    assert assistant["error"] == "integration failed"

    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "ready"
    assert review_state["rollup"]["draft"] == {
        "summary": None,
        "sha": None,
        "generated_at": None,
    }


# ── Tests: accept_rollup_review ──────────────────────────────────


def test_integration_rollup_can_retry_after_error_and_persist_new_draft(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    codex_client = FakeIntegrationCodexClient(fail=True)
    review_service = make_review_service(
        storage,
        tree_service,
        codex_client=codex_client,
    )

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=1)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    simulate_execution_completed(storage, project_id, first_child_id, "sha256:only-child")
    review_service.start_local_review(project_id, first_child_id)
    review_service.accept_local_review(project_id, first_child_id, "Only child done.")

    failed_session = wait_for_integration_terminal(storage, project_id, review_node_id)
    failed_assistant = next(
        message
        for message in reversed(failed_session["messages"])
        if message.get("role") == "assistant"
    )
    assert failed_assistant["status"] == "error"

    codex_client.fail = False
    codex_client.summary = "Recovered integration draft."

    restarted = review_service.start_review_rollup(project_id, review_node_id)
    assert restarted is True

    review_state = wait_for_rollup_draft(storage, project_id, review_node_id)
    assert review_state["rollup"]["draft"]["summary"] == "Recovered integration draft."
    assert review_state["rollup"]["draft"]["sha"].startswith("sha256:")
    assert len(codex_client.started_threads) == 1

    session = wait_for_integration_terminal(storage, project_id, review_node_id)
    assistants = [
        message
        for message in session["messages"]
        if isinstance(message, dict) and message.get("role") == "assistant"
    ]
    assert [message["status"] for message in assistants[-2:]] == ["error", "completed"]
    assert "Recovered integration draft." in assistants[-1]["content"]


def test_accept_rollup_review_sets_accepted_and_appends_to_parent_audit(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    codex_client = FakeIntegrationCodexClient(summary="Integration looks good.")
    review_service = make_review_service(storage, tree_service, codex_client=codex_client)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # Complete both children to get rollup to "ready"
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:c1")
    review_service.start_local_review(project_id, first_child_id)
    result1 = review_service.accept_local_review(project_id, first_child_id, "C1 done.")
    second_child_id = result1["activated_sibling_id"]
    assert second_child_id is not None

    simulate_execution_completed(storage, project_id, second_child_id, "sha256:c2")
    review_service.start_local_review(project_id, second_child_id)
    review_service.accept_local_review(project_id, second_child_id, "C2 done.")

    review_state = wait_for_rollup_draft(storage, project_id, review_node_id)
    draft_sha = review_state["rollup"]["draft"]["sha"]
    assert draft_sha is not None

    (workspace_root / "changed-after-draft.txt").write_text("new content\n", encoding="utf-8")

    result = review_service.accept_rollup_review(project_id, review_node_id)
    assert result["rollup_status"] == "accepted"
    assert result["summary"] == "Integration looks good."
    assert result["sha"] == draft_sha

    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "accepted"
    assert review_state["rollup"]["summary"] == "Integration looks good."
    assert review_state["rollup"]["sha"] == draft_sha
    assert review_state["rollup"]["package_review_started_at"] is not None
    assert review_state["rollup"]["package_review_prompt_consumed_at"] is None
    assert review_state["rollup"]["draft"] == {
        "summary": None,
        "sha": None,
        "generated_at": None,
    }

    audit_session = storage.chat_state_store.read_session(
        project_id, root_id, thread_role="audit"
    )
    messages = audit_session.get("messages", [])
    rollup_msgs = [m for m in messages if m.get("message_id") == "audit-package:rollup"]
    assert len(rollup_msgs) == 1
    assert "Integration looks good." in rollup_msgs[0]["content"]
    assert draft_sha in rollup_msgs[0]["content"]


def test_accept_rollup_review_rejects_non_ready(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=2)
    review_node_id = split_result["review_node_id"]

    # Rollup is still "pending"
    with pytest.raises(ReviewNotAllowed, match="pending"):
        review_service.accept_rollup_review(project_id, review_node_id)


def test_accept_rollup_review_rejects_missing_draft(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = make_review_service(storage, TreeService())

    split_result = do_lazy_split(storage, TreeService(), project_id, root_id, subtask_count=1)
    review_node_id = split_result["review_node_id"]
    storage.review_state_store.set_rollup(project_id, review_node_id, "ready")

    with pytest.raises(ReviewNotAllowed, match="draft summary and sha"):
        review_service.accept_rollup_review(project_id, review_node_id)


def test_accept_rollup_review_rejects_while_integration_turn_is_active(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    review_service = make_review_service(storage, TreeService())

    split_result = do_lazy_split(storage, TreeService(), project_id, root_id, subtask_count=1)
    review_node_id = split_result["review_node_id"]
    storage.review_state_store.set_rollup(project_id, review_node_id, "ready")
    storage.review_state_store.set_rollup_draft(
        project_id,
        review_node_id,
        summary="Draft exists",
        sha="sha256:draft",
    )

    session = storage.chat_state_store.clear_session(
        project_id,
        review_node_id,
        thread_role="audit",
    )
    session["active_turn_id"] = "rollup-turn-1"
    session["messages"].append(
        {
            "message_id": "msg-active",
            "role": "assistant",
            "content": "",
            "status": "pending",
            "error": None,
            "turn_id": "rollup-turn-1",
            "created_at": iso_now(),
            "updated_at": iso_now(),
        }
    )
    storage.chat_state_store.write_session(
        project_id,
        review_node_id,
        session,
        thread_role="audit",
    )

    with pytest.raises(ReviewNotAllowed, match="still running"):
        review_service.accept_rollup_review(project_id, review_node_id)


# ── Tests: single-child split ────────────────────────────────────


def test_single_child_split_rollup_ready_after_one_review(
    storage: Storage, workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    review_service = make_review_service(storage, tree_service)

    split_result = do_lazy_split(storage, tree_service, project_id, root_id, subtask_count=1)
    first_child_id = split_result["first_child_id"]
    review_node_id = split_result["review_node_id"]

    # No pending siblings — rollup should become ready after one child
    simulate_execution_completed(storage, project_id, first_child_id, "sha256:only_child")
    review_service.start_local_review(project_id, first_child_id)
    result = review_service.accept_local_review(project_id, first_child_id, "Only child done.")

    # No sibling to activate
    assert result["activated_sibling_id"] is None

    # Rollup should be ready
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert review_state["rollup"]["status"] == "ready"
