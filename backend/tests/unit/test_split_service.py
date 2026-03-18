from __future__ import annotations

import json
import time
from uuid import uuid4

import pytest

from backend.errors.app_errors import SplitNotAllowed
from backend.services.project_service import ProjectService
from backend.services.split_service import SplitService, split_runtime_bundle_for_mode
from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY
from backend.storage.storage import Storage
from backend.streaming.sse_broker import PlanningEventBroker


class FakeCodexClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []
        self.restart_calls = 0

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
    ) -> dict[str, object]:
        self.calls.append(
            {
                "prompt": prompt,
                "thread_id": thread_id,
                "timeout_sec": timeout_sec,
            }
        )
        if not self.outcomes:
            raise AssertionError("No fake Codex outcomes remaining")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        if isinstance(outcome, dict):
            response = dict(outcome)
        else:
            raw_text = str(outcome)
            response = {"stdout": raw_text}
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                response["stdout"] = ""
                response["tool_calls"] = [
                    {
                        "tool_name": "emit_render_data",
                        "arguments": {
                            "kind": "split_result",
                            "payload": payload,
                        },
                    }
                ]
            else:
                response["tool_calls"] = []

        response.setdefault("stdout", "")
        response.setdefault("tool_calls", [])
        response.setdefault("thread_id", thread_id or f"thread_{len(self.calls)}")

        if callable(on_tool_call):
            for tool_call in response["tool_calls"]:
                arguments = tool_call.get("arguments")
                if isinstance(arguments, dict):
                    on_tool_call(str(tool_call.get("tool_name") or ""), arguments)
        return response

    def restart(self) -> None:
        self.restart_calls += 1


class FakeThreadService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def ensure_planning_thread(
        self,
        project_id: str,
        node_id: str,
        *,
        source_node_id: str | None = None,
    ) -> str:
        return "planning_1"

    def set_planning_status(
        self,
        project_id: str,
        node_id: str,
        *,
        status: str | None,
        active_turn_id: str | None,
    ) -> dict[str, object]:
        return self._storage.thread_store.set_planning_status(
            project_id,
            node_id,
            status=status,
            active_turn_id=active_turn_id,
        )

    def materialize_inherited_planning_history(self, project_id: str, node_id: str) -> list[dict[str, object]]:
        return self._storage.thread_store.get_planning_turns(project_id, node_id)

    def append_visible_planning_turn(
        self,
        project_id: str,
        node_id: str,
        *,
        turn_id: str,
        user_content: str,
        tool_calls: list[dict[str, object]],
        assistant_content: str,
        timestamp: str,
    ) -> list[dict[str, object]]:
        entries = [
            {
                "turn_id": turn_id,
                "role": "user",
                "content": user_content,
                "timestamp": timestamp,
                "is_inherited": False,
                "origin_node_id": node_id,
            }
        ]
        for tool_call in tool_calls:
            entries.append(
                {
                    "turn_id": turn_id,
                    "role": "tool_call",
                    "tool_name": tool_call.get("tool_name"),
                    "arguments": tool_call.get("arguments", {}),
                    "timestamp": timestamp,
                    "is_inherited": False,
                    "origin_node_id": node_id,
                }
            )
        entries.append(
            {
                "turn_id": turn_id,
                "role": "assistant",
                "content": assistant_content,
                "timestamp": timestamp,
                "is_inherited": False,
                "origin_node_id": node_id,
            }
        )
        for entry in entries:
            self._storage.thread_store.append_planning_turn(project_id, node_id, entry)
        return entries

    def fork_planning_thread(self, project_id: str, source_node_id: str, target_node_id: str) -> str:
        return "planning_1"


def wait_for_split_completion(
    storage: Storage,
    project_id: str,
    node_id: str,
    timeout: float = 3.0,
) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        planning = storage.thread_store.peek_node_state(project_id, node_id).get("planning", {})
        if planning.get("active_turn_id") is None and str(planning.get("status") or "") != "active":
            return load_snapshot(storage, project_id)
        time.sleep(0.02)
    raise AssertionError(f"split did not complete for {node_id}")


