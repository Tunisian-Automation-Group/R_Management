"""Payments: the intent behind every booking, owner onboarding, Stripe's webhook."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Depends, Request
from pydantic import Field
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_internal, require_principal
from cappy_common.errors import Conflict, Invalid, NotFound
from cappy_common.events import PAYMENT_AUTHORISED, PAYOUTS_READY
from cappy_common.models import CamelModel
from cappy_common.runtime import Tx

from .provider import Provider
from .tables import PROCESSED, ConnectAccountRow, PaymentRow

log = logging.getLogger(__name__)
router = ApiRouter(prefix="/payments")
internal = ApiRouter(prefix="/internal", dependencies=[Depends(require_internal)])


def _now() -> datetime:
    return datetime.now(UTC)


def _provider(request: Request) -> Provider:
    return request.app.state.provider


class IntentIn(CamelModel):
    booking_id: str = Field(max_length=40)
    requester_id: str = Field(max_length=64)
    owner_id: str = Field(max_length=64)
    amount: int = Field(gt=0, le=10_000_000)
    owner_net: int = Field(ge=0)
    currency: str = Field(pattern="^[a-z]{3}$")


class IntentOut(CamelModel):
    client_secret: str
    intent_id: str


class Config(CamelModel):
    provider: str
    publishable_key: str | None = None


class Onboarding(CamelModel):
    url: str


class ConnectStatus(CamelModel):
    connected: bool
    payouts_enabled: bool
    details_submitted: bool


class PaymentView(CamelModel):
    booking_id: str
    status: str
    amount: int
    currency: str


async def _update_account(
    request: Request, session: AsyncSession, account: ConnectAccountRow, payouts: bool, submitted: bool
) -> None:
    """Record what Stripe says about an owner's account, and tell the catalog
    when that changes whether they can be booked."""
    changed = account.payouts_enabled != payouts
    account.payouts_enabled, account.details_submitted = payouts, submitted
    account.updated_at = _now()
    if changed:
        await request.app.state.outbox.add(session, PAYOUTS_READY, {"ownerId": account.owner_id, "ready": payouts})


async def _authorised(request: Request, session: AsyncSession, row: PaymentRow) -> bool:
    """Mark authorised and tell booking. False if it already was."""
    if row.status != "created":
        return False
    row.status = "authorised"
    row.updated_at = _now()
    await request.app.state.outbox.add(session, PAYMENT_AUTHORISED, {"bookingId": row.booking_id})
    return True


# --- booking asks for the intent ------------------------------------------------------------


@internal.post("/intents", response_model=IntentOut)
async def create_intent(body: IntentIn, request: Request, session: AsyncSession = Tx) -> IntentOut:
    """Idempotent per booking: a retried booking gets the same intent back."""
    provider = _provider(request)
    if body.owner_net > body.amount:
        raise Invalid("the owner's share cannot exceed the price")
    row = await session.get(PaymentRow, body.booking_id)
    if row is not None:
        return IntentOut(client_secret=await provider.client_secret(row.intent_id), intent_id=row.intent_id)

    account = await session.get(ConnectAccountRow, body.owner_id)
    if provider.name == "fake" and account is None:
        account = ConnectAccountRow(
            owner_id=body.owner_id,
            account_id=await provider.create_account(body.owner_id),
            payouts_enabled=False,
            details_submitted=False,
            updated_at=_now(),
        )
        session.add(account)
        await _update_account(request, session, account, True, True)
    if account is None or not account.payouts_enabled:
        # ADR 0005: nobody books an owner we could not pay.
        raise Conflict("this owner has not finished setting up payments yet, so they cannot take bookings")

    intent = await provider.create_intent(
        booking_id=body.booking_id,
        amount=body.amount,
        currency=body.currency,
        metadata={"requesterId": body.requester_id, "ownerId": body.owner_id},
    )
    now = _now()
    row = PaymentRow(
        booking_id=body.booking_id,
        intent_id=intent.id,
        requester_id=body.requester_id,
        owner_id=body.owner_id,
        amount=body.amount,
        owner_net=body.owner_net,
        currency=body.currency,
        status="created",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    if provider.authorises_immediately:
        await _authorised(request, session, row)
    return IntentOut(client_secret=intent.client_secret, intent_id=intent.id)


# --- the app ----------------------------------------------------------------------------------


@router.get("/config", response_model=Config)
async def config(request: Request) -> Config:
    """What the app needs to load Stripe.js, or to know there is no card step."""
    s = request.app.state.settings
    return Config(provider=_provider(request).name, publishable_key=s.stripe_publishable_key or None)


@router.get("/bookings/{booking_id}", response_model=PaymentView)
async def payment_for_booking(
    booking_id: str, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> PaymentView:
    row = await session.get(PaymentRow, booking_id)
    if row is None or p.sub not in (row.requester_id, row.owner_id):
        raise NotFound(f"no payment for booking {booking_id}")
    return PaymentView(booking_id=row.booking_id, status=row.status, amount=row.amount, currency=row.currency)


@router.post("/connect/onboarding", response_model=Onboarding)
async def onboarding(request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)):
    """A Stripe-hosted page where an owner gives Stripe their identity and bank
    details. We never see either."""
    provider = _provider(request)
    base = request.app.state.settings.web_base_url.rstrip("/")
    account = await session.get(ConnectAccountRow, p.sub)
    if account is None:
        account = ConnectAccountRow(owner_id=p.sub, account_id=await provider.create_account(p.sub), updated_at=_now())
        session.add(account)
    url = await provider.onboarding_link(
        account.account_id, f"{base}/earn?payments=done", f"{base}/earn?payments=retry"
    )
    return Onboarding(url=url)


@router.get("/connect/status", response_model=ConnectStatus)
async def connect_status(request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)):
    account = await session.get(ConnectAccountRow, p.sub)
    if account is None:
        return ConnectStatus(connected=False, payouts_enabled=False, details_submitted=False)
    if not account.payouts_enabled:
        # Webhooks keep this current; asking here as well means an owner
        # coming back from onboarding sees the result without waiting for one.
        status = await _provider(request).account_status(account.account_id)
        await _update_account(request, session, account, status.payouts_enabled, status.details_submitted)
    return ConnectStatus(
        connected=True, payouts_enabled=account.payouts_enabled, details_submitted=account.details_submitted
    )


# --- Stripe -----------------------------------------------------------------------------------


@router.post("/webhooks/stripe", status_code=200)
async def stripe_webhook(request: Request, session: AsyncSession = Tx) -> dict:
    """The source of truth for what happened at Stripe. Signature-verified,
    and handled once per Stripe event id however often Stripe retries."""
    event = _provider(request).parse_webhook(await request.body(), request.headers.get("stripe-signature", ""))
    try:
        async with session.begin_nested():
            await session.execute(
                insert(PROCESSED).values(event_id=event["id"][:40], type=event["type"][:80], processed_at=_now())
            )
    except IntegrityError:
        return {"received": True, "duplicate": True}

    obj = event["data"]["object"]
    kind = event["type"]
    if kind == "payment_intent.amount_capturable_updated":
        row = (await session.execute(select(PaymentRow).where(PaymentRow.intent_id == obj["id"]))).scalar_one_or_none()
        if row is not None:
            await _authorised(request, session, row)
    elif kind == "account.updated":
        q = select(ConnectAccountRow).where(ConnectAccountRow.account_id == obj["id"])
        account = (await session.execute(q)).scalar_one_or_none()
        if account is not None:
            await _update_account(
                request, session, account, bool(obj.get("payouts_enabled")), bool(obj.get("details_submitted"))
            )
    else:
        log.info("ignoring stripe event %s", kind)
    return {"received": True}
