"""One payment per booking, one connected account per owner."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cappy_common.db import UtcDateTime, new_metadata
from cappy_common.events import event_tables


class Base(DeclarativeBase):
    metadata = new_metadata()


OUTBOX, PROCESSED = event_tables(Base.metadata)


class PaymentRow(Base):
    """status: created -> authorised -> captured -> transferred
    and from created/authorised -> cancelled, from captured -> refunded."""

    __tablename__ = "payments"
    booking_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(80), unique=True)
    requester_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    owner_net: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))
    charge_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transfer_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    refund_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # The card holder disputed the charge with their bank (a chargeback).
    # While set, the owner is not paid out; support settles it.
    chargeback_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ConnectAccountRow(Base):
    """An owner's Stripe Express account. Stripe holds their identity and bank
    details; we keep the id and whether they can be paid."""

    __tablename__ = "connect_accounts"
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(80), unique=True)
    payouts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    details_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
