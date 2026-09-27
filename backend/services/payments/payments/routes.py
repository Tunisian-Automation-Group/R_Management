"""Payments: the intent behind every booking, owner onboarding, Stripe's webhook."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from fastapi import Depends, Request
from pydantic import Field
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_admin, require_internal, require_principal
from cappy_common.db import insert_or_ignore
from cappy_common.errors import Conflict, Invalid, NotFound, Unavailable
from cappy_common.events import IDENTITY_VERIFIED, PAYMENT_AUTHORISED, PAYOUTS_READY, STAFF_ACTION
from cappy_common.markets import markets
from cappy_common.models import CamelModel, Iso
from cappy_common.runtime import Tx
from cappy_common.timeutil import iso_from_datetime

from . import invoices
from .handlers import pay_out
from .identity import IdentityResult, stripe_result
from .provider import FAKE_ACCOUNT_PREFIX, Provider
from .tables import PROCESSED, ConnectAccountRow, IdentityRow, PaymentRow

log = logging.getLogger(__name__)
router = ApiRouter(prefix="/payments")
internal = ApiRouter(prefix="/internal", dependencies=[Depends(require_internal)])
admin = ApiRouter(prefix="/admin/payments")


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
    # ISO 4217; stored and answered uppercase, lowercased only for Stripe.
    currency: str = Field(pattern="^[A-Za-z]{3}$")


class IntentOut(CamelModel):
    client_secret: str
    intent_id: str


class Config(CamelModel):
    provider: str
    publishable_key: str | None = None
    # Which ID-check UI the app shows (F-1): "stripe" = Stripe.js verifyIdentity.
    identity_provider: str


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
            currency=body.currency.upper(),
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
            currency=body.currency.upper(),
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
    return Config(
        provider=_provider(request).name,
        publishable_key=s.stripe_publishable_key or None,
        identity_provider=request.app.state.identity.name,
    )


@router.get("/bookings/{booking_id}", response_model=PaymentView)
async def payment_for_booking(
    booking_id: str, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> PaymentView:
    row = await session.get(PaymentRow, booking_id)
    if row is None or p.sub not in (row.requester_id, row.owner_id):
        raise NotFound(f"no payment for booking {booking_id}")
    return PaymentView(booking_id=row.booking_id, status=row.status, amount=row.amount, currency=row.currency)


class OnboardingIn(CamelModel):
    # Where the owner lives (their profile's country). Stripe fixes an
    # account's country at creation; a later change needs a new account.
    country: str = Field(default="DE", pattern="^[A-Z]{2}$")


@router.post("/connect/onboarding", response_model=Onboarding)
async def onboarding(
    request: Request,
    body: OnboardingIn | None = None,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_principal),
):
    """A Stripe-hosted page where an owner gives Stripe their identity and bank
    details. We never see either."""
    provider = _provider(request)
    base = request.app.state.settings.web_base_url.rstrip("/")
    country = (body or OnboardingIn()).country
    # Owners are paid where Cappy is open (markets.json, M-2).
    if not (m := markets().get(country)) or not m.live:
        raise Invalid(f"payouts are not available in {country} yet", code="country_unsupported")
    account = await session.get(ConnectAccountRow, p.sub)
    if account is None:
        account_id = await provider.create_account(p.sub, country)
        account = ConnectAccountRow(owner_id=p.sub, account_id=account_id, updated_at=_now())
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
    # none | pending | requires_input | failed | verified
    status: str
    client_secret: str | None = None
    # Hosted flows (another provider) open this instead of using a client secret.
    url: str | None = None


async def _verified(request: Request, session: AsyncSession, row: IdentityRow) -> None:
    if row.status != "verified":
        row.status, row.verified_at = "verified", _now()
        await request.app.state.outbox.add(session, IDENTITY_VERIFIED, {"personId": row.person_id})


# The wording the app shows next to the consent box. A new wording is a new
# version, so each stored consent says exactly what was agreed to.
IDENTITY_CONSENT_VERSION = "identity-2026-09"


class IdentityStart(CamelModel):
    consent: bool = False


@router.post("/identity/session", response_model=IdentityOut)
async def identity_session(
    request: Request,
    body: IdentityStart | None = None,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_principal),
):
    """Starts (or continues) verifying who the caller is, once they have agreed
    to the ID and selfie check (P-18). The app hands the client secret to
    Stripe.js (verifyIdentity); the outcome comes by webhook."""
    row = await session.get(IdentityRow, p.sub, with_for_update=True)
    if row is not None and row.status == "verified":
        return IdentityOut(status="verified")
    if body is None or not body.consent:
        raise Invalid("agree to the identity check first (consent: true)", code="consent_required")
    identity = request.app.state.identity
    started = await identity.start_session(p.sub)
    now = _now()
    if row is None:
        row = IdentityRow(person_id=p.sub, session_id=started.session_id, status="pending", updated_at=now)
        session.add(row)
    else:
        row.session_id, row.status, row.updated_at = started.session_id, "pending", now
    row.consent_at, row.consent_version = now, IDENTITY_CONSENT_VERSION
    await session.flush()
    if identity.verifies_immediately:  # the fake: verified at once
        await _verified(request, session, row)
        return IdentityOut(status="verified")
    return IdentityOut(status="pending", client_secret=started.client_secret, url=started.url)


async def _identity_result(request: Request, session: AsyncSession, result: IdentityResult) -> None:
    """A provider's verdict, applied once and only to the session we started
    for that person (P-28): not an older one, not one made elsewhere carrying
    their id in its metadata."""
    row = await session.get(IdentityRow, result.person_id, with_for_update=True) if result.person_id else None
    if row is None or row.session_id != result.session_id:
        log.warning(
            "identity result for session %s is not %s's current one; ignored", result.session_id, result.person_id
        )
        return
    if result.status == "verified":
        await _verified(request, session, row)
    elif row.status != "verified":
        row.status = "requires_input" if result.status == "needs_input" else "failed"
    row.updated_at = _now()


@router.get("/identity", response_model=IdentityOut)
async def identity_status(session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> IdentityOut:
    row = await session.get(IdentityRow, p.sub)
    return IdentityOut(status=row.status if row else "none")


class PaymentState(CamelModel):
    booking_id: str
    status: str
    amount: int
    owner_net: int
    currency: str
    # Amounts in minor units of `currency`, not flags: what was charged, what
    # went back to the renter, what reached the owner.
    captured: int
    refunded: int
    paid_out: int
    chargeback_at: Iso | None = None
    updated_at: Iso


@internal.get("/bookings/{booking_id}/payment", response_model=PaymentState)
async def payment_state(booking_id: str, session: AsyncSession = Tx) -> PaymentState:
    """For the staff case view (H-9): where the money of a booking stands."""
    row = await session.get(PaymentRow, booking_id)
    if row is None:
        raise NotFound(f"no payment for booking {booking_id}")
    return PaymentState(
        booking_id=row.booking_id,
        status=row.status,
        amount=row.amount,
        owner_net=row.owner_net,
        currency=row.currency,
        captured=row.amount if row.charge_id else 0,
        refunded=row.refunded_amount,
        paid_out=row.paid_out_amount,
        chargeback_at=iso_from_datetime(row.chargeback_at) if row.chargeback_at else None,
        updated_at=iso_from_datetime(row.updated_at),
    )


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
    from .tables import CreditNoteRow, InvoiceRow

    account = await session.get(ConnectAccountRow, person)
    credits = (await session.execute(select(CreditNoteRow).where(CreditNoteRow.owner_id == person))).scalars()
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
            # The consent they gave before the check (P-18): when, to which text.
            "consentAt": identity.consent_at.isoformat() if identity.consent_at else None,
            "consentVersion": identity.consent_version,
        }
        if identity
        else None,
        "invoices": [
            {
                "number": i.number,
                "bookingId": i.booking_id,
                "gross": i.gross,
                "currency": i.currency,
                "issuedAt": i.issued_at.isoformat(),
                "recipient": {"name": i.recipient_name, "address": i.recipient_address, "vatId": i.recipient_vat_id},
            }
            for i in invoices
        ],
        "creditNotes": [
            {
                "number": c.number,
                "corrects": c.corrects,
                "gross": c.gross,
                "currency": c.currency,
                "reason": c.reason,
                "issuedAt": c.issued_at.isoformat(),
            }
            for c in credits
        ],
        # D-10: what was charged, refunded and paid out, and the card's
        # fingerprint (never the card: that stays with Stripe).
        "payments": [
            {
                "bookingId": p.booking_id,
                "amount": p.amount,
                "currency": p.currency,
                "status": p.status,
                "charged": bool(p.charge_id),
                "refunded": bool(p.refund_id),
                "paidOut": bool(p.transfer_id),
                "cardFingerprint": p.card_fingerprint if p.requester_id == person else None,
            }
            for p in paid
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
    elif (result := stripe_result(event)) is not None:
        # Stripe sends ID-check events to this same endpoint.
        await _identity_result(request, session, result)
    elif kind.startswith("charge.dispute."):
        await _chargeback(request, session, kind, obj)
    else:
        log.info("ignoring stripe event %s", kind)
    return {"received": True}


# Won, or a warning the bank closed: the hold ends. Lost: the money went back
# to the card holder, and with separate charges and transfers the platform
# carries it unless the owner's payout is recovered.
DISPUTE_RELEASED = ("won", "warning_closed")


async def _chargeback(request: Request, session: AsyncSession, kind: str, obj: dict) -> None:
    """Every charge.dispute.* event (R2-3, runbook "A chargeback"). Stripe
    sends them out of order, so each one records the dispute's own status."""
    q = select(PaymentRow).where(PaymentRow.charge_id == obj.get("charge")).with_for_update()
    row = (await session.execute(q)).scalar_one_or_none()
    if row is None:
        return
    now = _now()
    row.dispute_id = obj.get("id") or row.dispute_id
    row.dispute_status = (obj.get("status") or row.dispute_status or "")[:30] or None
    row.dispute_reason = (obj.get("reason") or row.dispute_reason or "")[:40] or None
    due = (obj.get("evidence_details") or {}).get("due_by")
    if due:
        row.dispute_due_at = datetime.fromtimestamp(int(due), UTC)
    row.updated_at = now
    status = obj.get("status")
    if kind == "charge.dispute.closed" or status in (*DISPUTE_RELEASED, "lost"):
        if status in DISPUTE_RELEASED and row.chargeback_at is not None:
            row.chargeback_at = None
            log.warning("chargeback on %s ended (%s): hold released", row.booking_id, status)
            if row.held_payout and row.status == "captured":
                held, row.held_payout = json.loads(row.held_payout), None
                settings = request.app.state.settings
                await pay_out(
                    session, _provider(request), request.app.state.outbox, invoices.issuer_of(settings), row, held
                )
        elif status == "lost" and row.status != "charged_back":
            await _chargeback_lost(request, row)
        return
    if row.chargeback_at is None:
        row.chargeback_at = now
        # The alarm on this line (Terraform: chargebacks) opens a ticket.
        log.error("CHARGEBACK on booking %s (dispute %s); payout held", row.booking_id, row.dispute_id)


