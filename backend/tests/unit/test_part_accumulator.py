from __future__ import annotations

from backend.ai.part_accumulator import PartAccumulator


def test_on_delta_creates_assistant_text_part():
    acc = PartAccumulator()
    acc.on_delta("Hello ")
    acc.on_delta("world")
    assert len(acc.parts) == 1
    assert acc.parts[0]["type"] == "assistant_text"
    assert acc.parts[0]["content"] == "Hello world"
    assert acc.parts[0]["is_streaming"] is True


def test_on_tool_call_closes_text_and_adds_tool():
    acc = PartAccumulator()
    acc.on_delta("Thinking...")
    acc.on_tool_call("read_file", {"path": "/foo.py"})
    acc.on_delta("Done.")
    assert len(acc.parts) == 3
    assert acc.parts[0]["type"] == "assistant_text"
    assert acc.parts[0]["is_streaming"] is False
    assert acc.parts[1]["type"] == "tool_call"
    assert acc.parts[1]["tool_name"] == "read_file"
    assert acc.parts[1]["arguments"] == {"path": "/foo.py"}
    assert acc.parts[1]["status"] == "running"
    assert acc.parts[2]["type"] == "assistant_text"
    assert acc.parts[2]["content"] == "Done."


def test_on_plan_delta_creates_and_updates_plan_item():
    acc = PartAccumulator()
    acc.on_plan_delta("Inspect ", {"id": "plan-1"})
    acc.on_plan_delta("workspace", {"id": "plan-1"})

    assert len(acc.parts) == 1
    assert acc.parts[0]["type"] == "plan_item"
    assert acc.parts[0]["item_id"] == "plan-1"
    assert acc.parts[0]["content"] == "Inspect workspace"
    assert acc.parts[0]["is_streaming"] is True


def test_on_thread_status_adds_status_block():
    acc = PartAccumulator()
    acc.on_thread_status({"status": {"type": "running"}})
    assert len(acc.parts) == 1
    assert acc.parts[0]["type"] == "status_block"
    assert acc.parts[0]["status_type"] == "running"
    assert acc.parts[0]["label"] == "Working..."


def test_on_thread_status_updates_existing_trailing_status():
    acc = PartAccumulator()
    acc.on_thread_status({"status": {"type": "running"}})
    acc.on_thread_status({"status": {"type": "idle"}})
    assert len(acc.parts) == 1
    assert acc.parts[0]["status_type"] == "idle"
    assert acc.parts[0]["label"] == "Idle"


def test_finalize_closes_text_and_completes_tools():
    acc = PartAccumulator()
    acc.on_delta("text")
    acc.on_plan_delta("Inspect files", {"id": "plan-1"})
    acc.on_tool_call("shell", {"cmd": "ls"})
    acc.on_thread_status({"status": {"type": "running"}})
    acc.finalize()

    # Plan part closed
    assert acc.parts[1]["is_streaming"] is False
    # Tool call completed
    assert acc.parts[2]["status"] == "completed"
    # Trailing status block removed
    assert len(acc.parts) == 3


def test_finalize_removes_only_trailing_status_blocks():
    acc = PartAccumulator()
    acc.on_thread_status({"status": {"type": "running"}})
    acc.on_delta("text after status")
    acc.on_thread_status({"status": {"type": "idle"}})
    acc.finalize()

    # First status block stays (not trailing), trailing one removed
    assert len(acc.parts) == 2
    assert acc.parts[0]["type"] == "status_block"
    assert acc.parts[1]["type"] == "assistant_text"


def test_finalize_can_keep_status_blocks():
    acc = PartAccumulator()
    acc.on_plan_delta("Inspect files", {"id": "plan-1"})
    acc.on_thread_status({"status": {"type": "running"}})
    acc.finalize(keep_status_blocks=True)

    assert len(acc.parts) == 2
    assert acc.parts[0]["type"] == "plan_item"
    assert acc.parts[0]["is_streaming"] is False
    assert acc.parts[1]["type"] == "status_block"


def test_content_projection():
    acc = PartAccumulator()
    acc.on_delta("Hello ")
    acc.on_tool_call("read_file", {})
    acc.on_delta("world")
    assert acc.content_projection() == "Hello world"


def test_snapshot_parts_returns_shallow_copy():
    acc = PartAccumulator()
    acc.on_delta("text")
    snap = acc.snapshot_parts()
    snap[0]["content"] = "modified"
    assert acc.parts[0]["content"] == "text"


def test_empty_accumulator():
    acc = PartAccumulator()
    acc.finalize()
    assert acc.parts == []
    assert acc.content_projection() == ""
