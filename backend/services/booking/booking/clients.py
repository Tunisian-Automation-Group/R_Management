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
        self, requirement: dict, listing_id: str, slot_id: str, start: Iso, end: Iso, *, extension: bool = False
    ) -> MatchView:
        """``extension``: the time straight after a booking, for its renter
        (S-12). No lead time (they are already there) and any idle slot that
        holds the window will do (``slot_id`` may be empty)."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class Payments:
    async def start(
        self, *, booking_id: str, requester_id: str, owner_id: str, amount: Cents, owner_net: Cents, currency: str
    ) -> PaymentStart:
        """Idempotent per booking: asking twice returns the same intent."""
        raise NotImplementedError

    async def state(self, booking_id: str) -> dict | None:
        """What payments holds for a booking (the staff case view, H-9)."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class Catalog:
    async def handover(self, listing_id: str) -> dict:
        raise NotImplementedError

    async def name_of(self, person: str) -> str | None:
        """The name a person goes by, for the owner's mails (V7-23)."""
        raise NotImplementedError

    async def keep_evidence(self, owner_id: str, urls: list[str]) -> None:
        """Refuses photos that are not the person's own uploads."""
        raise NotImplementedError

    async def evidence_photo(self, name: str) -> bytes:
        """A private hand-over photo's bytes (P-27)."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class HttpCatalog(Catalog):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def handover(self, listing_id: str) -> dict:
        return await self._c.get(f"/internal/listings/{quote(listing_id, safe='')}/handover")

    async def name_of(self, person: str) -> str | None:
        return (await self._c.get(f"/internal/people/{quote(person, safe='')}/name")).get("name")

    async def keep_evidence(self, owner_id: str, urls: list[str]) -> None:
        await self._c.post("/internal/media/evidence", json={"ownerId": owner_id, "urls": urls})

    async def evidence_photo(self, name: str) -> bytes:
        return await self._c.get(f"/internal/evidence/{quote(name, safe='')}", raw=True)

    async def aclose(self) -> None:
        await self._c.aclose()


class HttpMatching(Matching):
    def __init__(self, base_url: str, token: str) -> None:
        self._c = ServiceClient(base_url, internal_token=token)

    async def match_for_offer(self, requirement, listing_id, slot_id, start, end, *, extension=False) -> MatchView:  # noqa: ANN001
        body = {
            "requirement": requirement,
            "listingId": listing_id,
            "slotId": slot_id,
            "start": start,
            "end": end,
            "extension": extension,
        }
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

    async def state(self, booking_id: str) -> dict | None:
        from cappy_common.errors import ApiError

        try:
            return await self._c.get(f"/internal/bookings/{quote(booking_id, safe='')}/payment")
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    async def aclose(self) -> None:
        await self._c.aclose()


class People:
    """Who has an email address (the staff case lookup, H-9)."""

    async def sub_of(self, email: str) -> str | None:
        raise NotImplementedError


class CognitoPeople(People):
    def __init__(self, settings) -> None:  # noqa: ANN001
        self._settings, self._client = settings, None

    async def sub_of(self, email: str) -> str | None:
        import asyncio

        from cappy_common.events import aws_client

        def lookup() -> str | None:
            if self._client is None:
                self._client = aws_client("cognito-idp", self._settings, self._settings.cognito_endpoint_url)
            safe = email.replace("\\", "").replace('"', "")
            users = self._client.list_users(
                UserPoolId=self._settings.user_pool_id, Filter=f'email = "{safe}"', Limit=1
            )["Users"]
            attrs = {a["Name"]: a["Value"] for a in users[0]["Attributes"]} if users else {}
            return attrs.get("sub")

        return await asyncio.to_thread(lookup)
