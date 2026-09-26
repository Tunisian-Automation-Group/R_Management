"""What matching asks of other services. Interfaces first, so tests can pass
fakes; HTTP implementations for everything else."""

from __future__ import annotations

import time
from urllib.parse import quote

from cappy_common.http import ServiceClient
from cappy_common.models import Iso, World
from cappy_common.timeutil import ms_from_iso

Busy = dict[str, list[tuple[int, int]]]


class Catalog:
    async def candidates(
        self, *, origin: str, max_km: float, start: Iso, until: Iso, category: str | None, exclude_owner: str | None
    ) -> World:
        raise NotImplementedError

    async def listing_context(
        self, listing_id: str, *, after: Iso, origin: str | None = None, staff: bool = False
    ) -> World:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class Bookings:
    async def busy(self, listing_ids: list[str], start: Iso, until: Iso) -> Busy:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class HttpCatalog(Catalog):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def candidates(self, *, origin, max_km, start, until, category, exclude_owner) -> World:  # noqa: ANN001
        body = {"origin": origin, "maxKm": max_km, "start": start, "until": until}
        if category:
            body["category"] = category
        if exclude_owner:
            body["excludeOwner"] = exclude_owner
        return World.model_validate(await self._c.post("/internal/candidates", json=body))

    async def listing_context(
        self, listing_id: str, *, after: Iso, origin: str | None = None, staff: bool = False
    ) -> World:
        params = {"after": after, **({"origin": origin} if origin else {}), **({"staff": "true"} if staff else {})}
        # Encoded: an id is data, never a path (``../owners/x`` must stay one segment).
        path = f"/internal/listings/{quote(listing_id, safe='')}/context"
        return World.model_validate(await self._c.get(path, params=params))

    async def aclose(self) -> None:
        await self._c.aclose()


class CatalogRevocations:
    """``not_before`` per person, asked of catalog and cached briefly: the same
    interface as ``cappy_common.guard.Revocations``, for a service with no
    database (P-24). If catalog cannot answer, the request fails with its 5xx:
    never a 401 that would sign the person out, never a revoked token let
    through. ponytail: a dict with a TTL, cleared when large, like Revocations."""

    def __init__(self, base_url: str, token: str, ttl: float = 30.0) -> None:
        self._c = ServiceClient(base_url, internal_token=token)
        self._ttl = ttl
        self._cache: dict[str, tuple[float, float | None]] = {}

    async def not_before(self, sub: str) -> float | None:
        now = time.monotonic()
        hit = self._cache.get(sub)
        if hit and hit[0] > now:
            return hit[1]
        value = (await self._c.get(f"/internal/revocations/{quote(sub, safe='')}"))["notBefore"]
        if len(self._cache) > 50_000:
            self._cache.clear()
        self._cache[sub] = (now + self._ttl, value)
        return value

    async def aclose(self) -> None:
        await self._c.aclose()


class HttpBookings(Bookings):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def busy(self, listing_ids: list[str], start: Iso, until: Iso) -> Busy:
        if not listing_ids:
            return {}
        data = await self._c.post("/internal/busy", json={"listingIds": listing_ids, "start": start, "until": until})
        return {lid: [(ms_from_iso(a), ms_from_iso(b)) for a, b in spans] for lid, spans in data.items()}

    async def aclose(self) -> None:
        await self._c.aclose()