async def _chargeback_lost(request: Request, row: PaymentRow) -> None:
    """The card holder has the money back. An owner already paid gives their
    share back through a transfer reversal; what their balance cannot cover
    is recorded as owed and taken from the next payout, per the terms."""
    row.status = "charged_back"
    row.held_payout = None
    if row.transfer_id and row.paid_out_amount > row.recovered_amount:
        due = row.paid_out_amount - row.recovered_amount
        try:
            await _provider(request).reverse_transfer(row.transfer_id, due, row.booking_id)
            row.recovered_amount += due
        except Exception as e:  # noqa: BLE001 - any provider failure means we are still owed
            row.owner_owes = due
            log.error("CHARGEBACK LOST on %s: %s could not be recovered from the owner: %s", row.booking_id, due, e)
            return
    log.error("CHARGEBACK LOST on booking %s: recovered %s", row.booking_id, row.recovered_amount)


# --- staff: chargebacks ----------------------------------------------------------------


class Chargeback(CamelModel):
    """One row of the staff chargebacks screen (R2-24): what was disputed,
    why, by when evidence is due, and where the money stands."""

    booking_id: str
    title: str | None
    dispute_id: str | None
    status: str | None
    reason: str | None
    due_by: Iso | None
    amount: int
    currency: str
    paid_out: int
    recovered: int
    owner_owes: int


