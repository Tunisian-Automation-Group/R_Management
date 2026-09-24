"""The one account the demo ships with."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from sqlalchemy import select

from cappy_common.timeutil import now_iso

from .security import hash_password
from .tables import AccountRow

log = logging.getLogger(__name__)


async def seed_demo_account(app: FastAPI) -> bool:
    """Sign-in for the seeded owner the app used to speak for, so the Earn
    side is not empty on a cold start. No-op when it exists or is disabled."""
    settings = app.state.settings
    if not settings.demo_account_password or not settings.demo_account_owner_id:
        return False
    async with app.state.db.session() as s, s.begin():
        exists = await s.scalar(select(AccountRow).where(AccountRow.id == settings.demo_account_owner_id))
        if exists:
            return False
        s.add(
            AccountRow(
                id=settings.demo_account_owner_id,
                email=settings.demo_account_email.lower(),
                password_hash=hash_password(settings.demo_account_password),
                name="Nadia Brandt",
                created_at=now_iso(),
            )
        )
    log.info("seeded the demo account %s", settings.demo_account_email)
    return True