class SplitServiceAdapter:
    def __init__(self, service: SplitService, storage: Storage) -> None:
        self._service = service
        self._storage = storage

    def split_node(
        self,
        project_id: str,
        node_id: str,
        mode: str,
        confirm_replace: bool = False,
    ) -> dict[str, object]:
        self._service.split_node(project_id, node_id, mode, confirm_replace)
        return wait_for_split_completion(self._storage, project_id, node_id)

    def __getattr__(self, name: str):
        return getattr(self._service, name)


def create_project(project_service: ProjectService, workspace_root: str) -> tuple[str, str]:
    project_service.set_workspace_root(workspace_root)
    snapshot = project_service.create_project("Alpha", "Ship phase 5")
    return snapshot["project"]["id"], snapshot["tree_state"]["root_node_id"]


def load_snapshot(storage: Storage, project_id: str) -> dict:
    return storage.project_store.load_snapshot(project_id)


def save_snapshot(storage: Storage, project_id: str, snapshot: dict) -> None:
    storage.project_store.save_snapshot(project_id, snapshot)


def set_node_phase(storage: Storage, project_id: str, node_id: str, phase: str) -> None:
    snapshot = load_snapshot(storage, project_id)
    node_by_id(snapshot)[node_id]["phase"] = phase
    save_snapshot(storage, project_id, snapshot)
    state = storage.node_store.load_state(project_id, node_id)
    state["phase"] = phase
    storage.node_store.save_state(project_id, node_id, state)


def node_by_id(snapshot: dict) -> dict[str, dict]:
    tree_state = snapshot["tree_state"]
    node_index = tree_state.get("node_index")
    if isinstance(node_index, dict):
        return node_index
    return {node["node_id"]: node for node in tree_state["node_registry"]}


def make_service(storage: Storage, tree_service, fake_client: FakeCodexClient) -> SplitService:
    service = SplitService(
        storage,
        tree_service,
        fake_client,
        thread_service=FakeThreadService(storage),
        planning_event_broker=PlanningEventBroker(),
        split_timeout=5,
    )
    return SplitServiceAdapter(service, storage)


def _canonical_payload_for_mode(mode: str) -> dict[str, object]:
    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]  # type: ignore[index]
    subtasks = []
    for index in range(1, spec["min_items"] + 1):
        subtasks.append(
            {
                "id": f"S{index}",
                "title": f"{mode} step {index}",
                "objective": f"Objective {index} for {mode}",
                "why_now": f"Reason {index} for {mode}",
            }
        )
    return {"subtasks": subtasks}


def seed_ask_packets(storage: Storage, project_id: str, node_id: str, *statuses: str) -> None:
    ask_state = storage.thread_store.get_ask_state(project_id, node_id)
    packets = []
    for index, status in enumerate(statuses, start=1):
        packets.append(
            {
                "packet_id": f"dctx_{index}",
                "node_id": node_id,
                "created_at": "2026-03-11T00:00:00Z",
                "source_message_ids": [],
                "summary": f"Packet {index}",
                "context_text": f"Context {index}",
                "status": status,
                "status_reason": None,
                "merged_at": None,
                "merged_planning_turn_id": None,
                "suggested_by": "user",
            }
        )
    ask_state["delta_context_packets"] = packets
    storage.thread_store.write_ask_session(project_id, node_id, ask_state)


