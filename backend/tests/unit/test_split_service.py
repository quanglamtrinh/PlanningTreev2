from __future__ import annotations

import json
import time
from uuid import uuid4

import pytest

from backend.ai.codex_client import CodexTransportError
from backend.errors.app_errors import SplitNotAllowed
from backend.services import split_service as split_service_module
from backend.services.canonical_split_fallback import build_canonical_split_fallback
from backend.services.node_service import NodeService
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
            mode="slice",
            confirm_replace=False,
            payload={
                "subtasks": [
                    {
                        "order": 1,
                        "prompt": "Setup foundation",
                        "risk_reason": "",
                        "what_unblocks": "",
                    },
                    {
                        "order": 2,
                        "prompt": "Build feature",
                        "risk_reason": "",
                        "what_unblocks": "",
                    },
                ]
            },
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
    assert bundle.is_canonical is True
    assert bundle.validate_payload(_canonical_payload_for_mode("workflow")) is True
    assert bundle.validate_payload({"subtasks": [{"order": 1, "prompt": "legacy"}]}) is False
    assert "workflow-first sequential split" in bundle.build_user_message(
        {"current_node_prompt": "Ship workflow", "root_prompt": "Alpha"}
    )


def test_split_runtime_bundle_for_mode_selects_legacy_helpers() -> None:
    bundle = split_runtime_bundle_for_mode("slice")

    assert bundle.output_family == "legacy_flat_slice"
    assert bundle.is_canonical is False
    assert (
        bundle.validate_payload(
            {
                "subtasks": [
                    {"order": 1, "prompt": "First", "risk_reason": "", "what_unblocks": ""},
                    {"order": 2, "prompt": "Second", "risk_reason": "", "what_unblocks": ""},
                ]
            }
        )
        is True
    )
    assert "vertical slice mode" in bundle.build_user_message({"current_node_prompt": "Split this node"})


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


