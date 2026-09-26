"""Devices that want push notifications."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import Depends, Request, Response, status
from pydantic import Field
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_internal, require_principal
from cappy_common.errors import Conflict
from cappy_common.models import CamelModel, Iso
from cappy_common.pagination import clamp_limit, decode_cursor, encode_cursor
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .prefs import Prefs, locale_of, prefs_of, save, seen_locale
from .push import drop_devices
from .tables import DeviceRow, InboxRow
from .texts import render, summary

router = ApiRouter(prefix="/notifications")
internal = ApiRouter(prefix="/internal", dependencies=[Depends(require_internal)])

MAX_DEVICES = 10


class DeviceIn(CamelModel):
    platform: str = Field(pattern="^(ios|android)$")
    token: str = Field(min_length=8, max_length=400)
    # A random id the app makes once per install and keeps (P-33).
    install_id: str | None = Field(default=None, min_length=16, max_length=100)


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def register(
    body: DeviceIn, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
):
    """The app calls this after sign-in with its APNs/FCM token. A token moves
    to whoever signed in on that device last, but only from the same install:
    someone who merely knows a token cannot take another person's pushes away
    or point theirs at that phone (P-33). On a move the old endpoint is deleted
    first, so none of the previous person's notifications can reach it."""
    pusher = request.app.state.pusher
    install = hashlib.sha256(body.install_id.encode()).hexdigest() if body.install_id else None
    row = await session.get(DeviceRow, body.token)
    if row is not None and row.user_id != p.sub:
        if row.install_hash is not None and row.install_hash != install:
            raise Conflict("this device is registered by another install", code="device_taken")
        if row.endpoint:
            await pusher.unregister(row.endpoint)
        await session.delete(row)
        await session.flush()
        row = None
    endpoint = await pusher.register(body.platform, body.token)
    if row is None:
        session.add(
            DeviceRow(
                token=body.token,
                user_id=p.sub,
                platform=body.platform,
                endpoint=endpoint,
                created_at=datetime.now(UTC),
                install_hash=install,
            )
        )
    else:
        row.platform, row.endpoint = body.platform, endpoint
        row.install_hash = install or row.install_hash
    await session.flush()
    await _keep_newest(session, pusher, p.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister(
    token: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
):
    """On sign-out: this device stops getting this person's notifications."""
    rows = (
        await session.execute(select(DeviceRow).where(DeviceRow.token == token, DeviceRow.user_id == p.sub))
    ).scalars()
    await drop_devices(session, request.app.state.pusher, rows)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _keep_newest(session: AsyncSession, pusher, user_id: str) -> None:  # noqa: ANN001
    rows = (
        await session.execute(
            select(DeviceRow).where(DeviceRow.user_id == user_id).order_by(DeviceRow.created_at.desc())
        )
    ).scalars()
    await drop_devices(session, pusher, list(rows)[MAX_DEVICES:])


# --- the notification centre -----------------------------------------------------------------


class Item(CamelModel):
    id: str
    kind: str
    title: str
    body: str
    link: str | None = None
    at: Iso
    read: bool


class Inbox(CamelModel):
    items: list[Item]
    next: str | None = None
    unread: int


def _item(r: InboxRow, locale: str | None) -> Item:
    title, body = r.title, r.body
    if r.params is not None:
        try:
            title, text = render(r.kind, locale, **r.params)
            body = summary(r.kind, text)
        except (KeyError, ValueError):  # a text key or param that changed since: as sent
            pass
    return Item(
        id=r.id, kind=r.kind, title=title, body=body, link=r.link, at=iso_from_datetime(r.at), read=bool(r.read_at)
    )


@router.get("", response_model=Inbox)
async def inbox(
    request: Request,
    cursor: str | None = None,
    limit: int | None = None,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_principal),
) -> Inbox:
    """Newest first; ``next`` continues towards older ones. In the language the
    app asks for (``Accept-Language``: de… → German, else English), which is
    also remembered for their emails (V6-6)."""
    await seen_locale(session, p.sub, request.headers.get("accept-language"))
    n = clamp_limit(limit)
    # Messages live in the Inbox (GET /api/inbox, its own unread count), not in
    # the bell: one message is one badge, not two (V9-21), as top apps do. The
    # rows are still kept: they pace the message emails (_recently_told).
    bell = (InboxRow.user_id == p.sub, InboxRow.kind != "message")
    q = select(InboxRow).where(*bell)
    if key := decode_cursor(cursor):
        at = dt_from_iso(key["at"])
        q = q.where(or_(InboxRow.at < at, and_(InboxRow.at == at, InboxRow.id < key["id"])))
    rows = list((await session.execute(q.order_by(InboxRow.at.desc(), InboxRow.id.desc()).limit(n + 1))).scalars())
    more, rows = len(rows) > n, rows[:n]
    unread = (await session.execute(select(func.count()).where(*bell, InboxRow.read_at.is_(None)))).scalar_one()
    return Inbox(
        items=[_item(r, request.headers.get("accept-language")) for r in rows],
        next=encode_cursor({"at": rows[-1].at.isoformat(), "id": rows[-1].id}) if more else None,
        unread=unread,
    )


@router.get("/settings", response_model=Prefs)
async def get_settings(session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> Prefs:
    return await prefs_of(session, p.sub)


@router.put("/settings", response_model=Prefs)
async def put_settings(body: Prefs, session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> Prefs:
    """Every category, both channels. Some emails still come (prefs.py says which)."""
    return await save(session, p.sub, body)


class ReadIn(CamelModel):
    ids: list[str] | None = Field(default=None, max_length=500)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(body: ReadIn, session: AsyncSession = Tx, p: Principal = Depends(require_principal)):
    """These, or (no ``ids``) everything of mine, as read."""
    q = update(InboxRow).where(InboxRow.user_id == p.sub, InboxRow.read_at.is_(None))
    if body.ids is not None:
        q = q.where(InboxRow.id.in_(body.ids))
    await session.execute(q.values(read_at=datetime.now(UTC)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@internal.get("/people/{person}/export")
async def export_person(person: str, request: Request, session: AsyncSession = Tx) -> dict:
    """Their notifications, settings, devices, and the sign-in's email and
    language (Cognito), for a data export (GDPR art. 15/20, D-10)."""
    email, locale = await request.app.state.directory.person_of(person)
    devices = (await session.execute(select(DeviceRow).where(DeviceRow.user_id == person))).scalars()
    rows = (
        await session.execute(
            select(InboxRow).where(InboxRow.user_id == person).order_by(InboxRow.at.desc()).limit(10_000)
        )
    ).scalars()
    return {
        "items": [_item(r, None).model_dump(mode="json", by_alias=True) for r in rows],
        "settings": (await prefs_of(session, person)).model_dump(mode="json", by_alias=True),
        "signIn": {"email": email, "locale": locale},
        "appLocale": await locale_of(session, person),
        "devices": [{"platform": d.platform, "registeredAt": d.created_at.isoformat()} for d in devices],
    }


# --- signing out everywhere ------------------------------------------------------------------
