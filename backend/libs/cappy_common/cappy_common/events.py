"""A small event bus: publish JSON events on a topic, subscribe with a handler.

Two implementations behind one interface:

* ``MemoryEventBus``: in-process, used by tests and by ``memory://`` deployments.
* ``RedisEventBus``: Redis Streams with a consumer group per service, so a
  service that is down when an event is published still receives it when it
  comes back. That matters for ``booking.rated``: an owner's record must never
  silently miss a rating.

Handlers are ``async def handler(payload: dict) -> None``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[None]]

# Topic names, in one place so producers and consumers cannot drift.
BOOKING_REQUESTED = "booking.requested"
BOOKING_STATUS_CHANGED = "booking.status_changed"
BOOKING_RATED = "booking.rated"
CATALOG_CHANGED = "catalog.changed"


class EventBus:
    async def publish(self, topic: str, payload: dict) -> None:
        raise NotImplementedError

    def subscribe(self, topic: str, handler: Handler) -> None:
        raise NotImplementedError

    async def start(self) -> None:
        """Begin delivering events to subscribers."""

    async def stop(self) -> None:
        """Stop delivering and release resources."""


class MemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))
        for handler in list(self._handlers.get(topic, [])):
            try:
                await handler(payload)
            except Exception:  # noqa: BLE001 - one bad handler must not break the publisher
                log.exception("handler for %s failed", topic)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)


class RedisEventBus(EventBus):
    def __init__(self, url: str, group: str, *, block_ms: int = 1000) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=True)
        self._group = group
        self._consumer = f"{group}-{id(self):x}"
        self._block_ms = block_ms
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._task: asyncio.Task | None = None

    @staticmethod
    def _stream(topic: str) -> str:
        return f"cappy:events:{topic}"

    async def publish(self, topic: str, payload: dict) -> None:
        await self._redis.xadd(self._stream(topic), {"json": json.dumps(payload)})

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    async def start(self) -> None:
        if not self._handlers:
            return
        for topic in self._handlers:
            # MKSTREAM so subscribing before the first publish is fine; "$" means
            # new events only for a brand-new group. BUSYGROUP on restart is expected.
            with contextlib.suppress(Exception):
                await self._redis.xgroup_create(self._stream(topic), self._group, id="$", mkstream=True)
        self._task = asyncio.create_task(self._loop(), name=f"eventbus:{self._group}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._redis.aclose()

    async def _loop(self) -> None:
        streams = {self._stream(t): ">" for t in self._handlers}
        while True:
            try:
                batches = await self._redis.xreadgroup(
                    self._group, self._consumer, streams, count=32, block=self._block_ms
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("event bus read failed; retrying")
                await asyncio.sleep(1)
                continue
            for stream, messages in batches or []:
                topic = stream.removeprefix("cappy:events:")
                for msg_id, fields in messages:
                    payload = json.loads(fields.get("json", "{}"))
                    for handler in self._handlers.get(topic, []):
                        try:
                            await handler(payload)
                        except Exception:  # noqa: BLE001
                            log.exception("handler for %s failed", topic)
                    await self._redis.xack(stream, self._group, msg_id)


def make_event_bus(url: str, group: str) -> EventBus:
    if url.startswith("memory://"):
        return MemoryEventBus()
    if url.startswith(("redis://", "rediss://")):
        return RedisEventBus(url, group)
    raise ValueError(f"unsupported event bus url: {url}")
