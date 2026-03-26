from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.ai.review_rollup_prompt_builder import build_review_rollup_base_instructions
from backend.ai.codex_client import CodexTransportError
from backend.main import create_app
from backend.services import planningtree_workspace
from backend.services.project_service import ProjectService
from backend.services.thread_lineage_service import ThreadLineageService


class FakeThreadLineageCodexClient:
    def __init__(self) -> None:
        self.started_threads: list[dict[str, object]] = []
        self.resumed_threads: list[dict[str, object]] = []
        self.forked_threads: list[dict[str, object]] = []
        self.missing_thread_ids: set[str] = set()
        self._counter = 0

    def start_thread(self, **kwargs: object) -> dict[str, str]:
        thread_id = self._new_thread_id("start")
        self.started_threads.append({"thread_id": thread_id, **kwargs})
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **kwargs: object) -> dict[str, str]:
        self.resumed_threads.append({"thread_id": thread_id, **kwargs})
        if thread_id in self.missing_thread_ids:
            raise CodexTransportError("thread not found", "not_found")
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **kwargs: object) -> dict[str, str]:
        thread_id = self._new_thread_id("fork")
        self.forked_threads.append(
            {
                "thread_id": thread_id,
                "source_thread_id": source_thread_id,
                **kwargs,
            }
        )
        return {"thread_id": thread_id}

    def _new_thread_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-thread-{self._counter}"


@pytest.fixture
def codex_client() -> FakeThreadLineageCodexClient:
    return FakeThreadLineageCodexClient()


@pytest.fixture
def thread_lineage_service(storage, tree_service, codex_client) -> ThreadLineageService:
    return ThreadLineageService(storage, codex_client, tree_service)


def test_create_app_exposes_thread_lineage_service(data_root: Path) -> None:
    app = create_app(data_root=data_root)
    assert isinstance(app.state.thread_lineage_service, ThreadLineageService)


def test_root_audit_bootstrap_from_empty_session(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])

    session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))

    assert session["thread_role"] == "audit"
    assert session["fork_reason"] == "root_bootstrap"
    assert session["lineage_root_thread_id"] == session["thread_id"]
    assert session["forked_from_thread_id"] is None
    assert len(codex_client.started_threads) == 1
    assert "canonical audit assistant" in str(codex_client.started_threads[0]["base_instructions"]).lower()


def test_root_audit_resume_when_thread_exists(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": "root-thread",
            "thread_role": "audit",
            "fork_reason": "root_bootstrap",
            "lineage_root_thread_id": "root-thread",
            "messages": [],
        },
        thread_role="audit",
    )

    session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))

    assert session["thread_id"] == "root-thread"
    assert [item["thread_id"] for item in codex_client.resumed_threads] == ["root-thread"]
    assert codex_client.started_threads == []


def test_root_audit_rebootstrap_when_resume_missing(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": "missing-root-thread",
            "thread_role": "audit",
            "fork_reason": "root_bootstrap",
            "lineage_root_thread_id": "missing-root-thread",
            "messages": [],
        },
        thread_role="audit",
    )
    codex_client.missing_thread_ids.add("missing-root-thread")

    session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))

    assert session["thread_id"] != "missing-root-thread"
    assert session["fork_reason"] == "root_bootstrap"
    assert session["lineage_root_thread_id"] == session["thread_id"]
    assert len(codex_client.started_threads) == 1


