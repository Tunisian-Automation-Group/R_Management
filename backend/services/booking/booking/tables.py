"""Booking tables.

The window a booking occupies is two real ``timestamptz`` columns, because the
constraint that makes double booking impossible (ADR 0004) is a range
exclusion over them. It is created in the migration:

    EXCLUDE USING gist (listing_id WITH =, tstzrange(window_start, window_end) WITH &&)
      WHERE (status IN ('awaiting_payment','requested','accepted','active','completed','disputed'))

(migration 0003; it began without the last two, and a job finished early
had its window sold again)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cappy_common.db import JsonType, UtcDateTime, new_metadata
from cappy_common.events import event_tables


class Base(DeclarativeBase):
    metadata = new_metadata()


OUTBOX, PROCESSED = event_tables(Base.metadata)

NO_DOUBLE_BOOKING = "ex_bookings_no_double_booking"


class BookingRow(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    requester_id: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str] = mapped_column(String(64))
    listing_id: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    window_start: Mapped[datetime] = mapped_column(UtcDateTime)
    window_end: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # When an awaiting-payment or requested booking lapses. Null otherwise.
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="eur")
    requirement: Mapped[dict] = mapped_column(JsonType)
    match: Mapped[dict] = mapped_column(JsonType)
    listing_snapshot: Mapped[dict] = mapped_column(JsonType)
    decline_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    # The owner's rating of the renter (two-way reviews), once given.
    renter_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # What the cancellation refunded, in cents.
    refund_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Blind two-way reviews: when the renter rated, and when both reviews were
    # published (once both are in, or 14 days after the booked window).
    rated_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    reviews_published_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # What the client sent in Idempotency-Key, so a retried POST returns the
    # booking it already made instead of making a second one.
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Where and how the hand-over happens, copied from the listing once the
    # booking is accepted: what was agreed, whatever the listing says later.
    handover: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    # A fingerprint of the create request, so a key reused for a different
    # request is refused rather than answered with the wrong booking.
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("requester_id", "idempotency_key", name="uq_bookings_requester_idempotency"),
        CheckConstraint("window_end > window_start", name="window_forward"),
    )


class MessageRow(Base):
    """What the two sides of a booking say to each other. Stored as shown:
    contact details are masked before it is saved if the booking was not
    accepted yet (docs/research/2026-09-launch-gaps.md)."""

    __tablename__ = "booking_messages"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(40), ForeignKey("bookings.id", ondelete="CASCADE"))
    sender_id: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(String(2000))
    at: Mapped[datetime] = mapped_column(UtcDateTime)


Index("ix_booking_messages_booking_at", MessageRow.booking_id, MessageRow.at)


class BlockRow(Base):
    """Someone who does not want to hear from, or be booked by, someone else."""

    __tablename__ = "blocks"
    blocker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class VerifiedRow(Base):
    """People Stripe Identity verified (payments' payment.identity_verified)."""

    __tablename__ = "verified_people"
    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class SuspendedRow(Base):
    """People moderation suspended (catalog's moderation.owner_suspended)."""

    __tablename__ = "suspended"
    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class EvidenceRow(Base):
    """Photos either side takes at hand-over (check_in) and return
    (check_out): what the machine looked like, for damage claims and disputes."""

    __tablename__ = "booking_evidence"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(40), ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    by: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(10))
    photos: Mapped[list] = mapped_column(JsonType)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


class TransitionRow(Base):
    """Every status change, by whom and when: the audit trail support and
    disputes need, and what a timeline on the booking screen is drawn from."""

    __tablename__ = "booking_transitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_id: Mapped[str] = mapped_column(String(40), ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    by: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UtcDateTime)


Index("ix_bookings_requester_created", BookingRow.requester_id, BookingRow.created_at)
Index("ix_bookings_owner_created", BookingRow.owner_id, BookingRow.created_at)
# Busy intervals: holding bookings on a listing in a time range.
Index("ix_bookings_listing_window", BookingRow.listing_id, BookingRow.window_start)
# The sweeps: lapsed requests, and finished windows awaiting completion.
Index("ix_bookings_status_expires", BookingRow.status, BookingRow.expires_at)
Index("ix_bookings_status_window_end", BookingRow.status, BookingRow.window_end)
