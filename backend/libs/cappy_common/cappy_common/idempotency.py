"""``Idempotency-Key`` for POSTs that create something (a listing, a message,
a review, a report): a retry after a lost answer gets the first answer back
instead of a second copy. Same key with a different body is a 422.

The key and the answer are written in the same transaction as the thing
created, so either both exist or neither does. Two copies of the same request
racing each other: the second waits on the key's primary key, then gets 409
and, retried, the first one's answer.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import Header, Request
from pydantic import BaseModel
from sqlalchemy import Column, MetaData, String, Table, delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .db import JsonType, UtcDateTime
from .errors import Conflict, Invalid

# The header, for a route's signature: ``key: str | None = IdempotencyKey``.
IdempotencyKey = Header(default=None, alias="Idempotency-Key", max_length=80)


# A retry comes within minutes; a day covers a phone that was off overnight
# (Stripe keeps its keys 24 h too). Older answers are deleted hourly (D-4).
KEEP = timedelta(hours=24)


def idempotency_table(metadata: MetaData) -> Table:
    return Table(
        "idempotency_keys",
        metadata,
        Column("principal", String(64), primary_key=True),
        Column("key", String(80), primary_key=True),
        Column("request_hash", String(64), nullable=False),
        Column("response", JsonType, nullable=False),
        Column("created_at", UtcDateTime, nullable=False),
    )


def fingerprint(request: Request, body: BaseModel | None = None) -> str:
    """The route and the body: the same key on another route is another request."""
    raw = request.method + " " + request.url.path + " " + (body.model_dump_json(by_alias=True) if body else "")
    return hashlib.sha256(raw.encode()).hexdigest()


async def replayed(session: AsyncSession, table: Table, who: str, key: str | None, fp: str) -> dict | None:
    """The first answer to this key, if there was one."""
    if not key:
        return None
    row = (
        await session.execute(
            select(table.c.request_hash, table.c.response).where(table.c.principal == who, table.c.key == key)
        )
    ).first()
    if row is None:
        return None
    if row.request_hash != fp:
        raise Invalid("that Idempotency-Key was already used for a different request")
    return row.response


async def remember(session: AsyncSession, table: Table, who: str, key: str | None, fp: str, answer: BaseModel) -> None:
    if not key:
        return
    try:
        await session.execute(
            insert(table).values(
                principal=who,
                key=key,
                request_hash=fp,
                response=answer.model_dump(mode="json", by_alias=True),
                created_at=datetime.now(UTC),
            )
        )
    except IntegrityError:
        raise Conflict("that request is already being handled; retry in a moment") from None


async def expire(session: AsyncSession, table: Table, now: datetime | None = None) -> int:
    """Answers older than ``KEEP`` go: they held what was created, for the
    person who created it, and are useless once nobody will retry."""
    r = await session.execute(delete(table).where(table.c.created_at < (now or datetime.now(UTC)) - KEEP))
    return r.rowcount or 0


async def forget(session: AsyncSession, table: Table, who: str) -> None:
    """An account deletion: their stored answers go with it."""
    await session.execute(delete(table).where(table.c.principal == who))
