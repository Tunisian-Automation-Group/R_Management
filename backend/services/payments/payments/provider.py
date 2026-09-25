"""Stripe, behind the handful of calls we make. A fake with the same shape
runs tests and local development without keys.

Every call that moves money carries an idempotency key derived from the
booking, so a retried event can never capture, refund or pay out twice.
"""

from __future__ import annotations

from dataclasses import dataclass

import stripe

from cappy_common.errors import Invalid


@dataclass
class Intent:
    id: str
    client_secret: str


@dataclass
class AccountStatus:
    payouts_enabled: bool
    details_submitted: bool


# Accounts the fake provider made. They mean nothing to Stripe, so an
# environment switched to Stripe must not treat their owners as payable.
FAKE_ACCOUNT_PREFIX = "acct_fake_"


class Declined(Exception):
    """Stripe refused for good (a reversed authorisation, a closed account):
    retrying will not help, so the booking is told instead."""


class Provider:
    name: str
    # The fake has no card step: an intent is authorised the moment it exists.
    authorises_immediately = False

    async def create_intent(self, *, booking_id: str, amount: int, currency: str, metadata: dict) -> Intent: ...
    async def client_secret(self, intent_id: str) -> str: ...
    async def intent_status(self, intent_id: str) -> str:
        """Stripe's own word on an intent: requires_payment_method,
        requires_capture, succeeded, canceled, …"""

    async def capture(self, intent_id: str, booking_id: str) -> str:
        """Returns the charge id."""

    async def cancel(self, intent_id: str, booking_id: str) -> None: ...
    async def refund(self, intent_id: str, booking_id: str) -> str: ...
    async def transfer(
        self, *, booking_id: str, amount: int, currency: str, account_id: str, charge_id: str
    ) -> str: ...
    async def create_account(self, owner_id: str) -> str: ...
    async def onboarding_link(self, account_id: str, return_url: str, refresh_url: str) -> str: ...
    async def account_status(self, account_id: str) -> AccountStatus: ...
    def parse_webhook(self, payload: bytes, signature: str) -> dict: ...
    async def aclose(self) -> None: ...


