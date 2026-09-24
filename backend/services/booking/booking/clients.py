"""What the booking service needs from the matching service, as an interface.

Tests substitute a fake; production uses HTTP.
"""

from __future__ import annotations

from cappy_common.http import ServiceClient
from cappy_common.models import AnyRequirement, CamelModel, Iso, Match


class Offer(CamelModel):
    slot_id: str
    start: Iso
    end: Iso


class MatchingClient:
    async def match_for_offer(
        self, requirement: AnyRequirement, listing_id: str, slot_id: str, start: Iso, end: Iso
    ) -> Match:
        raise NotImplementedError

    async def first_offer(self, listing_id: str, hours: float, from_: Iso, until: Iso) -> Offer | None:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class CatalogClient:
    """The one thing booking asks the catalog directly: which edition of the
    world it is serving, so bookings against a world that no longer exists
    can be recognised at startup."""

    async def world_version(self) -> str:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class HttpCatalogClient(CatalogClient):
    def __init__(self, base_url: str) -> None:
        self._client = ServiceClient(base_url)

    async def world_version(self) -> str:
        return (await self._client.get("/world/version"))["version"]

    async def aclose(self) -> None:
        await self._client.aclose()


class HttpMatchingClient(MatchingClient):
    def __init__(self, base_url: str) -> None:
        self._client = ServiceClient(base_url)

    async def match_for_offer(
        self, requirement: AnyRequirement, listing_id: str, slot_id: str, start: Iso, end: Iso
    ) -> Match:
        data = await self._client.post(
            "/match-for-offer",
            json={
                "requirement": requirement.model_dump(mode="json", by_alias=True),
                "listingId": listing_id,
                "slotId": slot_id,
                "start": start,
                "end": end,
            },
        )
        return Match.model_validate(data)

    async def first_offer(self, listing_id: str, hours: float, from_: Iso, until: Iso) -> Offer | None:
        data = await self._client.get(
            f"/listings/{listing_id}/offers",
            params={"hours": hours, "from": from_, "until": until, "limit": 1},
        )
        return Offer.model_validate(data[0]) if data else None

    async def aclose(self) -> None:
        await self._client.aclose()
