from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import SplitNotAllowed
from backend.services import planningtree_workspace
from backend.services.node_detail_service import NodeDetailService
from backend.services.node_document_service import NodeDocumentService
from backend.services.project_service import ProjectService
from backend.services.split_service import SplitService
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage


class FakeCodexClient:
    def __init__(self, payloads: list[dict] | None = None, *, raw_json_only: bool = False) -> None:
        self.payloads = list(payloads or [])
        self.started_threads: list[str] = []
        self.resumed_threads: list[str] = []
        self.forked_threads: list[dict[str, object]] = []
        self.turns_run: list[str] = []
        self.fail_resume = False
        self.raw_json_only = raw_json_only

    def start_thread(self, **_: object) -> dict[str, str]:
        thread_id = f"thread-{len(self.started_threads) + 1}"
        self.started_threads.append(thread_id)
        return {"thread_id": thread_id}

    def resume_thread(self, thread_id: str, **_: object) -> dict[str, str]:
        self.resumed_threads.append(thread_id)
        if self.fail_resume:
            raise CodexTransportError("thread not found", "not_found")
        return {"thread_id": thread_id}

    def fork_thread(self, source_thread_id: str, **kwargs: object) -> dict[str, str]:
        thread_id = f"fork-thread-{len(self.forked_threads) + 1}"
        self.forked_threads.append(
            {
                "thread_id": thread_id,
                "source_thread_id": source_thread_id,
                **kwargs,
            }
        )
        return {"thread_id": thread_id}

    def run_turn_streaming(self, *_: object, **__: object) -> dict:
        if _:
            self.turns_run.append(str(_[0]))
        payload = self.payloads.pop(0)
        if self.raw_json_only:
            import json

            return {
                "stdout": json.dumps(payload),
                "tool_calls": [],
            }
        return {
            "stdout": "ok",
            "tool_calls": [
                {
                    "tool_name": "emit_render_data",
                    "arguments": {
                        "kind": "split_result",
                        "payload": payload,
                    },
                }
            ],
        }


def create_project(project_service: ProjectService, workspace_root: str) -> dict:
    return project_service.attach_project_folder(workspace_root)


def make_node_split_ready(
    storage: Storage,
    tree_service: TreeService,
    project_id: str,
    node_id: str,
    *,
    shaping_field_line: str = "- target platform: web",
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
            f"{shaping_field_line}\n"
        ),
    )
    detail_service.bump_frame_revision(project_id, node_id)
    state = detail_service.confirm_frame(project_id, node_id)
    assert state["active_step"] == "spec"


