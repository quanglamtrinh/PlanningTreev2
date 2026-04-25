from __future__ import annotations

from backend.session_core_v2.thread_store.turn_builder import ThreadHistoryBuilder


def test_turn_builder_replays_terminal_interaction_into_command_output() -> None:
    builder = ThreadHistoryBuilder()
    builder.handle_event(
        {
            "method": "item/started",
            "threadId": "thread-1",
            "turnId": "turn-1",
            "params": {
                "item": {
                    "id": "cmd-1",
                    "type": "commandExecution",
                    "status": "inProgress",
                }
            },
        }
    )
    builder.handle_event(
        {
            "method": "item/commandExecution/outputDelta",
            "threadId": "thread-1",
            "turnId": "turn-1",
            "params": {"itemId": "cmd-1", "delta": "npm test\n"},
        }
    )
    builder.handle_event(
        {
            "method": "item/commandExecution/terminalInteraction",
            "threadId": "thread-1",
            "turnId": "turn-1",
            "params": {"itemId": "cmd-1", "stdin": "y\r\n"},
        }
    )

    turns = builder.finish()

    assert turns[0]["items"][0]["output"] == "npm test\n[stdin]\ny\n"
    assert turns[0]["items"][0]["aggregatedOutput"] == "npm test\n[stdin]\ny\n"
