from __future__ import annotations

import asyncio
import copy
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Subscriber:
    queue: asyncio.Queue[dict[str, Any]]
    loop: asyncio.AbstractEventLoop


class EventBroker:
    def __init__(self) -> None:
        self._queues: dict[tuple[str, str], set[_Subscriber]] = defaultdict(set)
        self._lock = threading.Lock()

    def publish(self, project_id: str, node_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = tuple(self._queues.get((project_id, node_id), set()))
        if not subscribers:
            return
        for subscriber in subscribers:
            subscriber.loop.call_soon_threadsafe(
                self._put_nowait,
                subscriber.queue,
                copy.deepcopy(event),
            )

    def subscribe(self, project_id: str, node_id: str) -> asyncio.Queue[dict[str, Any]]:
        subscriber = _Subscriber(
            queue=asyncio.Queue(),
            loop=asyncio.get_running_loop(),
        )
        with self._lock:
            self._queues[(project_id, node_id)].add(subscriber)
        return subscriber.queue

    def unsubscribe(
        self,
        project_id: str,
        node_id: str,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        key = (project_id, node_id)
        with self._lock:
            subscribers = self._queues.get(key, set())
            target = next((item for item in subscribers if item.queue is queue), None)
            if target is not None:
                subscribers.discard(target)
            if not subscribers and key in self._queues:
                self._queues.pop(key, None)

    @staticmethod
    def _put_nowait(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            return


class ChatEventBroker(EventBroker):
    pass
