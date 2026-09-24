from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from cappy_common.db import Base


class AccountRow(Base):
    """A person who can sign in. The id is their owner id in the catalog, so
    everything they list, book or rate is already theirs."""

    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[str] = mapped_column(String(30))


class SessionRow(Base):
    """One sign-in on one device. Only a hash of the token is kept, so the
    database cannot be used to impersonate anyone."""

    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(40), ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[str] = mapped_column(String(30))


Index("ix_sessions_expires", SessionRow.expires_at)