def test_ensure_audit_exists_lazy_bootstrap_for_non_root_without_review_ancestry(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    child_id = _add_task_child(snapshot, root_id, "Child task", "Do the child work")
    _save_snapshot(storage, project_id, snapshot, workspace_root)

    session = thread_lineage_service._ensure_audit_exists(project_id, child_id, str(workspace_root))

    root_session = storage.chat_state_store.read_session(project_id, root_id, thread_role="audit")
    assert session["thread_role"] == "audit"
    assert session["fork_reason"] == "audit_lazy_bootstrap"
    assert session["forked_from_thread_id"] is None
    assert session["lineage_root_thread_id"] == root_session["thread_id"]
    assert len(codex_client.started_threads) == 2


def test_ensure_audit_exists_child_with_review_ancestry_forks_from_review_audit(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    child_id = _add_task_child(snapshot, root_id, "Child task", "Do the child work")
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)

    session = thread_lineage_service._ensure_audit_exists(project_id, child_id, str(workspace_root))

    review_session = storage.chat_state_store.read_session(project_id, review_id, thread_role="audit")
    assert review_session["thread_id"] is not None
    assert review_session["fork_reason"] == "review_bootstrap"
    assert session["thread_role"] == "audit"
    assert session["fork_reason"] == "child_activation"
    assert session["forked_from_node_id"] == review_id
    assert session["forked_from_thread_id"] == review_session["thread_id"]
    assert session["fork_reason"] != "audit_lazy_bootstrap"
    assert len(codex_client.forked_threads) == 2
    assert codex_client.forked_threads[0]["base_instructions"] == build_review_rollup_base_instructions()


def test_ensure_audit_exists_lazy_creates_review_audit_with_rollup_base_instructions(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)

    session = thread_lineage_service._ensure_audit_exists(project_id, review_id, str(workspace_root))

    assert session["thread_role"] == "audit"
    assert session["fork_reason"] == "review_bootstrap"
    assert session["forked_from_node_id"] == root_id
    assert codex_client.forked_threads[-1]["base_instructions"] == build_review_rollup_base_instructions()


def test_ensure_forked_thread_creates_fresh_fork_and_persists_lineage(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    root_session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))

    session = thread_lineage_service.ensure_forked_thread(
        project_id,
        root_id,
        "ask_planning",
        source_node_id=root_id,
        source_role="audit",
        fork_reason="ask_bootstrap",
        workspace_root=str(workspace_root),
        base_instructions="Ask planning base instructions",
        dynamic_tools=[{"name": "emit_frame_content"}],
        writable_roots=[str(workspace_root)],
    )

    assert session["thread_role"] == "ask_planning"
    assert session["forked_from_thread_id"] == root_session["thread_id"]
    assert session["forked_from_node_id"] == root_id
    assert session["forked_from_role"] == "audit"
    assert session["fork_reason"] == "ask_bootstrap"
    assert session["lineage_root_thread_id"] == root_session["lineage_root_thread_id"]
    assert len(codex_client.forked_threads) == 1
    assert codex_client.forked_threads[0]["base_instructions"] == "Ask planning base instructions"
    assert codex_client.forked_threads[0]["dynamic_tools"] == [{"name": "emit_frame_content"}]


def test_ensure_forked_thread_resumes_existing_fork_without_overwriting_metadata(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))
    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": "ask-thread",
            "thread_role": "ask_planning",
            "forked_from_thread_id": "root-thread",
            "forked_from_node_id": root_id,
            "forked_from_role": "audit",
            "fork_reason": "ask_bootstrap",
            "lineage_root_thread_id": "root-thread",
            "messages": [{"message_id": "m1", "role": "assistant", "content": "hi"}],
        },
        thread_role="ask_planning",
    )

    session = thread_lineage_service.ensure_forked_thread(
        project_id,
        root_id,
        "ask_planning",
        source_node_id=root_id,
        source_role="audit",
        fork_reason="ask_bootstrap",
        workspace_root=str(workspace_root),
    )

    assert session["thread_id"] == "ask-thread"
    assert session["forked_from_thread_id"] == "root-thread"
    assert session["messages"][0]["content"] == "hi"
    assert codex_client.forked_threads == []
    assert [item["thread_id"] for item in codex_client.resumed_threads][-1] == "ask-thread"


def test_ensure_forked_thread_legacy_resume_backfills_metadata_without_inventing_ancestry(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))
    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": "legacy-ask-thread",
            "thread_role": "ask_planning",
            "messages": [],
        },
        thread_role="ask_planning",
    )

    session = thread_lineage_service.ensure_forked_thread(
        project_id,
        root_id,
        "ask_planning",
        source_node_id=root_id,
        source_role="audit",
        fork_reason="ask_bootstrap",
        workspace_root=str(workspace_root),
    )

    assert session["thread_id"] == "legacy-ask-thread"
    assert session["fork_reason"] == "legacy_resumed"
    assert session["forked_from_thread_id"] is None
    assert session["forked_from_node_id"] is None
    assert session["forked_from_role"] is None
    assert session["lineage_root_thread_id"] is None


