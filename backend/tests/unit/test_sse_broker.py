from __future__ import annotations

import asyncio
import threading

from backend.streaming.sse_broker import ChatEventBroker


def test_publish_delivers_event_from_background_thread() -> None:
    async def run() -> None:
        broker = ChatEventBroker()
        queue = broker.subscribe("project-1", "node-1")

        def publish() -> None:
            broker.publish("project-1", "node-1", {"type": "assistant_delta", "content": "hello"})

        thread = threading.Thread(target=publish)
        thread.start()
        thread.join()

        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == {"type": "assistant_delta", "content": "hello"}

        broker.unsubscribe("project-1", "node-1", queue)

    asyncio.run(run())


def test_publish_deep_copies_event_payload() -> None:
    async def run() -> None:
        broker = ChatEventBroker()
        queue = broker.subscribe("project-1", "node-1")
        payload = {"type": "assistant_completed", "content": {"text": "hello"}}

        broker.publish("project-1", "node-1", payload)
        payload["content"]["text"] = "changed"

        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event["content"]["text"] == "hello"

        broker.unsubscribe("project-1", "node-1", queue)

    asyncio.run(run())
