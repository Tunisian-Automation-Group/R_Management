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


async def reconcile(app: FastAPI) -> None:
    await reconcile_once(app)
    await asyncio.sleep(jittered(300))
