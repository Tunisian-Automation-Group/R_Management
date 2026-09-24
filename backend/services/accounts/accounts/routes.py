from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import Depends, Header, Request, Response, status
from pydantic import Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.errors import Conflict, Invalid, NotFound, Unauthorized
from cappy_common.ids import new_id
from cappy_common.models import CamelModel, Iso, Owner
from cappy_common.timeutil import DAY_MS, iso_from_ms, now_iso, now_ms

from .security import hash_password, new_token, token_hash, verify_password
from .tables import AccountRow, SessionRow

router = ApiRouter()

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.session() as session:
        async with session.begin():
            yield session


class Account(CamelModel):
    id: str
    email: str
    name: str


class SessionOut(CamelModel):
    """What a client keeps: the token to send back, and who it is for."""

    token: str
    account: Account
    expires_at: Iso


class SessionInfo(Account):
    expires_at: Iso


class RegisterIn(CamelModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=2, max_length=120)
    kind: str = "person"
    district: str


class LoginIn(CamelModel):
    email: str
    password: str


def _normalise_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL.match(email):
        raise Invalid("that does not look like an email address")
    return email


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    letters = "".join(p[0] for p in parts[:2]).upper()
    return letters or name[:2].upper()


async def _open_session(session: AsyncSession, account: AccountRow, days: int) -> SessionOut:
    token = new_token()
    expires = iso_from_ms(now_ms() + days * DAY_MS)
    session.add(
        SessionRow(token_hash=token_hash(token), account_id=account.id, created_at=now_iso(), expires_at=expires)
    )
    await session.flush()
    return SessionOut(
        token=token,
        account=Account(id=account.id, email=account.email, name=account.name),
        expires_at=expires,
    )


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("sign in to do that")
    token = authorization[7:].strip()
    if not token:
        raise Unauthorized("sign in to do that")
    return token


async def _session_for(session: AsyncSession, token: str) -> tuple[SessionRow, AccountRow]:
    row = await session.get(SessionRow, token_hash(token))
    if not row or row.expires_at <= now_iso():
        if row:
            await session.delete(row)
        raise Unauthorized("your session has ended; sign in again")
    account = await session.get(AccountRow, row.account_id)
    if not account:
        raise Unauthorized("that account no longer exists")
    return row, account


@router.post("/auth/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, session: AsyncSession = Depends(get_session)) -> SessionOut:
    """A new person: an owner in the catalog (so they can list, book and be
    rated from the first minute) and an account here, signed in at once."""
    email = _normalise_email(body.email)
    if body.kind not in ("person", "business"):
        raise Invalid("kind must be person or business")
    if await session.scalar(select(AccountRow).where(AccountRow.email == email)):
        raise Conflict("there is already an account with that email; sign in instead")

    owner = Owner(
        id=new_id("u"),
        name=body.name.strip(),
        initials=_initials(body.name),
        kind=body.kind,  # type: ignore[arg-type]
        district=body.district,
        verified=False,
        rating_sum=0,
        jobs_done=0,
        on_time_jobs=0,
        joined_year=datetime.now().year,
        response_mins=30,
    )
    # The catalog validates the district and refuses a duplicate id.
    created = await request.app.state.catalog.create_owner(owner)

    account = AccountRow(
        id=created.id,
        email=email,
        password_hash=hash_password(body.password),
        name=created.name,
        created_at=now_iso(),
    )
    session.add(account)
    await session.flush()
    return await _open_session(session, account, request.app.state.settings.session_days)


@router.post("/auth/login", response_model=SessionOut)
async def login(body: LoginIn, request: Request, session: AsyncSession = Depends(get_session)) -> SessionOut:
    email = body.email.strip().lower()
    account = await session.scalar(select(AccountRow).where(AccountRow.email == email))
    # One message for both failures: which of the two was wrong is not for a
    # stranger to learn.
    if not account or not verify_password(body.password, account.password_hash):
        raise Unauthorized("wrong email or password")
    return await _open_session(session, account, request.app.state.settings.session_days)


@router.get("/auth/session", response_model=SessionInfo)
async def whoami(
    authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_session)
) -> SessionInfo:
    """Who this token belongs to. The gateway asks on every signed request."""
    row, account = await _session_for(session, _bearer(authorization))
    return SessionInfo(id=account.id, email=account.email, name=account.name, expires_at=row.expires_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    authorization: str | None = Header(default=None), session: AsyncSession = Depends(get_session)
) -> Response:
    """Ends this device's session. Other devices stay signed in."""
    await session.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash(_bearer(authorization))))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/internal/accounts/{owner_id}", response_model=Account)
async def account_for_owner(owner_id: str, session: AsyncSession = Depends(get_session)) -> Account:
    """Is there a real person behind this owner? The booking service asks, to
    know whether a request to them is answered by them or by the demo."""
    account = await session.get(AccountRow, owner_id)
    if not account:
        raise NotFound(f"no account for owner {owner_id}")
    return Account(id=account.id, email=account.email, name=account.name)


@router.post("/admin/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    """Demo only: forget every account except the seeded one, and every session."""
    from .seed import seed_demo_account

    await session.execute(delete(SessionRow))
    await session.execute(delete(AccountRow))
    await session.commit()
    await seed_demo_account(request.app)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