@admin.get("/chargebacks", response_model=list[Chargeback])
async def chargebacks(session: AsyncSession = Tx, staff: Principal = Depends(require_admin)) -> list[Chargeback]:
    """Open chargebacks first, soonest evidence deadline first; then the lost
    ones still owed by an owner."""
    rows = (
        await session.execute(
            select(PaymentRow)
            .where(PaymentRow.dispute_id.is_not(None))
            .where(PaymentRow.chargeback_at.is_not(None) | (PaymentRow.owner_owes > 0))
            .order_by(PaymentRow.dispute_due_at.asc().nulls_last())
            .limit(200)
        )
    ).scalars()
    return [
        Chargeback(
            booking_id=r.booking_id,
            title=r.title,
            dispute_id=r.dispute_id,
            status=r.dispute_status,
            reason=r.dispute_reason,
            due_by=iso_from_datetime(r.dispute_due_at) if r.dispute_due_at else None,
            amount=r.amount,
            currency=r.currency,
            paid_out=r.paid_out_amount,
            recovered=r.recovered_amount,
            owner_owes=r.owner_owes,
        )
        for r in rows
    ]


class EvidenceIn(CamelModel):
    text: str = Field(min_length=20, max_length=20000)
    links: list[str] = Field(default_factory=list, max_length=20)


