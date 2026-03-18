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


def test_publish_isolated_by_project_and_conversation_key() -> None:
    async def run() -> None:
        broker = ConversationEventBroker()
        queue_one = broker.subscribe("project-1", "conv-1")
        queue_same_project_other_conversation = broker.subscribe("project-1", "conv-2")
        queue_other_project_same_conversation = broker.subscribe("project-2", "conv-1")

        broker.publish("project-1", "conv-1", {"event_type": "message_created", "event_seq": 3})

        event = await asyncio.wait_for(queue_one.get(), timeout=1)
        assert event == {"event_type": "message_created", "event_seq": 3}

        try:
            await asyncio.wait_for(queue_same_project_other_conversation.get(), timeout=0.05)
        except TimeoutError:
            pass
        else:  # pragma: no cover - explicit failure path
            raise AssertionError("wrong conversation queue received an event")

        try:
            await asyncio.wait_for(queue_other_project_same_conversation.get(), timeout=0.05)
        except TimeoutError:
            pass
        else:  # pragma: no cover - explicit failure path
            raise AssertionError("wrong project queue received an event")

        broker.unsubscribe("project-1", "conv-1", queue_one)
        broker.unsubscribe("project-1", "conv-2", queue_same_project_other_conversation)
        broker.unsubscribe("project-2", "conv-1", queue_other_project_same_conversation)

    asyncio.run(run())
