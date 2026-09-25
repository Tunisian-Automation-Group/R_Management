"""Per-person guards a service with a database keeps: sessions revoked before
their tokens ran out (P-24), and counters for per-person rate limits (P-12).

Revocation: access tokens are verified locally, so a token stays valid until
it expires (15 minutes) even after "sign out everywhere" or a deleted account.
Each service therefore records, per person, "tokens issued before this moment
no longer count" when the event arrives, and checks it on every signed-in
request through a short in-process cache. Every replica reads the same row in
its service's database, so it does not matter which replica took the event.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, Index, Integer, MetaData, String, Table, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Database, UtcDateTime
from .errors import RateLimited
from .events import PERSON_SIGNED_OUT, PROFILE_DELETED, Event, Handler

REVOKING = (PERSON_SIGNED_OUT, PROFILE_DELETED)


def revocation_table(metadata: MetaData) -> Table:
    return Table(
        "revoked_sessions",
        metadata,
        Column("sub", String(64), primary_key=True),
        Column("not_before", UtcDateTime, nullable=False),
    )


def rate_table(metadata: MetaData) -> Table:
    t = Table(
        "rate_hits",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("key", String(120), nullable=False),
        Column("at", UtcDateTime, nullable=False),
    )
    Index("ix_rate_hits_key_at", t.c.key, t.c.at)
    return t


async def revoke(session: AsyncSession, table: Table, sub: str, at: datetime) -> None:
    """Tokens of ``sub`` issued before ``at`` stop counting. Only ever moves later."""
    current = (await session.execute(select(table.c.not_before).where(table.c.sub == sub))).scalar_one_or_none()
    if current is None:
        await session.execute(insert(table).values(sub=sub, not_before=at))
    elif current < at:
        await session.execute(update(table).where(table.c.sub == sub).values(not_before=at))


def with_revocation(
    handlers: dict[str, Handler], table: Table, forget: Callable[[str], None] = lambda _sub: None
) -> dict[str, Handler]:
    """The service's handlers, plus recording the revocation on the events that
    end sessions (before whatever the service itself does with them).
    ``forget`` drops this replica's cached answer for the person at once."""
    out = dict(handlers)
    for kind in REVOKING:
        own = handlers.get(kind)

        async def handle(session: AsyncSession, event: Event, own: Handler | None = own) -> None:
            person = event.data.get("personId") or event.data.get("ownerId")
            if person:
                await revoke(session, table, person, datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00")))
                forget(person)
            if own is not None:
                await own(session, event)

        out[kind] = handle
    return out


class Revocations:
    """``not_before`` per person, cached briefly. ponytail: a plain dict with a
    TTL, cleared wholesale when it grows large; one indexed read per person
    per ``ttl`` per replica."""

    def __init__(self, db: Database, table: Table, ttl: float = 30.0) -> None:
        self._db, self._table, self._ttl = db, table, ttl
        self._cache: dict[str, tuple[float, float | None]] = {}

    async def not_before(self, sub: str) -> float | None:
        hit = self._cache.get(sub)
        now = time.monotonic()
        if hit and hit[0] > now:
            return hit[1]
        async with self._db.session() as s:
            at = (
                await s.execute(select(self._table.c.not_before).where(self._table.c.sub == sub))
            ).scalar_one_or_none()
        value = at.timestamp() if at else None
        if len(self._cache) > 50_000:
            self._cache.clear()
        self._cache[sub] = (now + self._ttl, value)
        return value

    def forget(self, sub: str) -> None:
        """This replica revoked it itself: no need to wait for the cache."""
        self._cache.pop(sub, None)


async def hit(session: AsyncSession, table: Table, key: str, *, limit: int, window: timedelta, message: str) -> None:
    """Counts one use of ``key``; past ``limit`` within ``window``, a 429."""
    now = datetime.now(UTC)
    since = now - window
    await session.execute(delete(table).where(table.c.key == key, table.c.at < since))
    used = (await session.execute(select(func.count()).where(table.c.key == key, table.c.at >= since))).scalar_one()
    if used >= limit:
        raise RateLimited(message)
    await session.execute(insert(table).values(key=key, at=now))