@admin.post("/{booking_id}/dispute-evidence", status_code=204)
async def dispute_evidence(
    booking_id: str,
    body: EvidenceIn,
    request: Request,
    session: AsyncSession = Tx,
    staff: Principal = Depends(require_admin),
) -> None:
    """Staff answer a chargeback with the booking's trail: what happened, the
    hand-over photos, the messages (runbook "A chargeback")."""
    row = await session.get(PaymentRow, booking_id, with_for_update=True)
    if row is None or not row.dispute_id:
        raise NotFound("no chargeback on this booking")
    if row.chargeback_at is None:
        raise Conflict("this chargeback is closed")
    text = body.text + ("\n\nEvidence:\n" + "\n".join(body.links) if body.links else "")
    await _provider(request).submit_dispute_evidence(row.dispute_id, text)
    row.dispute_status = "under_review"
    row.updated_at = _now()
    await request.app.state.outbox.add(
        session,
        STAFF_ACTION,
        {
            "actorId": staff.sub,
            "action": "submit_chargeback_evidence",
            "targetType": "booking",
            "targetId": booking_id,
            "personId": row.owner_id,
            "reason": "",
            "details": {"bookingId": booking_id, "currency": row.currency, "amount": row.amount},
            "service": "payments",
            "at": iso_from_datetime(row.updated_at),
        },
    )


@router.post("/webhooks/identity", status_code=200)
async def identity_webhook(request: Request, session: AsyncSession = Tx) -> dict:
    """For an ID-check provider with its own webhook (F-1). Verified by the
    provider class; handled once per session and status."""
    result = request.app.state.identity.parse_webhook(await request.body(), dict(request.headers))
    if result is None:
        return {"received": True}
    key = f"idv:{result.session_id}:{result.status}"[:40]
    try:
        async with session.begin_nested():
            await session.execute(insert(PROCESSED).values(event_id=key, type="identity", processed_at=_now()))
    except IntegrityError:
        return {"received": True, "duplicate": True}
    await _identity_result(request, session, result)
    return {"received": True}
