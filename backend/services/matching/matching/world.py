"""Where the matching service gets its world from."""

from __future__ import annotations

import asyncio
import time

from cappy_common.http import ServiceClient
from cappy_common.models import World


class WorldProvider:
    async def get(self) -> World:
        raise NotImplementedError

    def invalidate(self) -> None:
        """Drop any cached copy."""

    async def aclose(self) -> None:
        """Release resources."""


class StaticWorldProvider(WorldProvider):
    """A fixed world. Tests use it; so could a read-only replica."""

    def __init__(self, world: World) -> None:
        self.world = world

    async def get(self) -> World:
        return self.world


class CatalogWorldProvider(WorldProvider):
    """Fetches ``GET /world`` from the catalog, cached for a short TTL.

    The cache is a latency trade, not a consistency one: the catalog publishes
    ``catalog.changed`` on every write and the service drops the copy on
    receipt, so a paused listing disappears from results within one event hop.
    """

    def __init__(self, client: ServiceClient, ttl_seconds: float) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._world: World | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> World:
        if self._world is not None and time.monotonic() - self._fetched_at < self._ttl:
            return self._world
        async with self._lock:
            if self._world is not None and time.monotonic() - self._fetched_at < self._ttl:
                return self._world
            data = await self._client.get("/world")
            self._world = World.model_validate(data)
            self._fetched_at = time.monotonic()
            return self._world

    def invalidate(self) -> None:
        self._fetched_at = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()
