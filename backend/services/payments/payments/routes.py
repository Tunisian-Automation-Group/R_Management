"""Payments: the intent behind every booking, owner onboarding, Stripe's webhook."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Depends, Request
from pydantic import Field
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_internal, require_principal
from cappy_common.db import insert_or_ignore
from cappy_common.errors import Conflict, Invalid, NotFound, Unavailable
from cappy_common.events import IDENTITY_VERIFIED, PAYMENT_AUTHORISED, PAYOUTS_READY
from cappy_common.models import CamelModel
from cappy_common.runtime import Tx

from .provider import FAKE_ACCOUNT_PREFIX, Provider
from .tables import PROCESSED, ConnectAccountRow, IdentityRow, PaymentRow

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
    await session.flush()
    if changed:
        # asOf lets the catalog ignore an older state that arrives late.
        await request.app.state.outbox.add(
            session,
            PAYOUTS_READY,
            {"ownerId": account.owner_id, "ready": payouts, "asOf": account.updated_at.isoformat()},
        )


async def _authorised(request: Request, session: AsyncSession, row: PaymentRow) -> bool:
    """Mark authorised and tell booking. False if it already was."""
    if row.status != "created":
        return False
    row.status = "authorised"
    row.updated_at = _now()
    try:
        row.card_fingerprint = await _provider(request).card_fingerprint(row.intent_id, row.requester_id)
    except Exception as e:  # noqa: BLE001 - a fraud signal, never a reason to fail a payment
        log.warning("no card fingerprint for %s: %s", row.booking_id, e)
    await request.app.state.outbox.add(
        session, PAYMENT_AUTHORISED, {"bookingId": row.booking_id, "cardFingerprint": row.card_fingerprint}
    )
    return True


# --- booking asks for the intent ------------------------------------------------------------


@internal.post("/intents", response_model=IntentOut)
async def create_intent(body: IntentIn, request: Request) -> IntentOut:
    """Idempotent per booking: a retried booking gets the same intent back.

    No database connection is held while Stripe answers: a slow Stripe must
    not use up the pool that every other request needs."""
    provider = _provider(request)
    db = request.app.state.db
    if body.owner_net > body.amount:
        raise Invalid("the owner's share cannot exceed the price")

    async with db.transaction() as session:
        row = await session.get(PaymentRow, body.booking_id)
        if row is None:
            account = await session.get(ConnectAccountRow, body.owner_id)
            if provider.name == "fake" and account is None:
                # Locally every owner can be paid. Racing first bookings of a
                # new owner both land here; one inserts, both then read it.
                await insert_or_ignore(
                    session,
                    ConnectAccountRow,
                    owner_id=body.owner_id,
                    account_id=await provider.create_account(body.owner_id),
                    payouts_enabled=False,
                    details_submitted=False,
                    updated_at=_now(),
                )
                account = await session.get(
                    ConnectAccountRow, body.owner_id, with_for_update=True, populate_existing=True
                )
                if not account.payouts_enabled:
                    await _update_account(request, session, account, True, True)
            if provider.name != "fake" and account is not None and account.account_id.startswith(FAKE_ACCOUNT_PREFIX):
                account = None  # made by the fake provider: Stripe has never heard of it
            if account is None or not account.payouts_enabled:
                # ADR 0005: nobody books an owner we could not pay.
                raise Conflict("this owner has not finished setting up payments yet, so they cannot take bookings")
    request.app.state.relay.wake()
    if row is not None:
        return IntentOut(client_secret=await provider.client_secret(row.intent_id), intent_id=row.intent_id)

    try:
        # Stripe returns the same intent for the same key, so two racing
        # requests for one booking get one intent.
        intent = await provider.create_intent(
            booking_id=body.booking_id,
            amount=body.amount,
            currency=body.currency,
            metadata={"requesterId": body.requester_id, "ownerId": body.owner_id},
        )
    except Exception as e:  # noqa: BLE001 - transient by default: booking keeps the booking and retries
        log.warning("creating the intent for %s failed: %s", body.booking_id, e)
        raise Unavailable("the payment provider did not answer; try again") from e

    now = _now()
    async with db.transaction() as session:
        await insert_or_ignore(
            session,
            PaymentRow,
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
        row = await session.get(PaymentRow, body.booking_id, with_for_update=True)
        if provider.authorises_immediately:
            await _authorised(request, session, row)
    request.app.state.relay.wake()
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


# --- identity (Stripe Identity) ---------------------------------------------------------------


class IdentityOut(CamelModel):
    status: str
    client_secret: str | None = None


async def _verified(request: Request, session: AsyncSession, row: IdentityRow) -> None:
    if row.status != "verified":
        row.status, row.verified_at = "verified", _now()
        await request.app.state.outbox.add(session, IDENTITY_VERIFIED, {"personId": row.person_id})


@router.post("/identity/session", response_model=IdentityOut)
async def identity_session(request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)):
    """Starts (or continues) verifying who the caller is. The app hands the
    client secret to Stripe.js (verifyIdentity); the outcome comes by webhook."""
    row = await session.get(IdentityRow, p.sub, with_for_update=True)
    if row is not None and row.status == "verified":
        return IdentityOut(status="verified")
    provider = _provider(request)
    session_id, secret = await provider.verification_session(p.sub)
    if row is None:
        row = IdentityRow(person_id=p.sub, session_id=session_id, status="pending", updated_at=_now())
        session.add(row)
    else:
        row.session_id, row.status, row.updated_at = session_id, "pending", _now()
    await session.flush()
    if provider.authorises_immediately:  # the fake: verified at once
        await _verified(request, session, row)
        return IdentityOut(status="verified")
    return IdentityOut(status="pending", client_secret=secret)


@router.get("/identity", response_model=IdentityOut)
async def identity_status(session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> IdentityOut:
    row = await session.get(IdentityRow, p.sub)
    return IdentityOut(status=row.status if row else "none")


# --- internal: a person's data export --------------------------------------------------------


@internal.get("/people/{person}/open")
async def open_payouts(person: str, session: AsyncSession = Tx) -> dict:
    """Before an account is deleted: money captured for them and not paid out
    yet (a completed booking waiting for its payout, or one held)."""
    n = (
        await session.execute(
            select(func.count()).where(PaymentRow.owner_id == person, PaymentRow.status == "captured")
        )
    ).scalar_one()
    return {"pendingPayouts": n}


@internal.get("/people/{person}/export")
async def export_person(person: str, session: AsyncSession = Tx) -> dict:
    """What payments holds about them (GDPR art. 15/20). Card details stay
    with Stripe and are never here."""
    from .tables import InvoiceRow

    account = await session.get(ConnectAccountRow, person)
    identity = await session.get(IdentityRow, person)
    invoices = (await session.execute(select(InvoiceRow).where(InvoiceRow.owner_id == person))).scalars()
    paid = (
        await session.execute(
            select(PaymentRow)
            .where((PaymentRow.requester_id == person) | (PaymentRow.owner_id == person))
            .limit(10_000)
        )
    ).scalars()
    return {
        "payoutAccount": {"connected": True, "payoutsEnabled": account.payouts_enabled} if account else None,
        "identity": {
            "status": identity.status,
            "verifiedAt": identity.verified_at.isoformat() if identity.verified_at else None,
        }
        if identity
        else None,
        "invoices": [
            {"number": i.number, "bookingId": i.booking_id, "gross": i.gross, "issuedAt": i.issued_at.isoformat()}
            for i in invoices
        ],
        "payments": [
            {"bookingId": p.booking_id, "amount": p.amount, "currency": p.currency, "status": p.status} for p in paid
        ],
    }


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
        q = select(PaymentRow).where(PaymentRow.intent_id == obj["id"]).with_for_update()
        row = (await session.execute(q)).scalar_one_or_none()
        if row is not None:
            await _authorised(request, session, row)
    elif kind == "account.updated":
        q = select(ConnectAccountRow).where(ConnectAccountRow.account_id == obj["id"]).with_for_update()
        account = (await session.execute(q)).scalar_one_or_none()
        if account is not None:
            # Stripe does not deliver webhooks in order: ask for the current
            # state rather than trusting this event's copy of it.
            status = await _provider(request).account_status(account.account_id)
            await _update_account(request, session, account, status.payouts_enabled, status.details_submitted)
    elif kind.startswith("identity.verification_session."):
        pid = (obj.get("metadata") or {}).get("personId")
        row = await session.get(IdentityRow, pid, with_for_update=True) if pid else None
        if row is not None:
            if kind.endswith(".verified"):
                await _verified(request, session, row)
            elif kind.endswith(".requires_input"):
                row.status = "requires_input"
            row.updated_at = _now()
    elif kind == "charge.dispute.created":
        q = select(PaymentRow).where(PaymentRow.charge_id == obj["charge"]).with_for_update()
        row = (await session.execute(q)).scalar_one_or_none()
        if row is not None and row.chargeback_at is None:
            row.chargeback_at = _now()
            row.updated_at = row.chargeback_at
            # The alarm on this line (Terraform: chargebacks) pages support.
            log.error("CHARGEBACK on booking %s (dispute %s); payout held", row.booking_id, obj.get("id"))
    else:
        log.info("ignoring stripe event %s", kind)
    return {"received": True}