def test_root_legacy_audit_resume_backfills_lineage_root_thread_id(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": "legacy-root-thread",
            "thread_role": "audit",
            "messages": [],
        },
        thread_role="audit",
    )

    session = thread_lineage_service.resume_or_rebuild_session(
        project_id,
        root_id,
        "audit",
        str(workspace_root),
    )

    assert session["thread_id"] == "legacy-root-thread"
    assert session["fork_reason"] == "legacy_resumed"
    assert session["lineage_root_thread_id"] == "legacy-root-thread"


def test_ensure_forked_thread_backfills_root_legacy_source_lineage_before_fork(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": "legacy-root-thread",
            "thread_role": "audit",
            "messages": [],
        },
        thread_role="audit",
    )

    ask_session = thread_lineage_service.ensure_forked_thread(
        project_id,
        root_id,
        "ask_planning",
        source_node_id=root_id,
        source_role="audit",
        fork_reason="ask_bootstrap",
        workspace_root=str(workspace_root),
    )

    root_session = storage.chat_state_store.read_session(project_id, root_id, thread_role="audit")
    assert root_session["fork_reason"] == "legacy_resumed"
    assert root_session["lineage_root_thread_id"] == "legacy-root-thread"
    assert ask_session["forked_from_thread_id"] == "legacy-root-thread"
    assert ask_session["lineage_root_thread_id"] == "legacy-root-thread"


@pytest.mark.parametrize(
    ("thread_role", "fork_reason"),
    [
        ("ask_planning", "ask_bootstrap"),
        ("execution", "execution_bootstrap"),
    ],
)
def test_resume_or_rebuild_session_rebuilds_task_descendants_from_audit(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
    thread_role: str,
    fork_reason: str,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    root_session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))
    storage.chat_state_store.write_session(
        project_id,
        root_id,
        {
            "thread_id": f"missing-{thread_role}",
            "thread_role": thread_role,
            "forked_from_thread_id": root_session["thread_id"],
            "forked_from_node_id": root_id,
            "forked_from_role": "audit",
            "fork_reason": fork_reason,
            "lineage_root_thread_id": root_session["lineage_root_thread_id"],
            "messages": [],
        },
        thread_role=thread_role,
    )
    codex_client.missing_thread_ids.add(f"missing-{thread_role}")

    session = thread_lineage_service.resume_or_rebuild_session(
        project_id,
        root_id,
        thread_role,
        str(workspace_root),
        base_instructions=f"{thread_role} base",
    )

    assert session["thread_role"] == thread_role
    assert session["fork_reason"] == fork_reason
    assert session["forked_from_thread_id"] == root_session["thread_id"]
    assert codex_client.forked_threads[-1]["source_thread_id"] == root_session["thread_id"]


def test_resume_or_rebuild_session_rebuilds_review_audit_from_parent_audit(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)
    root_session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))
    storage.chat_state_store.write_session(
        project_id,
        review_id,
        {
            "thread_id": "missing-review-thread",
            "thread_role": "audit",
            "forked_from_thread_id": root_session["thread_id"],
            "forked_from_node_id": root_id,
            "forked_from_role": "audit",
            "fork_reason": "review_bootstrap",
            "lineage_root_thread_id": root_session["lineage_root_thread_id"],
            "messages": [],
        },
        thread_role="audit",
    )
    codex_client.missing_thread_ids.add("missing-review-thread")

    session = thread_lineage_service.resume_or_rebuild_session(
        project_id,
        review_id,
        "audit",
        str(workspace_root),
    )

    assert session["thread_role"] == "audit"
    assert session["fork_reason"] == "review_bootstrap"
    assert session["forked_from_node_id"] == root_id
    assert codex_client.forked_threads[-1]["source_thread_id"] == root_session["thread_id"]
    assert codex_client.forked_threads[-1]["base_instructions"] == build_review_rollup_base_instructions()


