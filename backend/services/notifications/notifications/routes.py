"""Devices that want push notifications."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Request, Response, status
from pydantic import Field
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_principal
from cappy_common.models import CamelModel
from cappy_common.runtime import Tx

from .tables import DeviceRow

router = ApiRouter(prefix="/notifications")

MAX_DEVICES = 10


class DeviceIn(CamelModel):
    platform: str = Field(pattern="^(ios|android)$")
    token: str = Field(min_length=8, max_length=400)


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def register(
    body: DeviceIn, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
):
    """The app calls this after sign-in with its APNs/FCM token. A token moves
    to whoever signed in on that device last."""
    endpoint = await request.app.state.pusher.register(body.platform, body.token)
    row = await session.get(DeviceRow, body.token)
    if row is None:
        session.add(
            DeviceRow(
                token=body.token, user_id=p.sub, platform=body.platform, endpoint=endpoint, created_at=datetime.now(UTC)
            )
        )
    else:
        row.user_id, row.platform, row.endpoint = p.sub, body.platform, endpoint
    await session.flush()
    await _keep_newest(session, p.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister(token: str, session: AsyncSession = Tx, p: Principal = Depends(require_principal)):
    """On sign-out: this device stops getting this person's notifications."""
    await session.execute(delete(DeviceRow).where(DeviceRow.token == token, DeviceRow.user_id == p.sub))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _keep_newest(session: AsyncSession, user_id: str) -> None:
    from sqlalchemy import select

    rows = (
        await session.execute(
            select(DeviceRow).where(DeviceRow.user_id == user_id).order_by(DeviceRow.created_at.desc())
        )
    ).scalars()
    for old in list(rows)[MAX_DEVICES:]:
        await session.delete(old)