def test_split_service_executes_canonical_mode_without_legacy_runtime_helpers(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    def fail_legacy(*args, **kwargs):
        raise AssertionError("canonical split should not call legacy runtime helpers")

    monkeypatch.setattr(split_service_module, "build_legacy_split_user_message", fail_legacy)
    monkeypatch.setattr(split_service_module, "validate_legacy_split_payload", fail_legacy)
    monkeypatch.setattr(split_service_module, "legacy_split_payload_issues", fail_legacy)
    monkeypatch.setattr(split_service_module, "build_legacy_hidden_retry_feedback", fail_legacy)

    service = make_service(
        storage,
        tree_service,
        FakeCodexClient([json.dumps(_canonical_payload_for_mode("workflow"))]),
    )

    snapshot = service.split_node(project_id, root_id, "workflow")  # type: ignore[arg-type]
    root = node_by_id(snapshot)[root_id]

    assert root["planning_mode"] == "workflow"
    assert root["split_metadata"]["output_family"] == "flat_subtasks_v1"


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


def test_split_service_creates_walking_skeleton_tree(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    fake_client = FakeCodexClient(
        [
            """
            {
              "epics": [
                {
                  "title": "Core Track",
                  "prompt": "Build the core system",
                  "phases": [
                    {"prompt": "Scaffold backend", "definition_of_done": "API skeleton ready"},
                    {"prompt": "Implement core logic", "definition_of_done": "Core path works"}
                  ]
                },
                {
                  "title": "Polish Track",
                  "prompt": "Polish the product",
                  "phases": [
                    {"prompt": "Refine UX", "definition_of_done": "UX reviewed"},
                    {"prompt": "Write docs", "definition_of_done": "Docs published"}
                  ]
                }
              ]
            }
            """
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    snapshot = service.split_node(project_id, root_id, "walking_skeleton")
    nodes = node_by_id(snapshot)
    root = nodes[root_id]
    epic_ids = root["child_ids"]
    epics = [nodes[epic_id] for epic_id in epic_ids]
    first_epic_phases = [nodes[child_id] for child_id in epics[0]["child_ids"]]
    second_epic_phases = [nodes[child_id] for child_id in epics[1]["child_ids"]]
    created_ids = root["split_metadata"]["created_child_ids"]

    assert root["planning_mode"] == "walking_skeleton"
    assert root["split_metadata"]["source"] == "ai"
    assert root["split_metadata"]["revision"] == 1
    assert [epic["status"] for epic in epics] == ["draft", "locked"]
    assert [phase["status"] for phase in first_epic_phases] == ["ready", "locked"]
    assert [phase["status"] for phase in second_epic_phases] == ["locked", "locked"]
    assert created_ids == [
        epics[0]["node_id"],
        first_epic_phases[0]["node_id"],
        first_epic_phases[1]["node_id"],
        epics[1]["node_id"],
        second_epic_phases[0]["node_id"],
        second_epic_phases[1]["node_id"],
    ]
    assert "title" not in first_epic_phases[0]
    assert storage.node_store.load_task(project_id, first_epic_phases[0]["node_id"])["title"].startswith(
        "A: Scaffold backend"
    )
    assert snapshot["tree_state"]["active_node_id"] == first_epic_phases[0]["node_id"]


def test_split_service_unlocks_next_epic_and_first_phase_after_epic_completion(
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
                """
                {
                  "epics": [
                    {
                      "title": "Core Track",
                      "prompt": "Build the core system",
                      "phases": [
                        {"prompt": "Scaffold backend", "definition_of_done": "API skeleton ready"},
                        {"prompt": "Implement core logic", "definition_of_done": "Core path works"}
                      ]
                    },
                    {
                      "title": "Polish Track",
                      "prompt": "Polish the product",
                      "phases": [
                        {"prompt": "Refine UX", "definition_of_done": "UX reviewed"},
                        {"prompt": "Write docs", "definition_of_done": "Docs published"}
                      ]
                    }
                  ]
                }
                """
            ]
        ),
    )
    node_service = NodeService(storage, tree_service)

    snapshot = service.split_node(project_id, root_id, "walking_skeleton")
    nodes = node_by_id(snapshot)
    root = nodes[root_id]
    first_epic = nodes[root["child_ids"][0]]
    second_epic = nodes[root["child_ids"][1]]
    first_phase_id, second_phase_id = first_epic["child_ids"]
    second_epic_first_phase_id, second_epic_second_phase_id = second_epic["child_ids"]
    set_node_phase(storage, project_id, first_phase_id, "ready_for_execution")
    set_node_phase(storage, project_id, second_phase_id, "ready_for_execution")

    node_service.complete_node(project_id, first_phase_id)
    after_first_phase = node_by_id(load_snapshot(storage, project_id))
    assert after_first_phase[second_phase_id]["status"] == "ready"
    assert after_first_phase[second_phase_id]["phase"] == "spec_review"
    assert after_first_phase[second_epic["node_id"]]["status"] == "locked"
    assert after_first_phase[second_epic_first_phase_id]["status"] == "locked"

    set_node_phase(storage, project_id, second_phase_id, "ready_for_execution")
    node_service.complete_node(project_id, second_phase_id)
    after_epic_complete = node_by_id(load_snapshot(storage, project_id))
    assert after_epic_complete[second_epic["node_id"]]["status"] == "ready"
    assert after_epic_complete[second_epic_first_phase_id]["status"] == "ready"
    assert after_epic_complete[second_epic_second_phase_id]["status"] == "locked"


def test_split_service_creates_slice_children_and_downgrades_parent(
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
            """
            {
              "subtasks": [
                {"order": 1, "prompt": "Setup repo", "risk_reason": "env", "what_unblocks": "coding"},
                {"order": 2, "prompt": "Ship feature", "risk_reason": "", "what_unblocks": ""}
              ]
            }
            """
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    result = service.split_node(project_id, root_id, "slice")
    nodes = node_by_id(result)
    root = nodes[root_id]
    children = [nodes[child_id] for child_id in root["split_metadata"]["created_child_ids"]]

    assert root["status"] == "draft"
    assert root["split_metadata"]["source"] == "ai"
    assert [child["status"] for child in children] == ["ready", "locked"]
    first_child_task = storage.node_store.load_task(project_id, children[0]["node_id"])
    assert "title" not in children[0]
    assert first_child_task["title"] == "Setup repo"
    assert "Risk: env" in first_child_task["purpose"]
    assert "Unblocks: coding" in first_child_task["purpose"]
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
                """
                {"subtasks": [
                  {"order": 1, "prompt": "One", "risk_reason": "", "what_unblocks": ""},
                  {"order": 2, "prompt": "Two", "risk_reason": "", "what_unblocks": ""}
                ]}
                """
            ]
        ),
    )
    service.split_node(project_id, root_id, "slice")

    with pytest.raises(SplitNotAllowed, match="Re-split requires confirmation"):
        service.split_node(project_id, root_id, "slice")


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
                """
                {"epics": [
                  {
                    "title": "Epic",
                    "prompt": "Build it",
                    "phases": [
                      {"prompt": "Phase one", "definition_of_done": "one"},
                      {"prompt": "Phase two", "definition_of_done": "two"}
                    ]
                  }
                ]}
                """
            ]
        ),
    )
    first = service.split_node(project_id, root_id, "walking_skeleton")
    first_nodes = node_by_id(first)
    phase_id = next(
        node_id
        for node_id, node in first_nodes.items()
        if node.get("parent_id") in first_nodes[root_id]["split_metadata"]["created_child_ids"]
    )
    persisted = load_snapshot(storage, project_id)
    persisted_nodes = node_by_id(persisted)
    persisted_nodes[phase_id]["status"] = "done"
    save_snapshot(storage, project_id, persisted)

    with pytest.raises(SplitNotAllowed, match="descendants are already in progress or done"):
        service.split_node(project_id, root_id, "walking_skeleton", confirm_replace=True)


