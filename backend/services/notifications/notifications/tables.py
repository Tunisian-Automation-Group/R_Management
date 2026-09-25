"""Nothing but what the event runtime needs: which events were handled."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cappy_common.db import UtcDateTime, new_metadata
from cappy_common.events import event_tables


class Base(DeclarativeBase):
    metadata = new_metadata()


OUTBOX, PROCESSED = event_tables(Base.metadata)


class DeviceRow(Base):
    """A phone that wants push notifications for whoever signed in on it."""

    __tablename__ = "devices"
    token: Mapped[str] = mapped_column(String(400), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(10))
    # The SNS platform endpoint; None where push is not configured.
    endpoint: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class InboxRow(Base):
    """What the bell shows: one row per notification a signed-in person was
    sent, in the words (and language) they were sent in."""

    __tablename__ = "inbox"
    # Derived from the event, so a redelivered event does not show twice.
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(String(2000))
    # An app path (/bookings/bk_1), or None when there is nothing to open.
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime)
    read_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    __table_args__ = (Index("ix_inbox_user_at", "user_id", "at", "id"),)