def test_apply_split_payload_cleans_up_node_files_when_snapshot_save_fails(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = make_service(storage, tree_service, FakeCodexClient([]))

    def fail_save_snapshot(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(storage.project_store, "save_snapshot", fail_save_snapshot)

    with pytest.raises(OSError, match="disk full"):
        service._apply_split_payload(
            project_id=project_id,
            node_id=root_id,
            mode="workflow",
            confirm_replace=False,
            payload=_canonical_payload_for_mode("workflow"),
            source="ai",
            task_context={"parent_chain_truncated": False},
        )

    nodes_dir = storage.node_store.node_dir(project_id, root_id).parent
    assert sorted(path.name for path in nodes_dir.iterdir() if path.is_dir()) == [root_id]
    persisted = load_snapshot(storage, project_id)
    assert node_by_id(persisted)[root_id]["child_ids"] == []


def test_split_runtime_bundle_for_mode_selects_canonical_helpers() -> None:
    bundle = split_runtime_bundle_for_mode("workflow")

    assert bundle.output_family == "flat_subtasks_v1"
    assert bundle.validate_payload(_canonical_payload_for_mode("workflow")) is True
    assert bundle.validate_payload({"subtasks": [{"order": 1, "prompt": "legacy"}]}) is False
    assert "Split a parent task into a small set of sequential workflow-based subtasks." in bundle.build_attempt_prompt(
        {"current_node_prompt": "Ship workflow", "root_prompt": "Alpha"},
        None,
    )


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_apply_split_payload_materializes_all_canonical_modes_through_flat_family(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    mode: str,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = make_service(storage, tree_service, FakeCodexClient([]))

    service._apply_split_payload(
        project_id=project_id,
        node_id=root_id,
        mode=mode,  # type: ignore[arg-type]
        confirm_replace=False,
        payload=_canonical_payload_for_mode(mode),
        source="ai",
        task_context={"parent_chain_truncated": False},
    )

    persisted = load_snapshot(storage, project_id)
    nodes = node_by_id(persisted)
    root = nodes[root_id]
    children = [nodes[child_id] for child_id in root["split_metadata"]["created_child_ids"]]
    first_child_task = storage.node_store.load_task(project_id, children[0]["node_id"])
    materialized = root["split_metadata"]["materialized"]

    assert root["planning_mode"] == mode
    assert root["split_metadata"]["output_family"] == "flat_subtasks_v1"
    assert root["split_metadata"]["revision"] == 1
    assert [child["status"] for child in children] == ["ready", *["locked"] * (len(children) - 1)]
    assert all(child["planning_thread_forked_from_node"] == root_id for child in children)
    assert first_child_task["title"] == f"{mode} step 1"
    assert first_child_task["purpose"] == f"Objective 1 for {mode}\n\nWhy now: Reason 1 for {mode}"
    assert persisted["tree_state"]["active_node_id"] == children[0]["node_id"]
    assert materialized["family"] == "flat_subtasks_v1"
    assert [item["subtask_id"] for item in materialized["subtasks"]] == [
        f"S{index}" for index in range(1, len(children) + 1)
    ]
    assert [item["child_node_id"] for item in materialized["subtasks"]] == root["split_metadata"]["created_child_ids"]
    assert root["split_metadata"]["debug_payload"] == _canonical_payload_for_mode(mode)


def test_apply_split_payload_materialization_is_shared_across_canonical_modes_with_same_output_family(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    shared_payload = {
        "subtasks": [
            {
                "id": "S1",
                "title": "Shared setup",
                "objective": "Prepare the workspace for the split.",
                "why_now": "This unlocks the remaining work.",
            },
            {
                "id": "S2",
                "title": "Shared implementation",
                "objective": "Deliver the main implementation branch.",
                "why_now": "This is the core delivery path.",
            },
            {
                "id": "S3",
                "title": "Shared verification",
                "objective": "Validate behavior and handoff.",
                "why_now": "This closes the loop cleanly.",
            },
        ]
    }
    materialized_by_mode: dict[str, dict[str, object]] = {}

    for mode in ("workflow", "phase_breakdown"):
        project_id, root_id = create_project(project_service, str(workspace_root))
        service = make_service(storage, tree_service, FakeCodexClient([]))

        service._apply_split_payload(
            project_id=project_id,
            node_id=root_id,
            mode=mode,
            confirm_replace=False,
            payload=shared_payload,
            source="ai",
            task_context={"parent_chain_truncated": False},
        )

        persisted = load_snapshot(storage, project_id)
        root = node_by_id(persisted)[root_id]
        created_child_ids = root["split_metadata"]["created_child_ids"]
        materialized = root["split_metadata"]["materialized"]
        created_tasks = [
            storage.node_store.load_task(project_id, child_node_id)
            for child_node_id in created_child_ids
        ]

        materialized_by_mode[mode] = {
            "tasks": [
                {
                    "title": task["title"],
                    "purpose": task["purpose"],
                }
                for task in created_tasks
            ],
            "materialized": [
                {
                    key: value
                    for key, value in subtask.items()
                    if key != "child_node_id"
                }
                for subtask in materialized["subtasks"]
            ],
            "debug_payload": root["split_metadata"]["debug_payload"],
        }

    assert materialized_by_mode["workflow"] == materialized_by_mode["phase_breakdown"]


def test_split_service_executes_canonical_mode(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    service = make_service(
        storage,
        tree_service,
        FakeCodexClient([json.dumps(_canonical_payload_for_mode("workflow"))]),
    )

    snapshot = service.split_node(project_id, root_id, "workflow")  # type: ignore[arg-type]
    root = node_by_id(snapshot)[root_id]

    assert root["planning_mode"] == "workflow"
    assert root["split_metadata"]["output_family"] == "flat_subtasks_v1"


def test_split_service_accepts_valid_payload_outside_soft_count_range(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(
                    {
                        "subtasks": [
                            {
                                "id": "S1",
                                "title": "Single workflow proof",
                                "objective": "Validate the core workflow in one reversible step.",
                                "why_now": "This is the smallest grounded split the task currently supports.",
                            }
                        ]
                    }
                )
            ]
        ),
    )

    snapshot = service.split_node(project_id, root_id, "workflow")
    root = node_by_id(snapshot)[root_id]

    assert root["split_metadata"]["source"] == "ai"
    assert len(root["split_metadata"]["created_child_ids"]) == 1


def test_canonical_split_service_resplit_increments_revision(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    fake_client = FakeCodexClient(
        [
            json.dumps(_canonical_payload_for_mode("workflow")),
            json.dumps(
                {
                    "subtasks": [
                        {
                            "id": "S1",
                            "title": "workflow replacement 1",
                            "objective": "Replacement objective 1",
                            "why_now": "Replacement reason 1",
                        },
                        {
                            "id": "S2",
                            "title": "workflow replacement 2",
                            "objective": "Replacement objective 2",
                            "why_now": "Replacement reason 2",
                        },
                        {
                            "id": "S3",
                            "title": "workflow replacement 3",
                            "objective": "Replacement objective 3",
                            "why_now": "Replacement reason 3",
                        },
                    ]
                }
            ),
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    first = service.split_node(project_id, root_id, "workflow")  # type: ignore[arg-type]
    first_child_ids = node_by_id(first)[root_id]["split_metadata"]["created_child_ids"]
    second = service.split_node(project_id, root_id, "workflow", confirm_replace=True)  # type: ignore[arg-type]
    second_nodes = node_by_id(second)
    root = second_nodes[root_id]

    assert root["split_metadata"]["revision"] == 2
    assert root["split_metadata"]["replaced_child_ids"] == first_child_ids
    assert all(second_nodes[child_id]["node_kind"] == "superseded" for child_id in first_child_ids)


def test_split_service_creates_canonical_children_and_downgrades_parent(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    snapshot = load_snapshot(storage, project_id)
    node_by_id(snapshot)[root_id]["status"] = "ready"
    save_snapshot(storage, project_id, snapshot)
    fake_client = FakeCodexClient(
        [
            json.dumps(_canonical_payload_for_mode("workflow"))
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    result = service.split_node(project_id, root_id, "workflow")
    nodes = node_by_id(result)
    root = nodes[root_id]
    children = [nodes[child_id] for child_id in root["split_metadata"]["created_child_ids"]]

    assert root["status"] == "draft"
    assert root["split_metadata"]["source"] == "ai"
    assert [child["status"] for child in children] == ["ready", "locked", "locked"]
    first_child_task = storage.node_store.load_task(project_id, children[0]["node_id"])
    assert "title" not in children[0]
    assert first_child_task["title"] == "workflow step 1"
    assert "Objective 1 for workflow" in first_child_task["purpose"]
    assert "Why now: Reason 1 for workflow" in first_child_task["purpose"]
    assert result["tree_state"]["active_node_id"] == children[0]["node_id"]


def test_split_service_requires_confirmation_for_resplit(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )
    service.split_node(project_id, root_id, "workflow")

    with pytest.raises(SplitNotAllowed, match="Re-split requires confirmation"):
        service.split_node(project_id, root_id, "workflow")


def test_split_service_rejects_resplit_when_descendant_is_done(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )
    first = service.split_node(project_id, root_id, "workflow")
    first_nodes = node_by_id(first)
    phase_id = first_nodes[root_id]["split_metadata"]["created_child_ids"][0]
    persisted = load_snapshot(storage, project_id)
    persisted_nodes = node_by_id(persisted)
    persisted_nodes[phase_id]["status"] = "done"
    save_snapshot(storage, project_id, persisted)

    with pytest.raises(SplitNotAllowed, match="descendants are already in progress or done"):
        service.split_node(project_id, root_id, "workflow", confirm_replace=True)


def test_split_service_retries_invalid_payload_then_succeeds_without_fallback(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    fake_client = FakeCodexClient(
        [
            '{"subtasks": [{"id": "S1", "title": "Only one", "objective": "Only objective"}]}',
            json.dumps(_canonical_payload_for_mode("workflow")),
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    snapshot = service.split_node(project_id, root_id, "workflow")
    nodes = node_by_id(snapshot)
    root = nodes[root_id]

    assert len(fake_client.calls) == 2
    assert root["split_metadata"]["source"] == "ai"
    assert root["split_metadata"]["warnings"] == []
    assert len(root["split_metadata"]["created_child_ids"]) == 3
    assert fake_client.calls[0]["prompt"] == fake_client.calls[1]["prompt"].split("\n\n", 1)[1]


def test_split_service_fails_after_retry_exhaustion_without_mutating_snapshot(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                "not json",
                "still not json",
                "still not json",
            ]
        ),
    )

    service.split_node(project_id, root_id, "workflow")
    wait_for_split_completion(storage, project_id, root_id)

    assert len(service._service._codex_client.calls) == 3  # type: ignore[attr-defined]
    persisted_root = node_by_id(load_snapshot(storage, project_id))[root_id]
    assert persisted_root["planning_mode"] is None
    assert persisted_root["split_metadata"] is None
    assert persisted_root["child_ids"] == []
    turns = storage.thread_store.get_planning_turns(project_id, root_id)
    assert turns[-1]["role"] == "assistant"
    assert "Split failed because the model did not produce a valid structured split result." in turns[-1]["content"]


def test_split_service_treats_empty_subtasks_as_failure_sentinel_without_retry(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps({"subtasks": []}),
            ]
        ),
    )

    service.split_node(project_id, root_id, "workflow")
    wait_for_split_completion(storage, project_id, root_id)

    assert len(service._service._codex_client.calls) == 1  # type: ignore[attr-defined]
    persisted_root = node_by_id(load_snapshot(storage, project_id))[root_id]
    assert persisted_root["planning_mode"] is None
    assert persisted_root["split_metadata"] is None
    turns = storage.thread_store.get_planning_turns(project_id, root_id)
    assert turns[-1]["role"] == "assistant"
    assert "Could not produce a valid split from the parent task and current repo context." in turns[-1]["content"]


def test_canonical_apply_split_payload_keeps_parent_metadata_empty_when_snapshot_save_fails(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = make_service(storage, tree_service, FakeCodexClient([]))

    def fail_save_snapshot(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(storage.project_store, "save_snapshot", fail_save_snapshot)

    with pytest.raises(OSError, match="disk full"):
        service._apply_split_payload(
            project_id=project_id,
            node_id=root_id,
            mode="workflow",  # type: ignore[arg-type]
            confirm_replace=False,
            payload=_canonical_payload_for_mode("workflow"),
            source="ai",
            task_context={"parent_chain_truncated": False},
        )

    persisted_root = node_by_id(load_snapshot(storage, project_id))[root_id]
    assert persisted_root["child_ids"] == []
    assert persisted_root["planning_mode"] is None
    assert persisted_root["split_metadata"] is None


def test_split_service_resplit_supersedes_old_children_and_increments_revision(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    fake_client = FakeCodexClient(
        [
            json.dumps(_canonical_payload_for_mode("workflow")),
            json.dumps(
                {
                    "subtasks": [
                        {
                            "id": "S1",
                            "title": "workflow replacement 1",
                            "objective": "Replacement objective 1",
                            "why_now": "Replacement reason 1",
                        },
                        {
                            "id": "S2",
                            "title": "workflow replacement 2",
                            "objective": "Replacement objective 2",
                            "why_now": "Replacement reason 2",
                        },
                        {
                            "id": "S3",
                            "title": "workflow replacement 3",
                            "objective": "Replacement objective 3",
                            "why_now": "Replacement reason 3",
                        },
                    ]
                }
            ),
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    first = service.split_node(project_id, root_id, "workflow")
    first_child_ids = node_by_id(first)[root_id]["split_metadata"]["created_child_ids"]
    second = service.split_node(project_id, root_id, "workflow", confirm_replace=True)
    second_nodes = node_by_id(second)
    root = second_nodes[root_id]
    second_child_ids = root["split_metadata"]["created_child_ids"]

    assert root["split_metadata"]["revision"] == 2
    assert root["split_metadata"]["replaced_child_ids"] == first_child_ids
    assert second_child_ids != first_child_ids
    assert all(second_nodes[child_id]["node_kind"] == "superseded" for child_id in first_child_ids)
    assert all(second_nodes[child_id]["node_kind"] != "superseded" for child_id in second_child_ids)
    assert second["tree_state"]["active_node_id"] == second_child_ids[0]


def test_split_service_replace_lifecycle_preserves_canonical_metadata_and_planning_history(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    replacement_payload = {
        "subtasks": [
            {
                "id": "S1",
                "title": "workflow replacement 1",
                "objective": "Replacement objective 1",
                "why_now": "Replacement reason 1",
            },
            {
                "id": "S2",
                "title": "workflow replacement 2",
                "objective": "Replacement objective 2",
                "why_now": "Replacement reason 2",
            },
            {
                "id": "S3",
                "title": "workflow replacement 3",
                "objective": "Replacement objective 3",
                "why_now": "Replacement reason 3",
            },
        ]
    }
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow")),
                json.dumps(replacement_payload),
            ]
        ),
    )

    first = service.split_node(project_id, root_id, "workflow")
    first_root = node_by_id(first)[root_id]
    first_child_ids = first_root["split_metadata"]["created_child_ids"]

    with pytest.raises(SplitNotAllowed, match="Re-split requires confirmation"):
        service.split_node(project_id, root_id, "workflow")

    second = service.split_node(project_id, root_id, "workflow", confirm_replace=True)
    second_nodes = node_by_id(second)
    root = second_nodes[root_id]
    second_child_ids = root["split_metadata"]["created_child_ids"]
    metadata = root["split_metadata"]
    materialized = metadata["materialized"]

    assert root["planning_mode"] == "workflow"
    assert metadata["mode"] == "workflow"
    assert metadata["output_family"] == "flat_subtasks_v1"
    assert metadata["source"] == "ai"
    assert metadata["warnings"] == []
    assert metadata["revision"] == 2
    assert metadata["created_child_ids"] == second_child_ids
    assert metadata["replaced_child_ids"] == first_child_ids
    assert isinstance(metadata["created_at"], str)
    assert second_child_ids != first_child_ids
    assert materialized["family"] == "flat_subtasks_v1"
    assert [item["title"] for item in materialized["subtasks"]] == [
        "workflow replacement 1",
        "workflow replacement 2",
        "workflow replacement 3",
    ]
    assert [item["child_node_id"] for item in materialized["subtasks"]] == second_child_ids
    assert second["tree_state"]["active_node_id"] == second_child_ids[0]
    assert all(second_nodes[child_id]["node_kind"] == "superseded" for child_id in first_child_ids)
    assert all(second_nodes[child_id]["node_kind"] != "superseded" for child_id in second_child_ids)

    turns = storage.thread_store.get_planning_turns(project_id, root_id)
    tool_call_turns = [turn for turn in turns if turn["role"] == "tool_call"]

    assert [turn["role"] for turn in turns] == [
        "user",
        "tool_call",
        "assistant",
        "user",
        "tool_call",
        "assistant",
    ]
    assert len(tool_call_turns) == 2
    assert [turn["origin_node_id"] for turn in tool_call_turns] == [root_id, root_id]
    assert all(turn["is_inherited"] is False for turn in tool_call_turns)
    assert tool_call_turns[0]["arguments"]["payload"]["subtasks"][0]["title"] == "workflow step 1"
    assert tool_call_turns[1]["arguments"]["payload"]["subtasks"][0]["title"] == "workflow replacement 1"


def test_split_service_inherited_locked_ancestor_locks_new_children(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    snapshot = load_snapshot(storage, project_id)
    root = node_by_id(snapshot)[root_id]
    child_id = uuid4().hex
    root["status"] = "locked"
    root["child_ids"] = [child_id]
    snapshot["tree_state"]["node_index"][child_id] = {
        "node_id": child_id,
        "parent_id": root_id,
        "child_ids": [],
        "title": "Nested task",
        "description": "Break this down",
        "status": "draft",
        "phase": "planning",
        "node_kind": "original",
        "planning_mode": None,
        "depth": 1,
        "display_order": 0,
        "hierarchical_number": "1.1",
        "split_metadata": None,
        "chat_session_id": None,
        "planning_thread_id": None,
        "execution_thread_id": None,
        "planning_thread_forked_from_node": None,
        "planning_thread_bootstrapped_at": None,
        "created_at": "2026-03-08T00:00:00Z",
    }
    save_snapshot(storage, project_id, snapshot)
    storage.node_store.create_node_files(
        project_id,
        child_id,
        task={"title": "Nested task", "purpose": "Break this down", "responsibility": ""},
    )
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )

    result = service.split_node(project_id, child_id, "workflow")
    result_nodes = node_by_id(result)
    nested = result_nodes[child_id]
    created_children = [result_nodes[node_id] for node_id in nested["split_metadata"]["created_child_ids"]]

    assert [child["status"] for child in created_children] == ["locked", "locked", "locked"]


def test_split_service_allows_locked_node_and_keeps_new_children_locked(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    snapshot = load_snapshot(storage, project_id)
    root = node_by_id(snapshot)[root_id]
    root["status"] = "locked"
    save_snapshot(storage, project_id, snapshot)
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )

    result = service.split_node(project_id, root_id, "workflow")
    result_nodes = node_by_id(result)
    created_children = [
        result_nodes[node_id]
        for node_id in result_nodes[root_id]["split_metadata"]["created_child_ids"]
    ]

    assert result_nodes[root_id]["status"] == "locked"
    assert [child["status"] for child in created_children] == ["locked", "locked", "locked"]
    assert result["tree_state"]["active_node_id"] == created_children[0]["node_id"]


@pytest.mark.parametrize(
    ("status", "is_superseded", "expected_message"),
    [
        ("done", False, "Cannot split a done node."),
        ("draft", True, "Cannot split a superseded node."),
    ],
)
def test_split_service_rejects_ineligible_nodes(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    status: str,
    is_superseded: bool,
    expected_message: str,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    snapshot = load_snapshot(storage, project_id)
    root = node_by_id(snapshot)[root_id]
    root["status"] = status
    root["node_kind"] = "superseded" if is_superseded else "root"
    save_snapshot(storage, project_id, snapshot)
    service = make_service(storage, tree_service, FakeCodexClient([]))

    with pytest.raises(SplitNotAllowed, match=expected_message):
        service.split_node(project_id, root_id, "workflow")


def test_split_rejects_when_pending_packets_exist(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    seed_ask_packets(storage, project_id, root_id, "pending")
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )

    with pytest.raises(SplitNotAllowed, match="Resolve ask-thread delta context packets"):
        service.split_node(project_id, root_id, "workflow")


def test_split_rejects_when_approved_packets_exist(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    seed_ask_packets(storage, project_id, root_id, "approved")
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )

    with pytest.raises(SplitNotAllowed, match="Resolve ask-thread delta context packets"):
        service.split_node(project_id, root_id, "workflow")


@pytest.mark.parametrize("status", ["rejected", "merged", "blocked"])
def test_split_allows_when_only_resolved_packets_exist(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    status: str,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    seed_ask_packets(storage, project_id, root_id, status)
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )

    result = service.split_node(project_id, root_id, "workflow")

    assert node_by_id(result)[root_id]["split_metadata"]["source"] == "ai"


def test_split_allows_when_no_packets_exist(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    service = make_service(
        storage,
        tree_service,
        FakeCodexClient(
            [
                json.dumps(_canonical_payload_for_mode("workflow"))
            ]
        ),
    )

    result = service.split_node(project_id, root_id, "workflow")

    assert node_by_id(result)[root_id]["split_metadata"]["source"] == "ai"
