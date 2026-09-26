"""Money follows the booking: every status change it announces maps to at
most one Stripe call.

    accepted                      -> capture
    declined, cancelled, expired,
    payment_failed (not captured) -> cancel the hold
    cancelled after capture       -> refund (all, or what the policy gives back)
    completed                     -> transfer the owner's share
    completed with refundAmount   -> refund that part, pay the owner their
                                     share of the rest (a dispute settled
                                     with a partial refund, H-6 and S-21)

The Stripe call happens before our row is updated. If the process dies in
between, the event is redelivered, the call repeats with the same
idempotency key, Stripe returns the first result, and the row catches up.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import (
    BOOKING_STATUS_CHANGED,
    PAYMENT_CAPTURED,
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYOUT_SENT,
    PROFILE_DELETED,
    Event,
    Handler,
    Outbox,
)

from .identity import IdentityProvider
from .invoices import GERMANY, Issuer, issue
from .provider import Declined, Provider
from .tables import OUTBOX, ConnectAccountRow, IdentityRow, PaymentRow

log = logging.getLogger(__name__)

RELEASE = {"declined", "cancelled", "expired", "payment_failed"}


class NotReady(RuntimeError):
    """Raised to leave an event on the queue: it is retried, and dead-lettered
    (and alarmed on) if it never becomes possible."""


async def _address(provider: Provider, account_id: str) -> str | None:
    """Best effort: an invoice is never held up by the provider being slow;
    it carries a business address instead, or none (valid under § 33 UStDV)."""
    try:
        return await provider.account_address(account_id)
    except Exception as e:  # noqa: BLE001
        log.warning("no verified address for %s: %s", account_id, e)
        return None


def handlers(
    provider: Provider,
    service_name: str,
    payouts_on: bool = True,
    issuer: Issuer = GERMANY,
    identity: IdentityProvider | None = None,
) -> dict[str, Handler]:
    outbox = Outbox(OUTBOX, service_name)

    async def on_status_changed(session: AsyncSession, event: Event) -> None:
        d = event.data
        to = d["to"]
        row = await session.get(PaymentRow, d["bookingId"], with_for_update=True)
        if row is None:
            # A booking whose intent was never created (payments was down).
            return
        now = datetime.now(UTC)
        facts = {"bookingId": row.booking_id, "ownerId": row.owner_id, "requesterId": row.requester_id}

        if to == "accepted" and row.status in ("created", "authorised"):
            try:
                row.charge_id = await provider.capture(row.intent_id, row.booking_id)
            except Declined as e:
                # Nothing was taken; the booking cannot go ahead. Booking moves
                # it to payment_failed, which releases the window and tells both.
                log.warning("capture declined for %s: %s", row.booking_id, e)
                row.status = "failed"
                row.updated_at = now
                await outbox.add(session, PAYMENT_FAILED, {**facts, "stage": "capture"})
                return
            row.status = "captured"
            await outbox.add(session, PAYMENT_CAPTURED, {**facts, "amount": row.amount, "currency": row.currency})
        elif to in RELEASE and row.status in ("created", "authorised"):
            await provider.cancel(row.intent_id, row.booking_id)
            row.status = "cancelled"
        elif row.status == "captured" and (to == "cancelled" or (to == "completed" and d.get("refundAmount"))):
            # The cancellation policy decided the refund (booking/cancellation.py),
            # or a dispute was settled with part of the price going back.
            refund = d.get("refundAmount")
            refund = row.amount if refund is None else max(0, min(row.amount, int(refund)))
            if refund > 0:
                row.refund_id = await provider.refund(
                    row.intent_id, row.booking_id, None if refund == row.amount else refund
                )
                await outbox.add(session, PAYMENT_REFUNDED, {**facts, "amount": refund, "currency": row.currency})
            kept = row.amount - refund
            owner_part = kept * row.owner_net // row.amount if row.amount else 0
            row.status = "refunded"
            if owner_part > 0 and (not payouts_on or row.chargeback_at is not None):
                # Refund done; the owner's share waits like any payout would.
                raise NotReady(f"payout for {row.booking_id} held (payouts off or a chargeback)")
            if owner_part > 0:
                # A late cancellation: the owner keeps their share of what was kept.
                account = await session.get(ConnectAccountRow, row.owner_id)
                if account is None or not row.charge_id:
                    raise NotReady(f"cannot pay out {row.booking_id}: no connected account or charge")
                row.transfer_id = await provider.transfer(
                    booking_id=row.booking_id,
                    amount=owner_part,
                    currency=row.currency,
                    account_id=account.account_id,
                    charge_id=row.charge_id,
                )
                await outbox.add(session, PAYOUT_SENT, {**facts, "amount": owner_part, "currency": row.currency})
                await issue(
                    session,
                    booking_id=row.booking_id,
                    owner_id=row.owner_id,
                    fee_gross=kept - owner_part,
                    currency=row.currency,
                    about=d,
                    issuer=issuer,
                    verified_address=await _address(provider, account.account_id),
                )
        elif to == "completed" and row.status == "captured" and row.chargeback_at is not None:
            log.error("CHARGEBACK hold: not paying out booking %s", row.booking_id)
            return
        elif to == "completed" and row.status == "captured":
            if not payouts_on:
                raise NotReady(f"payouts are switched off; {row.booking_id} waits")
            account = await session.get(ConnectAccountRow, row.owner_id)
            if account is None or not row.charge_id:
                raise NotReady(f"cannot pay out {row.booking_id}: no connected account or charge")
            row.transfer_id = await provider.transfer(
                booking_id=row.booking_id,
                amount=row.owner_net,
                currency=row.currency,
                account_id=account.account_id,
                charge_id=row.charge_id,
            )
            row.status = "transferred"
            await outbox.add(session, PAYOUT_SENT, {**facts, "amount": row.owner_net, "currency": row.currency})
            await issue(
                session,
                booking_id=row.booking_id,
                owner_id=row.owner_id,
                fee_gross=row.amount - row.owner_net,
                currency=row.currency,
                about=d,
                issuer=issuer,
                verified_address=await _address(provider, account.account_id),
            )
        elif to == "completed" and row.status in ("created", "authorised"):
            # Completed without an accept (auto-completion of an accepted
            # booking always follows a capture): out of order; try again later.
            raise NotReady(f"booking {row.booking_id} completed before its payment was captured")
        else:
            return
        row.updated_at = now

    async def on_profile_deleted(session: AsyncSession, event: Event) -> None:
        """Their payout link goes; the Stripe account itself stays with Stripe,
        which keeps what financial regulation requires. The ID document and
        selfie are erased at the provider (D-6); the card fingerprint goes
        (booking keeps a suspended person's for fraud prevention, S-17)."""
        person = event.data["ownerId"]
        account = await session.get(ConnectAccountRow, person)
        if account is not None:
            await session.delete(account)
        row = await session.get(IdentityRow, person)
        if row is not None:
            if identity is not None:
                await identity.redact(row.session_id)
            await session.delete(row)
        await session.execute(
            update(PaymentRow)
            .where((PaymentRow.requester_id == person) | (PaymentRow.owner_id == person))
            .values(card_fingerprint=None)
        )

    return {BOOKING_STATUS_CHANGED: on_status_changed, PROFILE_DELETED: on_profile_deleted}
