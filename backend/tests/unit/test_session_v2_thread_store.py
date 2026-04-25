from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.protocol import SessionProtocolClientV2
from backend.session_core_v2.storage import RuntimeStoreV2
from backend.session_core_v2.thread_store import (
    ThreadMetadataStore,
    ThreadRolloutRecorder,
    build_turns_from_rollout_items,
    paginate_turns,
    read_native_thread,
)

# Phase 0 mapping fixture: PlanningTree runtime notifications are stored as
# Codex-like event_msg rollout items, alongside session_meta/turn_context when
# available. Phase 4+ will read these items directly for thread/read.
SAMPLE_ROLLOUT_ITEMS: list[dict[str, Any]] = [
    {"type": "session_meta", "threadId": "thread-1"},
    {"type": "event_msg", "event": {"method": "turn/started", "threadId": "thread-1", "turnId": "turn-1", "params": {"turnId": "turn-1"}}},
    {"type": "event_msg", "event": {"method": "user/message", "threadId": "thread-1", "turnId": "turn-1", "params": {"text": "Build it"}}},
    {"type": "event_msg", "event": {"method": "assistant/message", "threadId": "thread-1", "turnId": "turn-1", "params": {"text": "Done"}}},
    {"type": "event_msg", "event": {"method": "task/completed", "threadId": "thread-1", "turnId": "turn-1", "params": {"id": "task-1"}}},
    {"type": "event_msg", "event": {"method": "turn/completed", "threadId": "thread-1", "turnId": "turn-1", "params": {"turn": {"id": "turn-1", "status": "completed"}}}},
]


class _FakeTransport:
    def __init__(self) -> None:
        self.notification_handler = None
        self.server_request_handler = None

    def set_notification_handler(self, handler) -> None:  # noqa: ANN001
        self.notification_handler = handler

    def set_server_request_handler(self, handler) -> None:  # noqa: ANN001
        self.server_request_handler = handler

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: int | None = None) -> dict[str, Any]:
        del timeout_sec
        if method == "thread/start":
            return {"thread": {"id": "thread-created-1", "name": "Created thread"}}
        return {}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        del method, params


class _AssertingRuntimeStore(RuntimeStoreV2):
    def __init__(self, *, recorder: ThreadRolloutRecorder) -> None:
        super().__init__()
        self._recorder = recorder

    def append_notification(
        self,
        *,
        method: str,
        params: dict[str, Any],
        thread_id_override: str | None = None,
    ) -> dict[str, Any]:
        thread_id = str(thread_id_override or params.get("threadId") or "")
        items = self._recorder.load_items(thread_id)
        assert any(
            item.get("type") == "event_msg"
            and isinstance(item.get("event"), dict)
            and item["event"].get("method") == method
            for item in items
        )
        return super().append_notification(method=method, params=params, thread_id_override=thread_id_override)


def _stores(tmp_path: Path) -> tuple[ThreadMetadataStore, ThreadRolloutRecorder]:
    metadata = ThreadMetadataStore(
        db_path=tmp_path / "thread_metadata.sqlite3",
        rollout_root=tmp_path / "rollouts",
    )
    return metadata, ThreadRolloutRecorder(metadata_store=metadata)


def test_thread_metadata_store_create_get_update_reopen(tmp_path: Path) -> None:
    metadata, _ = _stores(tmp_path)
    created = metadata.create_or_update(thread_id="thread-1", project_id="project-1", title="First", status="running", now_ms=10)
    assert created.rollout_path.endswith("thread-1.jsonl")
    metadata.update_status("thread-1", "closed", now_ms=20)
    metadata.update_title("thread-1", "Renamed", now_ms=30)
    metadata.close()

    reopened = ThreadMetadataStore(db_path=tmp_path / "thread_metadata.sqlite3", rollout_root=tmp_path / "rollouts")
    loaded = reopened.get("thread-1")
    assert loaded is not None
    assert loaded.project_id == "project-1"
    assert loaded.title == "Renamed"
    assert loaded.status == "closed"
    assert loaded.created_at_ms == 10
    assert loaded.updated_at_ms == 30


def test_rollout_recorder_append_load_preserves_order(tmp_path: Path) -> None:
    _, recorder = _stores(tmp_path)
    recorder.ensure_thread(thread_id="thread-1")
    recorder.append_items("thread-1", SAMPLE_ROLLOUT_ITEMS)

    items = recorder.load_items("thread-1")
    assert [item.get("type") for item in items] == [item.get("type") for item in SAMPLE_ROLLOUT_ITEMS]
    assert items[1]["event"]["method"] == "turn/started"
    assert recorder.rollout_path_for("thread-1").exists()


def test_rollout_recorder_dedupes_event_id_per_thread(tmp_path: Path) -> None:
    _, recorder = _stores(tmp_path)
    recorder.ensure_thread(thread_id="thread-1")
    item = {
        "type": "event_msg",
        "event": {
            "eventId": "event-1",
            "method": "turn/started",
            "threadId": "thread-1",
            "params": {"turnId": "turn-1"},
        },
    }
    recorder.append_items("thread-1", [item, item])
    recorder.append_items("thread-1", [item])

    assert len(recorder.load_items("thread-1")) == 1


