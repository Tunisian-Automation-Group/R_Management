"""Identity verification (document and selfie), behind one small seam (F-1).

Payments owns it because the ID check gates bookings above a threshold, but it
is its own provider: moving from Stripe Identity to Onfido, Veriff or Persona
is a new class here, a setting, and a webhook secret. Nothing else changes:
routes and handlers see only ``IdentitySession`` and ``IdentityResult``.

To add a provider (e.g. Veriff):
1. A class with ``name``, ``verifies_immediately``, ``start_session``,
   ``parse_webhook`` and ``redact`` below, mapping its statuses to
   verified / failed / needs_input.
2. ``IDENTITY_PROVIDER=veriff`` plus its keys in settings.py and Terraform
   (secrets), and its webhook pointed at ``POST /api/payments/webhooks/identity``.
3. The web picks its UI from ``/api/payments/config`` → ``identityProvider``
   (``stripe``: Stripe.js verifyIdentity with ``clientSecret``; a hosted
   flow: open ``url``). A DPA with the provider (docs/FEATURES.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import stripe

from cappy_common.errors import Invalid

Status = Literal["verified", "failed", "needs_input"]


@dataclass
class IdentitySession:
    session_id: str
    # Stripe.js takes a client secret; hosted flows (Onfido, Veriff) a URL.
    client_secret: str | None = None
    url: str | None = None


@dataclass
class IdentityResult:
    """What a provider's webhook means, in our words."""

    session_id: str
    person_id: str | None
    status: Status


class IdentityProvider:
    name: str
    # The fake: a started check is a passed check.
    verifies_immediately = False

    async def start_session(self, person_id: str) -> IdentitySession: ...
    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> IdentityResult | None:
        """A verified webhook, or None when it is not about an ID check."""

    async def redact(self, session_id: str) -> None:
        """Erase the document and selfie at the provider (account deletion, D-6)."""


def stripe_result(event: dict) -> IdentityResult | None:
    """A Stripe event, if it is about an ID check. Shared with the payments
    webhook, since Stripe sends every event to one endpoint."""
    kind: str = event.get("type", "")
    if not kind.startswith("identity.verification_session."):
        return None
    obj = event["data"]["object"]
    status: Status | None = {
        "verified": "verified",
        "requires_input": "needs_input",
        "canceled": "failed",
    }.get(kind.rsplit(".", 1)[1])
    if status is None:  # processing, created, redacted: nothing to act on
        return None
    return IdentityResult(obj["id"], (obj.get("metadata") or {}).get("personId"), status)


class StripeIdentity(IdentityProvider):
    name = "stripe"

    def __init__(self, secret_key: str, webhook_secret: str, api_base: str = "") -> None:
        kwargs: dict = {"http_client": stripe.HTTPXClient(timeout=10), "max_network_retries": 1}
        if api_base:
            kwargs["base_addresses"] = {"api": api_base}
        self._c = stripe.StripeClient(secret_key, **kwargs)
        self._webhook_secret = webhook_secret

    async def start_session(self, person_id: str) -> IdentitySession:
        v = await self._c.v1.identity.verification_sessions.create_async(
            {
                "type": "document",
                "options": {"document": {"require_matching_selfie": True, "require_live_capture": True}},
                "metadata": {"personId": person_id},
            }
        )
        return IdentitySession(v.id, client_secret=v.client_secret or "")

    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> IdentityResult | None:
        try:
            event = stripe.Webhook.construct_event(payload, headers.get("stripe-signature", ""), self._webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as e:
            raise Invalid("not a genuine Stripe event") from e
        return stripe_result(event.to_dict())

    async def redact(self, session_id: str) -> None:
        try:
            await self._c.v1.identity.verification_sessions.redact_async(session_id)
        except stripe.InvalidRequestError as e:
            # Already redacted, or still processing (Stripe redacts those when
            # they finish only if asked again): gone either way is the goal.
            if e.code not in ("resource_missing",) and "already" not in str(e).lower():
                raise


class FakeIdentity(IdentityProvider):
    name = "fake"
    verifies_immediately = True

    def __init__(self) -> None:
        self.redacted: list[str] = []

    async def start_session(self, person_id: str) -> IdentitySession:
        return IdentitySession(f"vs_fake_{person_id}"[:80], client_secret="vs_fake_secret")

    def parse_webhook(self, payload: bytes, headers: dict[str, str]) -> IdentityResult | None:
        raise Invalid("the fake identity provider takes no webhooks")

    async def redact(self, session_id: str) -> None:
        self.redacted.append(session_id)


def make_identity(settings) -> IdentityProvider:  # noqa: ANN001
    if (settings.identity_provider or settings.payments_provider) == "stripe":
        return StripeIdentity(
            settings.stripe_secret_key.get_secret_value(),
            settings.stripe_webhook_secret.get_secret_value(),
            settings.stripe_api_base,
        )
    return FakeIdentity()
