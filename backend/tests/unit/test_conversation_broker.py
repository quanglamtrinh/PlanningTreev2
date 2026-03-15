from __future__ import annotations

import asyncio
import threading

from backend.streaming.conversation_broker import ConversationEventBroker


def test_publish_delivers_event_from_background_thread() -> None:
    async def run() -> None:
        broker = ConversationEventBroker()
        queue = broker.subscribe("project-1", "conv-1")

        def publish() -> None:
            broker.publish("project-1", "conv-1", {"event_type": "message_created", "event_seq": 1})

        thread = threading.Thread(target=publish)
        thread.start()
        thread.join()

        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == {"event_type": "message_created", "event_seq": 1}

        broker.unsubscribe("project-1", "conv-1", queue)

    asyncio.run(run())


def test_publish_deep_copies_event_payload() -> None:
    async def run() -> None:
        broker = ConversationEventBroker()
        queue = broker.subscribe("project-1", "conv-1")
        payload = {
            "event_type": "message_created",
            "event_seq": 2,
            "payload": {"message": {"message_id": "msg_1"}},
        }

        broker.publish("project-1", "conv-1", payload)
        payload["payload"]["message"]["message_id"] = "changed"

        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event["payload"]["message"]["message_id"] == "msg_1"

        broker.unsubscribe("project-1", "conv-1", queue)

    asyncio.run(run())