def test_persist_pipeline_appends_before_runtime_broadcast(tmp_path: Path) -> None:
    _, recorder = _stores(tmp_path)
    runtime = _AssertingRuntimeStore(recorder=recorder)
    manager = SessionManagerV2(
        protocol_client=SessionProtocolClientV2(_FakeTransport()),  # type: ignore[arg-type]
        runtime_store=runtime,
        connection_state_machine=ConnectionStateMachine(),
        thread_rollout_recorder=recorder,
    )

    manager._on_notification("turn/started", {"threadId": "thread-1", "turnId": "turn-1"})  # noqa: SLF001

    assert runtime.get_turn(thread_id="thread-1", turn_id="turn-1") is not None


def test_finish_task_writes_task_completed_and_turn_completed(tmp_path: Path) -> None:
    metadata, recorder = _stores(tmp_path)
    manager = SessionManagerV2(
        protocol_client=SessionProtocolClientV2(_FakeTransport()),  # type: ignore[arg-type]
        runtime_store=RuntimeStoreV2(),
        connection_state_machine=ConnectionStateMachine(),
        thread_rollout_recorder=recorder,
    )

    manager._append_notification_persisted(method="task/completed", params={"threadId": "thread-1", "turnId": "turn-1", "id": "task-1"})  # noqa: SLF001
    manager._append_notification_persisted(method="turn/completed", params={"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}})  # noqa: SLF001

    methods = [item["event"]["method"] for item in recorder.load_items("thread-1")]
    assert methods == ["task/completed", "turn/completed"]
    loaded = metadata.get("thread-1")
    assert loaded is not None
    assert loaded.status == "closed"


def test_native_terminal_settlement_is_idempotent_and_rehydrates_after_disconnect(tmp_path: Path) -> None:
    metadata, recorder = _stores(tmp_path)
    manager = SessionManagerV2(
        protocol_client=SessionProtocolClientV2(_FakeTransport()),  # type: ignore[arg-type]
        runtime_store=RuntimeStoreV2(),
        connection_state_machine=ConnectionStateMachine(),
        thread_rollout_recorder=recorder,
    )

    first = manager.settle_native_terminal_event(
        thread_id="thread-1",
        turn_id="turn-1",
        task={"id": "task-1", "type": "task"},
        status="completed",
    )
    second = manager.settle_native_terminal_event(
        thread_id="thread-1",
        turn_id="turn-1",
        task={"id": "task-1", "type": "task"},
        status="completed",
    )

    assert first["appended"] == 2
    assert second["terminalAlreadyPersisted"] is True
    assert second["appended"] == 0
    methods = [item["event"]["method"] for item in recorder.load_items("thread-1")]
    assert methods == ["task/completed", "turn/completed"]
    read = read_native_thread(
        metadata_store=metadata,
        rollout_recorder=recorder,
        thread_id="thread-1",
        include_history=True,
    )
    assert read["thread"]["turns"][0]["status"] == "completed"
    assert read["thread"]["turns"][0]["items"][0]["id"] == "task-1"


def test_read_native_thread_rebuilds_turns_from_rollout(tmp_path: Path) -> None:
    metadata, recorder = _stores(tmp_path)
    recorder.ensure_thread(thread_id="thread-1", title="Native")
    recorder.append_items("thread-1", SAMPLE_ROLLOUT_ITEMS)

    response = read_native_thread(
        metadata_store=metadata,
        rollout_recorder=recorder,
        thread_id="thread-1",
        include_history=True,
    )

    assert response["thread"]["id"] == "thread-1"
    assert response["thread"]["name"] == "Native"
    assert response["thread"]["turns"][0]["id"] == "turn-1"


def test_build_turns_from_rollout_items_normal_turn() -> None:
    turns = build_turns_from_rollout_items(SAMPLE_ROLLOUT_ITEMS)

    assert len(turns) == 1
    assert turns[0]["id"] == "turn-1"
    assert turns[0]["status"] == "completed"
    assert [item["type"] for item in turns[0]["items"]] == ["userMessage", "agentMessage", "task_completed"]


def test_build_turns_from_rollout_items_terminal_before_started() -> None:
    turns = build_turns_from_rollout_items(
        [
            {
                "type": "event_msg",
                "event": {
                    "method": "turn/completed",
                    "threadId": "thread-1",
                    "params": {"turn": {"id": "turn-terminal", "status": "completed", "items": [{"id": "done", "type": "agentMessage", "text": "done"}]}},
                },
            }
        ]
    )

    assert turns == [
        {
            "id": "turn-terminal",
            "threadId": "thread-1",
            "status": "completed",
            "lastCodexStatus": "completed",
            "startedAtMs": 0,
            "completedAtMs": 0,
            "items": [{"id": "done", "type": "agentMessage", "text": "done"}],
            "error": None,
            "updatedAtMs": 0,
        }
    ]


def test_build_turns_from_rollout_items_unknown_event_is_ignored() -> None:
    turns = build_turns_from_rollout_items(
        [
            {"type": "event_msg", "event": {"method": "unknown", "params": {"anything": True}}},
            *SAMPLE_ROLLOUT_ITEMS,
        ]
    )

    assert len(turns) == 1
    assert turns[0]["id"] == "turn-1"


def test_paginate_turns_desc_and_cursor() -> None:
    turns = [
        {"id": "turn-1", "items": []},
        {"id": "turn-2", "items": []},
        {"id": "turn-3", "items": []},
    ]

    first = paginate_turns(turns, limit=2)
    assert [turn["id"] for turn in first["data"]] == ["turn-3", "turn-2"]
    assert first["nextCursor"] == "turn-2"

    second = paginate_turns(turns, cursor=first["nextCursor"], limit=2)
    assert [turn["id"] for turn in second["data"]] == ["turn-1"]
    assert second["nextCursor"] is None
