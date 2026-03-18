from __future__ import annotations

from backend.ai.codex_client import CodexTransportError
from backend.services.project_service import ProjectService
from backend.services.split_service import SplitService
from backend.services.thread_service import ThreadService
from backend.storage.storage import Storage
from backend.streaming.sse_broker import PlanningEventBroker

CANONICAL_PAYLOAD = {
    "subtasks": [
        {
            "id": "S1",
            "title": "Setup foundation",
            "objective": "Prepare the repo and workspace.",
            "why_now": "This unlocks implementation.",
        },
        {
            "id": "S2",
            "title": "Ship feature",
            "objective": "Land the main feature work.",
            "why_now": "This is the core delivery path.",
        },
        {
            "id": "S3",
            "title": "Validate rollout",
            "objective": "Verify the change end to end.",
            "why_now": "This closes the split safely.",
        },
    ]
}


class FakeSplitCodexClient:
    def __init__(self) -> None:
        self.available_threads: set[str] = set()
        self._planning_counter = 0

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        if thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {thread_id}", "rpc_error")
        return {"thread_id": thread_id}

    def start_planning_thread(
        self,
        *,
        base_instructions: str,
        dynamic_tools: list[dict[str, object]],
        cwd: str | None = None,
        timeout_sec: int = 30,
    ) -> dict[str, object]:
        self._planning_counter += 1
        thread_id = f"planning_{self._planning_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def fork_thread(
        self,
        source_thread_id: str,
        *,
        cwd: str | None = None,
        timeout_sec: int = 30,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        if source_thread_id not in self.available_threads:
            raise CodexTransportError(f"no rollout found for thread id {source_thread_id}", "rpc_error")
        self._planning_counter += 1
        thread_id = f"planning_{self._planning_counter}"
        self.available_threads.add(thread_id)
        return {"thread_id": thread_id}

    def run_turn_streaming(
        self,
        input_text: str,
        *,
        thread_id: str,
        timeout_sec: int = 120,
        cwd: str | None = None,
        on_tool_call=None,
    ) -> dict[str, object]:
        if input_text.startswith("Bootstrap this planning thread"):
            return {
                "stdout": "bootstrap ok",
                "thread_id": thread_id,
                "turn_id": "turn_bootstrap",
                "tool_calls": [],
            }

        payload = CANONICAL_PAYLOAD
        if callable(on_tool_call):
            on_tool_call("emit_render_data", {"kind": "split_result", "payload": payload})
        return {
            "stdout": "Created a valid canonical split.",
            "thread_id": thread_id,
            "turn_id": "turn_visible",
            "tool_calls": [
                {
                    "tool_name": "emit_render_data",
                    "arguments": {"kind": "split_result", "payload": payload},
                }
            ],
        }


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def internal_nodes(snapshot: dict) -> dict[str, dict]:
    return snapshot["tree_state"]["node_index"]


def test_execute_split_turn_materializes_first_leaf_history_and_sets_canonical_lineage(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeSplitCodexClient()
    thread_service = ThreadService(storage, tree_service, client)
    service = SplitService(
        storage,
        tree_service,
        client,
        thread_service,
        PlanningEventBroker(),
        split_timeout=5,
    )

    result = service._execute_split_turn(
        project_id=project_id,
        node_id=root_id,
        mode="workflow",
        confirm_replace=False,
        turn_id="turn_1",
    )

    snapshot = storage.project_store.load_snapshot(project_id)
    nodes = internal_nodes(snapshot)
    first_leaf_id = result["created_child_ids"][0]
    second_leaf_id = result["created_child_ids"][1]

    assert nodes[first_leaf_id]["planning_thread_forked_from_node"] == root_id
    assert nodes[second_leaf_id]["planning_thread_forked_from_node"] == root_id

    first_leaf_turns = storage.thread_store.get_planning_turns(project_id, first_leaf_id)
    second_leaf_turns = storage.thread_store.get_planning_turns(project_id, second_leaf_id)

    assert len(first_leaf_turns) == 3
    assert all(turn["is_inherited"] is True for turn in first_leaf_turns)
    assert all(turn["origin_node_id"] == root_id for turn in first_leaf_turns)
    assert second_leaf_turns == []


def test_apply_split_payload_sets_canonical_lineage_on_created_children(
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_service = ProjectService(storage)
    project_id, root_id = create_project(project_service, str(workspace_root))
    client = FakeSplitCodexClient()
    thread_service = ThreadService(storage, tree_service, client)
    service = SplitService(
        storage,
        tree_service,
        client,
        thread_service,
        PlanningEventBroker(),
        split_timeout=5,
    )

    creation = service._apply_split_payload(
        project_id=project_id,
        node_id=root_id,
        mode="workflow",
        confirm_replace=False,
        payload=CANONICAL_PAYLOAD,
        source="ai",
        task_context={},
    )

    snapshot = storage.project_store.load_snapshot(project_id)
    nodes = internal_nodes(snapshot)
    created_ids = creation["created_child_ids"]
    created_nodes = [nodes[node_id] for node_id in created_ids]

    assert created_nodes
    assert all(node["planning_thread_forked_from_node"] == root_id for node in created_nodes)