def wait_for_terminal_status(service: SplitService, project_id: str, timeout_sec: float = 2.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        status = service.get_split_status(project_id)
        if status["status"] != "active":
            return status
        time.sleep(0.02)
    raise AssertionError("split job did not finish in time")


def make_split_service(
    storage: Storage,
    tree_service: TreeService,
    codex_client: FakeCodexClient,
) -> SplitService:
    return SplitService(
        storage,
        tree_service,
        codex_client,
        ThreadLineageService(storage, codex_client, tree_service),
        split_timeout=5,
    )


def test_split_service_creates_children_and_reuses_parent_audit_thread(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    make_node_split_ready(storage, tree_service, project_id, root_id)
    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            },
            {
                "subtasks": [
                    {"id": "S1", "title": "Detail", "objective": "Detail the first child.", "why_now": "It is the next step."},
                    {"id": "S2", "title": "Polish", "objective": "Polish the child.", "why_now": "It follows detail."},
                ]
            },
        ]
    )
    service = make_split_service(storage, tree_service, fake_client)

    accepted = service.split_node(project_id, root_id, "workflow")
    assert accepted["status"] == "accepted"
    terminal = wait_for_terminal_status(service, project_id)
    assert terminal["status"] == "idle"

    persisted = storage.project_store.load_snapshot(project_id)
    root = persisted["tree_state"]["node_index"][root_id]
    first_child_id = persisted["tree_state"]["active_node_id"]
    project_dir = storage.project_store.project_dir(project_id)
    root_dir = project_dir / planningtree_workspace.ROOT_SEGMENT / "1 workspace"
    first_child_dir = root_dir / "1.1 Prep"

    # Lazy sibling: only first child in child_ids, second is pending in review_state
    assert len(root["child_ids"]) == 1
    assert root["child_ids"][0] == first_child_id

    # Review node created and linked via review_node_id (NOT in child_ids)
    review_node_id = root.get("review_node_id")
    assert review_node_id is not None
    review_node = persisted["tree_state"]["node_index"][review_node_id]
    assert review_node["node_kind"] == "review"
    assert review_node["title"] == "Review"
    assert review_node_id not in root["child_ids"]

    # Review state has K0 checkpoint and pending sibling manifest
    review_state = storage.review_state_store.read_state(project_id, review_node_id)
    assert review_state is not None
    assert len(review_state["checkpoints"]) == 1
    assert review_state["checkpoints"][0]["label"] == "K0"
    assert review_state["checkpoints"][0]["sha"].startswith("sha256:")
    assert len(review_state["pending_siblings"]) == 1
    assert review_state["pending_siblings"][0]["title"] == "Finish"
    assert review_state["pending_siblings"][0]["materialized_node_id"] is None
    assert review_state["rollup"]["status"] == "pending"

    split_state = storage.split_state_store.read_state(project_id)
    assert "thread_id" not in split_state
    assert split_state["active_job"] is None
    assert split_state["last_error"] is None
    assert first_child_dir.is_dir()
    assert (first_child_dir / planningtree_workspace.FRAME_FILE_NAME).read_text(encoding="utf-8") == ""

    root_audit_session = storage.chat_state_store.read_session(project_id, root_id, thread_role="audit")
    review_audit_session = storage.chat_state_store.read_session(project_id, review_node_id, thread_role="audit")
    first_child_audit_session = storage.chat_state_store.read_session(
        project_id,
        first_child_id,
        thread_role="audit",
    )
    root_audit_thread_id = root_audit_session["thread_id"]
    first_child_audit_thread_id = first_child_audit_session["thread_id"]

    assert root_audit_thread_id is not None
    assert review_audit_session["fork_reason"] == "review_bootstrap"
    assert review_audit_session["forked_from_node_id"] == root_id
    assert first_child_audit_session["fork_reason"] == "child_activation"
    assert first_child_audit_session["forked_from_node_id"] == review_node_id

    make_node_split_ready(storage, tree_service, project_id, first_child_id)
    accepted_second = service.split_node(project_id, first_child_id, "phase_breakdown")
    assert accepted_second["status"] == "accepted"
    second_terminal = wait_for_terminal_status(service, project_id)
    assert second_terminal["status"] == "idle"

    second_root_audit_session = storage.chat_state_store.read_session(
        project_id,
        first_child_id,
        thread_role="audit",
    )
    assert second_root_audit_session["thread_id"] == first_child_audit_thread_id
    assert root_audit_thread_id in fake_client.resumed_threads
    assert first_child_audit_thread_id in fake_client.resumed_threads


def test_split_service_rejects_nodes_with_existing_children(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    make_node_split_ready(storage, tree_service, project_id, root_id)
    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            }
        ]
    )
    service = make_split_service(storage, tree_service, fake_client)

    service.split_node(project_id, root_id, "workflow")
    terminal = wait_for_terminal_status(service, project_id)
    assert terminal["status"] == "idle"

    with pytest.raises(SplitNotAllowed):
        service.split_node(project_id, root_id, "workflow")


def test_split_service_recreates_thread_when_resume_fails(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    make_node_split_ready(storage, tree_service, project_id, root_id)
    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            },
            {
                "subtasks": [
                    {"id": "S1", "title": "Detail", "objective": "Detail the first child.", "why_now": "It is the next step."},
                    {"id": "S2", "title": "Polish", "objective": "Polish the child.", "why_now": "It follows detail."},
                ]
            },
        ]
    )
    service = make_split_service(storage, tree_service, fake_client)

    service.split_node(project_id, root_id, "workflow")
    wait_for_terminal_status(service, project_id)
    first_child_id = storage.project_store.load_snapshot(project_id)["tree_state"]["active_node_id"]
    first_child_audit = storage.chat_state_store.read_session(
        project_id,
        first_child_id,
        thread_role="audit",
    )
    first_thread_id = first_child_audit["thread_id"]

    fake_client.fail_resume = True
    make_node_split_ready(storage, tree_service, project_id, first_child_id)
    service.split_node(project_id, first_child_id, "workflow")
    wait_for_terminal_status(service, project_id)
    second_child_audit = storage.chat_state_store.read_session(
        project_id,
        first_child_id,
        thread_role="audit",
    )
    second_thread_id = second_child_audit["thread_id"]

    assert first_thread_id != second_thread_id
    assert len(fake_client.forked_threads) >= 3