def test_split_service_falls_back_after_retries_and_restarts_transport(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))
    fake_client = FakeCodexClient(
        [
            '{"subtasks": [{"order": 1, "prompt": "Only one", "risk_reason": "", "what_unblocks": ""}]}',
            "not json",
            "still not json",
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    snapshot = service.split_node(project_id, root_id, "slice")
    nodes = node_by_id(snapshot)
    root = nodes[root_id]

    assert len(fake_client.calls) == 3
    assert root["split_metadata"]["source"] == "fallback"
    assert "fallback_used" in root["split_metadata"]["warnings"]
    assert len(root["split_metadata"]["created_child_ids"]) == 3


def test_canonical_split_service_falls_back_after_retries_without_legacy_helpers(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    def fail_legacy(*args, **kwargs):
        raise AssertionError("canonical split should not fall into legacy retry helpers")

    monkeypatch.setattr(split_service_module, "build_legacy_split_user_message", fail_legacy)
    monkeypatch.setattr(split_service_module, "validate_legacy_split_payload", fail_legacy)
    monkeypatch.setattr(split_service_module, "legacy_split_payload_issues", fail_legacy)
    monkeypatch.setattr(split_service_module, "build_legacy_hidden_retry_feedback", fail_legacy)

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

    snapshot = service.split_node(project_id, root_id, "workflow")  # type: ignore[arg-type]
    nodes = node_by_id(snapshot)
    root = nodes[root_id]
    children = [nodes[child_id] for child_id in root["split_metadata"]["created_child_ids"]]
    first_child_task = storage.node_store.load_task(project_id, children[0]["node_id"])

    assert len(service._service._codex_client.calls) == 3  # type: ignore[attr-defined]
    assert root["planning_mode"] == "workflow"
    assert root["split_metadata"]["source"] == "fallback"
    assert root["split_metadata"]["output_family"] == "flat_subtasks_v1"
    assert root["split_metadata"]["warnings"] == ["fallback_used"]
    assert [child["status"] for child in children] == ["ready", "locked", "locked"]
    assert first_child_task["title"] == "Define the working flow"
    assert "Why now:" in first_child_task["purpose"]


def test_canonical_fallback_payload_is_revalidated_before_apply(
    project_service: ProjectService,
    storage: Storage,
    tree_service,
    workspace_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, root_id = create_project(project_service, str(workspace_root))

    monkeypatch.setattr(
        split_service_module,
        "build_canonical_split_fallback",
        lambda mode, task_context: {  # type: ignore[return-value]
            "subtasks": [
                {
                    "id": "S1",
                    "title": "Invalid canonical fallback",
                    "objective": "Missing why_now should fail validation",
                }
            ]
        },
    )

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

    with pytest.raises(RuntimeError, match="Deterministic split fallback produced an invalid payload:"):
        service._execute_split_turn(
            project_id=project_id,
            node_id=root_id,
            mode="workflow",  # type: ignore[arg-type]
            confirm_replace=False,
            turn_id="turn_invalid_canonical_fallback",
        )

    persisted_root = node_by_id(load_snapshot(storage, project_id))[root_id]
    assert persisted_root["planning_mode"] is None
    assert persisted_root["split_metadata"] is None


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
            """
            {"subtasks": [
              {"order": 1, "prompt": "First pass one", "risk_reason": "", "what_unblocks": ""},
              {"order": 2, "prompt": "First pass two", "risk_reason": "", "what_unblocks": ""}
            ]}
            """,
            """
            {"subtasks": [
              {"order": 1, "prompt": "Second pass one", "risk_reason": "", "what_unblocks": ""},
              {"order": 2, "prompt": "Second pass two", "risk_reason": "", "what_unblocks": ""}
            ]}
            """,
        ]
    )
    service = make_service(storage, tree_service, fake_client)

    first = service.split_node(project_id, root_id, "slice")
    first_child_ids = node_by_id(first)[root_id]["split_metadata"]["created_child_ids"]
    second = service.split_node(project_id, root_id, "slice", confirm_replace=True)
    second_nodes = node_by_id(second)
    root = second_nodes[root_id]
    second_child_ids = root["split_metadata"]["created_child_ids"]

    assert root["split_metadata"]["revision"] == 2
    assert root["split_metadata"]["replaced_child_ids"] == first_child_ids
    assert second_child_ids != first_child_ids
    assert all(second_nodes[child_id]["node_kind"] == "superseded" for child_id in first_child_ids)
    assert all(second_nodes[child_id]["node_kind"] != "superseded" for child_id in second_child_ids)
    assert second["tree_state"]["active_node_id"] == second_child_ids[0]


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
                """
                {"subtasks": [
                  {"order": 1, "prompt": "Locked child one", "risk_reason": "", "what_unblocks": ""},
                  {"order": 2, "prompt": "Locked child two", "risk_reason": "", "what_unblocks": ""}
                ]}
                """
            ]
        ),
    )

    result = service.split_node(project_id, child_id, "slice")
    result_nodes = node_by_id(result)
    nested = result_nodes[child_id]
    created_children = [result_nodes[node_id] for node_id in nested["split_metadata"]["created_child_ids"]]

    assert [child["status"] for child in created_children] == ["locked", "locked"]


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
                """
                {"subtasks": [
                  {"order": 1, "prompt": "Locked split one", "risk_reason": "", "what_unblocks": ""},
                  {"order": 2, "prompt": "Locked split two", "risk_reason": "", "what_unblocks": ""}
                ]}
                """
            ]
        ),
    )

    result = service.split_node(project_id, root_id, "slice")
    result_nodes = node_by_id(result)
    created_children = [
        result_nodes[node_id]
        for node_id in result_nodes[root_id]["split_metadata"]["created_child_ids"]
    ]

    assert result_nodes[root_id]["status"] == "locked"
    assert [child["status"] for child in created_children] == ["locked", "locked"]
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
        service.split_node(project_id, root_id, "slice")


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
                (
                    '{"subtasks": ['
                    '{"order": 1, "prompt": "One", "risk_reason": "", "what_unblocks": ""}, '
                    '{"order": 2, "prompt": "Two", "risk_reason": "", "what_unblocks": ""}'
                    "]}"
                )
            ]
        ),
    )

    with pytest.raises(SplitNotAllowed, match="Resolve ask-thread delta context packets"):
        service.split_node(project_id, root_id, "slice")


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
                (
                    '{"subtasks": ['
                    '{"order": 1, "prompt": "One", "risk_reason": "", "what_unblocks": ""}, '
                    '{"order": 2, "prompt": "Two", "risk_reason": "", "what_unblocks": ""}'
                    "]}"
                )
            ]
        ),
    )

    with pytest.raises(SplitNotAllowed, match="Resolve ask-thread delta context packets"):
        service.split_node(project_id, root_id, "slice")


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
                (
                    '{"subtasks": ['
                    '{"order": 1, "prompt": "One", "risk_reason": "", "what_unblocks": ""}, '
                    '{"order": 2, "prompt": "Two", "risk_reason": "", "what_unblocks": ""}'
                    "]}"
                )
            ]
        ),
    )

    result = service.split_node(project_id, root_id, "slice")

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
                (
                    '{"subtasks": ['
                    '{"order": 1, "prompt": "One", "risk_reason": "", "what_unblocks": ""}, '
                    '{"order": 2, "prompt": "Two", "risk_reason": "", "what_unblocks": ""}'
                    "]}"
                )
            ]
        ),
    )

    result = service.split_node(project_id, root_id, "slice")

    assert node_by_id(result)[root_id]["split_metadata"]["source"] == "ai"
