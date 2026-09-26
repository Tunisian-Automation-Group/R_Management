"""Notifications housekeeping: the bell keeps a year, not for ever."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import delete

from cappy_common.events import jittered

from .tables import InboxRow


async def expire_inbox_once(app: FastAPI, now: datetime | None = None) -> int:
    """Inbox items older than the retention period go (docs/retention.md):
    the emails and pushes they repeat were sent long ago."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=app.state.settings.inbox_retention_days)
    async with app.state.db.transaction() as s:
        return (await s.execute(delete(InboxRow).where(InboxRow.at < cutoff))).rowcount or 0


async def expire_inbox(app: FastAPI) -> None:
    await expire_inbox_once(app)
    await asyncio.sleep(jittered(3600))
