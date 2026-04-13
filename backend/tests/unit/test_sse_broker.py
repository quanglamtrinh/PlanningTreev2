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


def test_publish_fanout_reuses_single_cloned_payload() -> None:
    async def run() -> None:
        broker = ChatEventBroker()
        queue_a = broker.subscribe("project-1", "node-1")
        queue_b = broker.subscribe("project-1", "node-1")
        payload = {"type": "assistant_completed", "content": {"text": "hello"}}

        broker.publish("project-1", "node-1", payload)
        payload["content"]["text"] = "changed"

        event_a = await asyncio.wait_for(queue_a.get(), timeout=1)
        event_b = await asyncio.wait_for(queue_b.get(), timeout=1)
        assert event_a["content"]["text"] == "hello"
        assert event_b["content"]["text"] == "hello"
        assert event_a is event_b

        broker.unsubscribe("project-1", "node-1", queue_a)
        broker.unsubscribe("project-1", "node-1", queue_b)

    asyncio.run(run())


def test_publish_marks_lagged_subscriber_when_queue_is_full() -> None:
    async def run() -> None:
        broker = ChatEventBroker(subscriber_queue_max=1)
        queue = broker.subscribe("project-1", "node-1")

        broker.publish("project-1", "node-1", {"type": "assistant_delta", "content": "first"})
        broker.publish("project-1", "node-1", {"type": "assistant_delta", "content": "second"})
        await asyncio.sleep(0)

        first = await asyncio.wait_for(queue.get(), timeout=1)
        assert first["content"] == "first"
        assert broker.consume_lagged_disconnect("project-1", "node-1", queue) is True
        assert broker.consume_lagged_disconnect("project-1", "node-1", queue) is False

        broker.unsubscribe("project-1", "node-1", queue)

    asyncio.run(run())
