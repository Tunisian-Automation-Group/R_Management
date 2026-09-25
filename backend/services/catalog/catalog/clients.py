"""What the catalog asks the booking service. An interface, so tests pass a fake."""

from __future__ import annotations

from urllib.parse import quote

from cappy_common.http import ServiceClient


class Bookings:
    async def open_for(self, person: str) -> int:
        raise NotImplementedError

    async def all_for(self, person: str) -> list[dict]:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class Payments:
    async def export_for(self, person: str) -> dict:
        return {}

    async def aclose(self) -> None:
        """Release resources."""


class HttpPayments(Payments):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def export_for(self, person: str) -> dict:
        return await self._c.get(f"/internal/people/{quote(person, safe='')}/export")

    async def aclose(self) -> None:
        await self._c.aclose()


class HttpBookings(Bookings):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def open_for(self, person: str) -> int:
        return (await self._c.get(f"/internal/people/{quote(person, safe='')}/open"))["open"]

    async def all_for(self, person: str) -> dict:
        """Bookings, messages sent and hand-over photos, for an export."""
        return await self._c.get(f"/internal/people/{quote(person, safe='')}/export")

    async def aclose(self) -> None:
        await self._c.aclose()
