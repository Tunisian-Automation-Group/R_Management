"""Reconciliation: our records and Stripe's, made to agree.

Webhooks are at-least-once but not certain: an endpoint that was down for
longer than Stripe keeps retrying, or a bug, loses one. So every few minutes
the intents that have waited suspiciously long are looked up at Stripe
directly and brought in line (research: Stripe webhooks, Airbnb's payments).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import select

from cappy_common.events import PAYMENT_AUTHORISED, jittered

from .tables import PaymentRow

log = logging.getLogger(__name__)

# A card step normally finishes in a minute; the booking lapses after 30.
STUCK_AFTER = timedelta(minutes=10)
BATCH = 50


async def reconcile_once(app: FastAPI) -> int:
    """Returns how many payments it corrected."""
    provider = app.state.provider
    fixed = 0
    async with app.state.db.transaction() as s:
        q = (
            select(PaymentRow)
            .where(PaymentRow.status == "created", PaymentRow.created_at < datetime.now(UTC) - STUCK_AFTER)
            .order_by(PaymentRow.created_at)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        )
        for row in (await s.execute(q)).scalars():
            try:
                status = await provider.intent_status(row.intent_id)
            except Exception as e:  # noqa: BLE001 - try again next round
                log.warning("could not reconcile %s: %s", row.booking_id, e)
                continue
            if status == "requires_capture":
                # Authorised, and we never heard: tell booking now.
                log.warning("reconciled %s: authorised at Stripe, the webhook never arrived", row.booking_id)
                row.status, row.updated_at = "authorised", datetime.now(UTC)
                await app.state.outbox.add(s, PAYMENT_AUTHORISED, {"bookingId": row.booking_id})
                fixed += 1
            elif status == "canceled":
                row.status, row.updated_at = "cancelled", datetime.now(UTC)
                fixed += 1
    if fixed:
        app.state.relay.wake()
    return fixed


async def purge_invoices_once(app: FastAPI, now: datetime | None = None) -> int:
    """Invoices past their retention period go (GDPR Art. 5(1)(e), D-9): the
    period runs from the end of the year of issue, so an invoice of 2026 kept
    8 years may go from 1 January 2035. Credit notes go with the same rule."""
    from sqlalchemy import delete

    from .invoices import issuer_of
    from .tables import CreditNoteRow, InvoiceRow

    issuer = issuer_of(app.state.settings)
    year = (now or datetime.now(UTC)).year
    first_kept = datetime(year - issuer.retention_years, 1, 1, tzinfo=UTC)
    async with app.state.db.transaction() as s:
        await s.execute(delete(CreditNoteRow).where(CreditNoteRow.issued_at < first_kept))
        r = await s.execute(delete(InvoiceRow).where(InvoiceRow.issued_at < first_kept))
    if r.rowcount:
        log.info("purged %d invoices issued before %s", r.rowcount, first_kept.date())
    return r.rowcount or 0


async def reconcile(app: FastAPI) -> None:
    await reconcile_once(app)
    await asyncio.sleep(jittered(300))


async def purge_invoices(app: FastAPI) -> None:
    await purge_invoices_once(app)
    await asyncio.sleep(jittered(86_400))
