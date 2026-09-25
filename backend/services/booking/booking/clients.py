"""What booking asks of other services. Interfaces, so tests pass fakes."""

from __future__ import annotations

from urllib.parse import quote

from cappy_common.http import ServiceClient
from cappy_common.models import CamelModel, Cents, Iso, MatchView


class PaymentStart(CamelModel):
    """What the app needs to collect the card: Stripe's client secret for the
    PaymentIntent that holds (authorises, not captures) the booking's price."""

    client_secret: str
    intent_id: str


class Matching:
    async def match_for_offer(
        self, requirement: dict, listing_id: str, slot_id: str, start: Iso, end: Iso
    ) -> MatchView:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class Payments:
    async def start(
        self, *, booking_id: str, requester_id: str, owner_id: str, amount: Cents, owner_net: Cents, currency: str
    ) -> PaymentStart:
        """Idempotent per booking: asking twice returns the same intent."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class Catalog:
    async def handover(self, listing_id: str) -> dict:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class HttpCatalog(Catalog):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def handover(self, listing_id: str) -> dict:
        return await self._c.get(f"/internal/listings/{quote(listing_id, safe='')}/handover")

    async def aclose(self) -> None:
        await self._c.aclose()


class HttpMatching(Matching):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def match_for_offer(self, requirement, listing_id, slot_id, start, end) -> MatchView:  # noqa: ANN001
        body = {"requirement": requirement, "listingId": listing_id, "slotId": slot_id, "start": start, "end": end}
        return MatchView.model_validate(await self._c.post("/internal/match-for-offer", json=body))

    async def aclose(self) -> None:
        await self._c.aclose()


class HttpPayments(Payments):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def start(self, *, booking_id, requester_id, owner_id, amount, owner_net, currency) -> PaymentStart:  # noqa: ANN001
        body = {
            "bookingId": booking_id,
            "requesterId": requester_id,
            "ownerId": owner_id,
            "amount": amount,
            "ownerNet": owner_net,
            "currency": currency,
        }
        return PaymentStart.model_validate(await self._c.post("/internal/intents", json=body))

    async def aclose(self) -> None:
        await self._c.aclose()
