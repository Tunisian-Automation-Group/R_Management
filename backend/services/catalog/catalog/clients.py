"""What the catalog asks the booking service. An interface, so tests pass a fake."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote, urlencode

from cappy_common.http import ServiceClient


class Bookings:
    async def open_for(self, person: str) -> dict:
        """``{"open": n, "until": iso | None}``."""
        raise NotImplementedError

    async def all_for(self, person: str) -> list[dict]:
        raise NotImplementedError

    async def active_people(self, start: datetime, end: datetime) -> int:
        """People who were a party to a booking made in [start, end)."""
        return 0

    async def aclose(self) -> None:
        """Release resources."""


class Payments:
    async def export_for(self, person: str) -> dict:
        return {}

    async def pending_payouts(self, person: str) -> int:
        return 0

    async def aclose(self) -> None:
        """Release resources."""


class HttpPayments(Payments):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def export_for(self, person: str) -> dict:
        return await self._c.get(f"/internal/people/{quote(person, safe='')}/export")

    async def pending_payouts(self, person: str) -> int:
        return (await self._c.get(f"/internal/people/{quote(person, safe='')}/open"))["pendingPayouts"]

    async def aclose(self) -> None:
        await self._c.aclose()


class HttpBookings(Bookings):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def open_for(self, person: str) -> dict:
        return await self._c.get(f"/internal/people/{quote(person, safe='')}/open")

    async def all_for(self, person: str) -> dict:
        """Bookings, messages sent and hand-over photos, for an export."""
        return await self._c.get(f"/internal/people/{quote(person, safe='')}/export")

    async def active_people(self, start: datetime, end: datetime) -> int:
        q = urlencode({"from": start.isoformat(), "until": end.isoformat()})
        return (await self._c.get(f"/internal/stats/active-people?{q}"))["people"]

    async def aclose(self) -> None:
        await self._c.aclose()


class Notifications:
    async def export_for(self, person: str) -> list[dict]:
        return []

    async def aclose(self) -> None:
        """Release resources."""


class HttpNotifications(Notifications):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def export_for(self, person: str) -> list[dict]:
        """The in-app notifications they were sent."""
        return await self._c.get(f"/internal/people/{quote(person, safe='')}/export")

    async def aclose(self) -> None:
        await self._c.aclose()
