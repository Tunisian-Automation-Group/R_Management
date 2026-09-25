"""The two sweeps: lapse what nobody answered, complete what nobody closed."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import FastAPI

from cappy_common.events import jittered

from .repository import BookingRepository
from .settings import Settings

BATCH = 100


async def sweep_once(app: FastAPI) -> int:
    """One pass. Returns how many bookings it moved."""
    settings: Settings = app.state.settings
    moved = 0
    for pick, to in (
        (lambda r, now: r.lapsed(now, BATCH), "expired"),
        (lambda r, now: r.finished(now, settings.auto_complete_after, BATCH), "completed"),
    ):
        while True:
            async with app.state.db.transaction() as s:
                repo = BookingRepository(s, app.state.outbox)
                now = datetime.now(UTC)
                rows = await pick(repo, now)
                for row in rows:
                    await repo.move(row, to, "system", now, expires_at=None)
            moved += len(rows)
            if len(rows) < BATCH:
                break
    # Blind reviews whose window closed with only one side in: publish it.
    while True:
        async with app.state.db.transaction() as s:
            repo = BookingRepository(s, app.state.outbox)
            now = datetime.now(UTC)
            due = await repo.reviews_due(now, BATCH)
            for row in due:
                await repo.publish_reviews(row, now)
        moved += len(due)
        if len(due) < BATCH:
            break
    if moved:
        app.state.relay.wake()
    return moved


async def sweep(app: FastAPI) -> None:
    await sweep_once(app)
    await asyncio.sleep(jittered(app.state.settings.sweep_seconds))
