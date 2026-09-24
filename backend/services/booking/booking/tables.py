from __future__ import annotations

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from cappy_common.db import Base


class BookingRow(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    requester_id: Mapped[str] = mapped_column(String(40), index=True)
    owner_id: Mapped[str] = mapped_column(String(40), index=True)
    listing_id: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(12), index=True)
    created_at: Mapped[str] = mapped_column(String(30))
    updated_at: Mapped[str] = mapped_column(String(30))
    requirement: Mapped[dict] = mapped_column(JSON)
    match: Mapped[dict] = mapped_column(JSON)
    decline_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Demo: when a seeded host should be simulated as accepting. Null = never.
    auto_accept_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class MetaRow(Base):
    """Facts about the database itself: which edition of the world its bookings
    were made against."""

    __tablename__ = "booking_meta"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


Index("ix_bookings_auto_accept", BookingRow.status, BookingRow.auto_accept_at)
