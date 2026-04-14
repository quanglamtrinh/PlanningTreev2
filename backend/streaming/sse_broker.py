from __future__ import annotations

import asyncio
import copy
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(eq=False)
class _Subscriber:
    queue: asyncio.Queue[dict[str, Any]]
    loop: asyncio.AbstractEventLoop
    lagged_signal: asyncio.Event


class EventBroker:
    def __init__(self, *, subscriber_queue_max: int = 128) -> None:
        self._subscriber_queue_max = max(1, int(subscriber_queue_max))
        self._queues: dict[tuple[str, ...], set[_Subscriber]] = defaultdict(set)
        self._lock = threading.Lock()

    def publish(self, project_id: str, node_id: str, event: dict[str, Any], thread_role: str = "") -> None:
        keys: list[tuple[str, ...]] = [(project_id, node_id)]
        if thread_role:
            keys.append((project_id, node_id, thread_role))
        with self._lock:
            subscribers: list[_Subscriber] = []
            for key in keys:
                subscribers.extend(self._queues.get(key, set()))
        if not subscribers:
            return
        fanout_event = copy.deepcopy(event)
        for subscriber in subscribers:
            subscriber.loop.call_soon_threadsafe(
                self._put_nowait,
                subscriber,
                fanout_event,
            )

    def subscribe(self, project_id: str, node_id: str, thread_role: str = "") -> asyncio.Queue[dict[str, Any]]:
        subscriber = _Subscriber(
            queue=asyncio.Queue(maxsize=self._subscriber_queue_max),
            loop=asyncio.get_running_loop(),
            lagged_signal=asyncio.Event(),
        )
        key: tuple[str, ...] = (project_id, node_id, thread_role) if thread_role else (project_id, node_id)
        with self._lock:
            self._queues[key].add(subscriber)
        return subscriber.queue

    def unsubscribe(
        self,
        project_id: str,
        node_id: str,
        queue: asyncio.Queue[dict[str, Any]],
        thread_role: str = "",
    ) -> None:
        key: tuple[str, ...] = (project_id, node_id, thread_role) if thread_role else (project_id, node_id)
        with self._lock:
            subscribers = self._queues.get(key, set())
            target = next((item for item in subscribers if item.queue is queue), None)
            if target is not None:
                subscribers.discard(target)
            if not subscribers and key in self._queues:
                self._queues.pop(key, None)

    def get_lagged_signal(
        self,
        project_id: str,
        node_id: str,
        queue: asyncio.Queue[dict[str, Any]],
        thread_role: str = "",
    ) -> asyncio.Event | None:
        key: tuple[str, ...] = (project_id, node_id, thread_role) if thread_role else (project_id, node_id)
        with self._lock:
            subscribers = self._queues.get(key, set())
            target = next((item for item in subscribers if item.queue is queue), None)
            return target.lagged_signal if target is not None else None

    def consume_lagged_disconnect(
        self,
        project_id: str,
        node_id: str,
        queue: asyncio.Queue[dict[str, Any]],
        thread_role: str = "",
    ) -> bool:
        signal = self.get_lagged_signal(project_id, node_id, queue, thread_role=thread_role)
        if signal is None or not signal.is_set():
            return False
        signal.clear()
        return True

    @staticmethod
    def _put_nowait(subscriber: _Subscriber, event: dict[str, Any]) -> None:
        try:
            subscriber.queue.put_nowait(event)
        except asyncio.QueueFull:
            subscriber.lagged_signal.set()
            return


class ChatEventBroker(EventBroker):
    pass


class GlobalEventBroker:
    def __init__(self, *, subscriber_queue_max: int = 128) -> None:
        self._subscriber_queue_max = max(1, int(subscriber_queue_max))
        self._subscribers: set[_Subscriber] = set()
        self._lock = threading.Lock()

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        if not subscribers:
            return
        fanout_event = copy.deepcopy(event)
        for subscriber in subscribers:
            subscriber.loop.call_soon_threadsafe(
                EventBroker._put_nowait,
                subscriber,
                fanout_event,
            )

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        subscriber = _Subscriber(
            queue=asyncio.Queue(maxsize=self._subscriber_queue_max),
            loop=asyncio.get_running_loop(),
            lagged_signal=asyncio.Event(),
        )
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber.queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            target = next((item for item in self._subscribers if item.queue is queue), None)
            if target is not None:
                self._subscribers.discard(target)

    def get_lagged_signal(self, queue: asyncio.Queue[dict[str, Any]]) -> asyncio.Event | None:
        with self._lock:
            target = next((item for item in self._subscribers if item.queue is queue), None)
            return target.lagged_signal if target is not None else None

    def consume_lagged_disconnect(self, queue: asyncio.Queue[dict[str, Any]]) -> bool:
        signal = self.get_lagged_signal(queue)
        if signal is None or not signal.is_set():
            return False
        signal.clear()
        return True
