from __future__ import annotations

from backend.conversation.domain.types import default_thread_snapshot
from backend.conversation.services.thread_history_importer import hydrate_snapshot_from_thread_read


def test_hydrate_snapshot_from_thread_read_imports_current_thread_visible_history_only() -> None:
    snapshot = default_thread_snapshot("project-1", "node-1", "execution")
    snapshot["threadId"] = "019d38ba-9fe3-7f52-a773-41a2df4b55af"
    snapshot["activeTurnId"] = "exec_local_turn_1"
    snapshot["processingState"] = "running"
    snapshot["updatedAt"] = "2026-03-29T08:35:43Z"

    payload = {
        "thread": {
            "id": "019d38ba-9fe3-7f52-a773-41a2df4b55af",
            "createdAt": 1774773247,
            "turns": [
                {
                    "id": "019d38b6-8f4b-76a0-a4e1-c330e61c6ef8",
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "old-user",
                            "content": [{"type": "text", "text": "older inherited prompt"}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "old-assistant",
                            "text": "older inherited answer",
                            "phase": "final_answer",
                        },
                    ],
                },
                {
                    "id": "019d38ba-a000-7000-8000-000000000001",
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "bootstrap-user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Initialization only. Do not call any tools. Reply with exactly READY.",
                                }
                            ],
                        },
                        {
                            "type": "agentMessage",
                            "id": "bootstrap-ready",
                            "text": "READY",
                            "phase": "final_answer",
                        },
                    ],
                },
                {
                    "id": "019d38bc-1854-7df2-843e-88ef9c7d3077",
                    "status": "completed",
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "exec-user",
                            "content": [{"type": "text", "text": "internal execution prompt"}],
                        },
                        {
                            "type": "agentMessage",
                            "id": "exec-commentary",
                            "text": "I am checking the repo layout.",
                            "phase": "commentary",
                        },
                        {
                            "type": "agentMessage",
                            "id": "exec-final",
                            "text": "Implemented the browser round interface.",
                            "phase": "final_answer",
                        },
                    ],
                },
            ],
        }
    }

    updated, changed = hydrate_snapshot_from_thread_read(snapshot, payload)

    assert changed is True
    assert updated["processingState"] == "idle"
    assert updated["activeTurnId"] is None
    assert [item["id"] for item in updated["items"]] == ["exec-commentary", "exec-final"]
    assert [item["kind"] for item in updated["items"]] == ["message", "message"]
    assert updated["items"][0]["metadata"]["phase"] == "commentary"
    assert updated["items"][1]["text"] == "Implemented the browser round interface."