def test_split_service_uses_frame_context_not_spec_context(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    make_node_split_ready(
        storage,
        tree_service,
        project_id,
        root_id,
        shaping_field_line="- frontend stack: React + Tailwind",
    )
    persisted = storage.project_store.load_snapshot(project_id)
    workspace_path = Path(str(persisted["project"]["project_path"]))
    node_dir = planningtree_workspace.resolve_node_dir(workspace_path, persisted, root_id)
    assert node_dir is not None

    (node_dir / planningtree_workspace.SPEC_FILE_NAME).write_text(
        "# Overview\nUse Vue + Bootstrap.\n",
        encoding="utf-8",
    )

    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            }
        ]
    )
    service = make_split_service(storage, tree_service, fake_client)

    service.split_node(project_id, root_id, "workflow")
    wait_for_terminal_status(service, project_id)

    prompt = fake_client.turns_run[0]
    assert "Task frame:" in prompt
    assert "React + Tailwind" in prompt
    assert "Technical spec:" not in prompt
    assert "Vue + Bootstrap" not in prompt


def test_split_service_rejects_when_frame_is_not_confirmed(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    service = make_split_service(storage, TreeService(), FakeCodexClient(payloads=[]))

    with pytest.raises(SplitNotAllowed, match="frame is confirmed"):
        service.split_node(project_id, root_id, "workflow")


def test_split_service_rejects_when_clarify_questions_remain(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)
    title = str(storage.project_store.load_snapshot(project_id)["tree_state"]["node_index"][root_id]["title"])
    doc_service.put_document(
        project_id,
        root_id,
        "frame",
        f"# Task Title\n{title}\n\n# Task-Shaping Fields\n- target platform:\n",
    )
    detail_service.bump_frame_revision(project_id, root_id)
    state = detail_service.confirm_frame(project_id, root_id)
    assert state["active_step"] == "clarify"
    service = make_split_service(storage, tree_service, FakeCodexClient(payloads=[]))

    with pytest.raises(SplitNotAllowed, match="no remaining clarify questions"):
        service.split_node(project_id, root_id, "workflow")


def test_split_service_rejects_when_frame_needs_reconfirm(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    doc_service = NodeDocumentService(storage)
    detail_service = NodeDetailService(storage, tree_service)
    title = str(storage.project_store.load_snapshot(project_id)["tree_state"]["node_index"][root_id]["title"])
    doc_service.put_document(
        project_id,
        root_id,
        "frame",
        f"# Task Title\n{title}\n\n# Task-Shaping Fields\n- target platform:\n",
    )
    detail_service.bump_frame_revision(project_id, root_id)
    detail_service.confirm_frame(project_id, root_id)
    detail_service.update_clarify_answers(
        project_id,
        root_id,
        [{"field_name": "target platform", "custom_answer": "web"}],
    )
    state = detail_service.apply_clarify_to_frame(project_id, root_id)
    assert state["active_step"] == "frame"
    assert state["frame_needs_reconfirm"] is True
    service = make_split_service(storage, tree_service, FakeCodexClient(payloads=[]))

    with pytest.raises(SplitNotAllowed, match="re-confirmed"):
        service.split_node(project_id, root_id, "workflow")


def test_split_status_marks_stale_jobs_as_failed(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    service = make_split_service(storage, TreeService(), FakeCodexClient())

    storage.split_state_store.write_state(
        project_id,
        {
            "active_job": {
                "job_id": "split_stale",
                "node_id": root_id,
                "mode": "workflow",
                "started_at": "2026-03-20T00:00:00Z",
            },
            "last_error": None,
        },
    )

    status = service.get_split_status(project_id)

    assert status["status"] == "failed"
    assert "server restarted" in str(status["error"]).lower()


def test_split_service_accepts_raw_json_stdout_fallback_on_legacy_audit_threads(
    storage: Storage,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    snapshot = create_project(project_service, str(workspace_root))
    project_id = snapshot["project"]["id"]
    root_id = snapshot["tree_state"]["root_node_id"]
    tree_service = TreeService()
    make_node_split_ready(storage, tree_service, project_id, root_id)
    fake_client = FakeCodexClient(
        payloads=[
            {
                "subtasks": [
                    {"id": "S1", "title": "Prep", "objective": "Prepare the flow.", "why_now": "It starts the work."},
                    {"id": "S2", "title": "Finish", "objective": "Complete the flow.", "why_now": "It depends on prep."},
                ]
            }
        ],
        raw_json_only=True,
    )
    service = make_split_service(storage, tree_service, fake_client)

    service.split_node(project_id, root_id, "workflow")
    terminal = wait_for_terminal_status(service, project_id)

    assert terminal["status"] == "idle"
    persisted = storage.project_store.load_snapshot(project_id)
    root = persisted["tree_state"]["node_index"][root_id]
    assert len(root["child_ids"]) == 1
