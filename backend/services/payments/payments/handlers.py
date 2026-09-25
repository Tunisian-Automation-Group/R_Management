"""Money follows the booking: every status change it announces maps to at
most one Stripe call.

    accepted                      -> capture
    declined, cancelled, expired,
    payment_failed (not captured) -> cancel the hold
    cancelled after capture       -> refund in full
    completed                     -> transfer the owner's share

The Stripe call happens before our row is updated. If the process dies in
between, the event is redelivered, the call repeats with the same
idempotency key, Stripe returns the first result, and the row catches up.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

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

from .provider import Declined, Provider
from .tables import OUTBOX, ConnectAccountRow, PaymentRow

log = logging.getLogger(__name__)

RELEASE = {"declined", "cancelled", "expired", "payment_failed"}


class NotReady(RuntimeError):
    """Raised to leave an event on the queue: it is retried, and dead-lettered
    (and alarmed on) if it never becomes possible."""


def handlers(provider: Provider, service_name: str) -> dict[str, Handler]:
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
        elif to == "cancelled" and row.status == "captured":
            row.refund_id = await provider.refund(row.intent_id, row.booking_id)
            row.status = "refunded"
            await outbox.add(session, PAYMENT_REFUNDED, {**facts, "amount": row.amount, "currency": row.currency})
        elif to == "completed" and row.status == "captured" and row.chargeback_at is not None:
            log.error("CHARGEBACK hold: not paying out booking %s", row.booking_id)
            return
        elif to == "completed" and row.status == "captured":
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
        elif to == "completed" and row.status in ("created", "authorised"):
            # Completed without an accept (auto-completion of an accepted
            # booking always follows a capture): out of order; try again later.
            raise NotReady(f"booking {row.booking_id} completed before its payment was captured")
        else:
            return
        row.updated_at = now

    async def on_profile_deleted(session: AsyncSession, event: Event) -> None:
        """Their payout link goes; the Stripe account itself stays with Stripe,
        which keeps what financial regulation requires."""
        account = await session.get(ConnectAccountRow, event.data["ownerId"])
        if account is not None:
            await session.delete(account)

    return {BOOKING_STATUS_CHANGED: on_status_changed, PROFILE_DELETED: on_profile_deleted}