def test_resume_or_rebuild_session_keeps_existing_review_audit_without_thread_level_retrofit(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)
    root_session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))
    storage.chat_state_store.write_session(
        project_id,
        review_id,
        {
            "thread_id": "existing-review-thread",
            "thread_role": "audit",
            "forked_from_thread_id": root_session["thread_id"],
            "forked_from_node_id": root_id,
            "forked_from_role": "audit",
            "fork_reason": "review_bootstrap",
            "lineage_root_thread_id": root_session["lineage_root_thread_id"],
            "messages": [],
        },
        thread_role="audit",
    )

    session = thread_lineage_service.resume_or_rebuild_session(
        project_id,
        review_id,
        "audit",
        str(workspace_root),
        base_instructions=build_review_rollup_base_instructions(),
    )

    assert session["thread_id"] == "existing-review-thread"
    assert [item["thread_id"] for item in codex_client.resumed_threads][-1] == "existing-review-thread"
    assert all(
        item.get("thread_id") != "existing-review-thread" for item in codex_client.forked_threads
    )


def test_resume_or_rebuild_session_rebuilds_child_audit_from_review_audit(
    storage,
    workspace_root: Path,
    thread_lineage_service: ThreadLineageService,
    codex_client: FakeThreadLineageCodexClient,
) -> None:
    snapshot = ProjectService(storage).attach_project_folder(str(workspace_root))
    project_id = str(snapshot["project"]["id"])
    root_id = str(snapshot["tree_state"]["root_node_id"])
    child_id = _add_task_child(snapshot, root_id, "Child task", "Do child work")
    review_id = _add_review_node(snapshot, root_id)
    _save_snapshot(storage, project_id, snapshot, workspace_root)
    root_session = thread_lineage_service.ensure_root_audit_thread(project_id, root_id, str(workspace_root))
    storage.chat_state_store.write_session(
        project_id,
        review_id,
        {
            "thread_id": "missing-review-thread",
            "thread_role": "audit",
            "forked_from_thread_id": root_session["thread_id"],
            "forked_from_node_id": root_id,
            "forked_from_role": "audit",
            "fork_reason": "review_bootstrap",
            "lineage_root_thread_id": root_session["lineage_root_thread_id"],
            "messages": [],
        },
        thread_role="audit",
    )
    codex_client.missing_thread_ids.add("missing-review-thread")

    session = thread_lineage_service.resume_or_rebuild_session(
        project_id,
        child_id,
        "audit",
        str(workspace_root),
    )

    review_session = storage.chat_state_store.read_session(project_id, review_id, thread_role="audit")
    assert session["thread_role"] == "audit"
    assert session["fork_reason"] == "child_activation"
    assert session["forked_from_node_id"] == review_id
    assert session["forked_from_thread_id"] == review_session["thread_id"]
    assert codex_client.forked_threads[-1]["source_thread_id"] == review_session["thread_id"]


def _save_snapshot(storage, project_id: str, snapshot: dict[str, object], workspace_root: Path) -> None:
    storage.project_store.save_snapshot(project_id, snapshot)
    planningtree_workspace.sync_snapshot_tree(workspace_root, snapshot)


def _add_task_child(
    snapshot: dict[str, object],
    parent_id: str,
    title: str,
    description: str,
) -> str:
    node_index = snapshot["tree_state"]["node_index"]
    parent = node_index[parent_id]
    child_id = uuid4().hex
    display_order = len(parent.get("child_ids", []))
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)
    parent.setdefault("child_ids", []).append(child_id)
    node_index[child_id] = {
        "node_id": child_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": title,
        "description": description,
        "status": "ready",
        "node_kind": "original",
        "depth": parent_depth + 1,
        "display_order": display_order,
        "hierarchical_number": f"{parent_hnum}.{display_order + 1}",
        "created_at": snapshot["updated_at"],
    }
    snapshot["updated_at"] = snapshot["updated_at"]
    return child_id


def _add_review_node(snapshot: dict[str, object], parent_id: str) -> str:
    node_index = snapshot["tree_state"]["node_index"]
    parent = node_index[parent_id]
    review_id = uuid4().hex
    parent_hnum = str(parent.get("hierarchical_number") or "1")
    parent_depth = int(parent.get("depth", 0) or 0)
    parent["review_node_id"] = review_id
    node_index[review_id] = {
        "node_id": review_id,
        "parent_id": parent_id,
        "child_ids": [],
        "title": "Review",
        "description": f"Review node for {parent_hnum}",
        "status": "ready",
        "node_kind": "review",
        "depth": parent_depth + 1,
        "display_order": 0,
        "hierarchical_number": f"{parent_hnum}.R",
        "created_at": snapshot["updated_at"],
    }
    return review_id