class StripeProvider(Provider):
    name = "stripe"

    def __init__(self, secret_key: str, webhook_secret: str, api_base: str = "") -> None:
        # Bounded: every Stripe call happens while an event is being handled,
        # and an event must finish well inside its queue visibility timeout.
        kwargs: dict = {"http_client": stripe.HTTPXClient(timeout=10), "max_network_retries": 1}
        if api_base:
            kwargs["base_addresses"] = {"api": api_base}
        self._c = stripe.StripeClient(secret_key, **kwargs)
        self._webhook_secret = webhook_secret

    async def create_intent(self, *, booking_id, amount, currency, metadata) -> Intent:  # noqa: ANN001
        pi = await self._c.v1.payment_intents.create_async(
            {
                "amount": amount,
                "currency": currency,
                # Authorise now, capture when the owner accepts (ADR 0005).
                "capture_method": "manual",
                "automatic_payment_methods": {"enabled": True},
                "transfer_group": booking_id,
                "metadata": {"bookingId": booking_id, **metadata},
            },
            {"idempotency_key": f"intent-{booking_id}"},
        )
        return Intent(id=pi.id, client_secret=pi.client_secret or "")

    async def client_secret(self, intent_id: str) -> str:
        return (await self._c.v1.payment_intents.retrieve_async(intent_id)).client_secret or ""

    async def intent_status(self, intent_id: str) -> str:
        return (await self._c.v1.payment_intents.retrieve_async(intent_id)).status

    async def capture(self, intent_id: str, booking_id: str) -> str:
        # Idempotency keys live 24 hours and a dead-lettered event can be
        # redriven days later: look at the intent first, act only if needed.
        pi = await self._c.v1.payment_intents.retrieve_async(intent_id)
        if pi.status != "succeeded":
            try:
                pi = await self._c.v1.payment_intents.capture_async(
                    intent_id, {}, {"idempotency_key": f"capture-{booking_id}"}
                )
            except (stripe.CardError, stripe.InvalidRequestError) as e:
                raise Declined(str(e)) from e
        charge = pi.latest_charge
        return charge if isinstance(charge, str) else (charge.id if charge else "")

    async def cancel(self, intent_id: str, booking_id: str) -> None:
        try:
            await self._c.v1.payment_intents.cancel_async(intent_id, {}, {"idempotency_key": f"cancel-{booking_id}"})
        except stripe.InvalidRequestError as e:
            # Already cancelled, or never confirmed and since expired: the hold
            # is gone either way, which is all a cancel is for.
            if e.code != "payment_intent_unexpected_state":
                raise

    async def refund(self, intent_id: str, booking_id: str) -> str:
        done = await self._c.v1.refunds.list_async({"payment_intent": intent_id, "limit": 1})
        if done.data:
            return done.data[0].id
        r = await self._c.v1.refunds.create_async(
            {"payment_intent": intent_id}, {"idempotency_key": f"refund-{booking_id}"}
        )
        return r.id

    async def transfer(self, *, booking_id, amount, currency, account_id, charge_id) -> str:  # noqa: ANN001
        done = await self._c.v1.transfers.list_async({"transfer_group": booking_id, "limit": 1})
        if done.data:
            return done.data[0].id
        t = await self._c.v1.transfers.create_async(
            {
                "amount": amount,
                "currency": currency,
                "destination": account_id,
                "transfer_group": booking_id,
                # Tied to the charge: Stripe waits for its funds to settle.
                "source_transaction": charge_id,
            },
            {"idempotency_key": f"transfer-{booking_id}"},
        )
        return t.id

    async def create_account(self, owner_id: str) -> str:
        a = await self._c.v1.accounts.create_async(
            {
                "type": "express",
                "capabilities": {"transfers": {"requested": True}},
                "metadata": {"ownerId": owner_id},
            },
            {"idempotency_key": f"account-{owner_id}"},
        )
        return a.id

    async def onboarding_link(self, account_id: str, return_url: str, refresh_url: str) -> str:
        link = await self._c.v1.account_links.create_async(
            {"account": account_id, "type": "account_onboarding", "return_url": return_url, "refresh_url": refresh_url}
        )
        return link.url

    async def account_status(self, account_id: str) -> AccountStatus:
        a = await self._c.v1.accounts.retrieve_async(account_id)
        return AccountStatus(bool(a.payouts_enabled), bool(a.details_submitted))

    def parse_webhook(self, payload: bytes, signature: str) -> dict:
        try:
            event = stripe.Webhook.construct_event(payload, signature, self._webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as e:
            raise Invalid("not a genuine Stripe event") from e
        return event.to_dict()


class FakeProvider(Provider):
    """Records what would have happened. Every owner can be paid."""

    name = "fake"
    authorises_immediately = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failing: set[str] = set()
        self.statuses: dict[str, str] = {}

    def _call(self, op: str, key: str) -> None:
        if op in self.failing:
            raise RuntimeError(f"fake {op} failed")
        self.calls.append((op, key))

    async def create_intent(self, *, booking_id, amount, currency, metadata) -> Intent:  # noqa: ANN001
        self._call("intent", booking_id)
        return Intent(id=f"pi_fake_{booking_id}", client_secret=f"pi_fake_{booking_id}_secret_fake")

    async def client_secret(self, intent_id: str) -> str:
        return f"{intent_id}_secret_fake"

    async def intent_status(self, intent_id: str) -> str:
        return self.statuses.get(intent_id, "requires_capture")

    async def capture(self, intent_id: str, booking_id: str) -> str:
        if "capture_declined" in self.failing:
            raise Declined("the authorisation was reversed")
        self._call("capture", booking_id)
        return f"ch_fake_{booking_id}"

    async def cancel(self, intent_id: str, booking_id: str) -> None:
        self._call("cancel", booking_id)

    async def refund(self, intent_id: str, booking_id: str) -> str:
        self._call("refund", booking_id)
        return f"re_fake_{booking_id}"

    async def transfer(self, *, booking_id, amount, currency, account_id, charge_id) -> str:  # noqa: ANN001
        self._call("transfer", booking_id)
        return f"tr_fake_{booking_id}"

    async def create_account(self, owner_id: str) -> str:
        return f"{FAKE_ACCOUNT_PREFIX}{owner_id}"[:80]

    async def onboarding_link(self, account_id: str, return_url: str, refresh_url: str) -> str:
        return return_url

    async def account_status(self, account_id: str) -> AccountStatus:
        return AccountStatus(True, True)

    def parse_webhook(self, payload: bytes, signature: str) -> dict:
        raise Invalid("the fake provider takes no webhooks")


def make_provider(settings) -> Provider:  # noqa: ANN001
    if settings.payments_provider == "stripe":
        return StripeProvider(
            settings.stripe_secret_key.get_secret_value(),
            settings.stripe_webhook_secret.get_secret_value(),
            settings.stripe_api_base,
        )
    return FakeProvider()
