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

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cappy_common.db import JsonType, UtcDateTime, new_metadata
from cappy_common.events import event_tables
from cappy_common.idempotency import idempotency_table


class Base(DeclarativeBase):
    metadata = new_metadata()


OUTBOX, PROCESSED = event_tables(Base.metadata)
IDEMPOTENCY = idempotency_table(Base.metadata)

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
    # ISO 4217, uppercase: the listing's currency, set at creation (M-3).
    currency: Mapped[str] = mapped_column(String(3))
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
    # Who did not turn up ("owner" or "renter"), when a no-show ended it.
    no_show: Mapped[str | None] = mapped_column(String(6), nullable=True)
    # Stripe's fingerprint of the card that paid (the same card, whoever
    # holds it): links a new account to a suspended one (S-17).
    card_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # An extension of another booking by the same renter (S-12): the time
    # straight after it, booked as its own booking.
    extends_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    __table_args__ = (
        UniqueConstraint("requester_id", "idempotency_key", name="uq_bookings_requester_idempotency"),
        CheckConstraint("window_end > window_start", name="window_forward"),
    )


class MessageRow(Base):
    """What the two sides of a booking say to each other. Sent before the
    booking was accepted, contact details are masked in ``body``; the words as
    written wait in ``unmasked`` and are shown once it is accepted
    (docs/research/2026-09-launch-gaps.md)."""

    __tablename__ = "booking_messages"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(40), ForeignKey("bookings.id", ondelete="CASCADE"))
    sender_id: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(String(2000))
    unmasked: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime)
    # Asks to pay around Cappy (messages.flagged): shown with a warning, kept for moderation.
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


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


class DisputeRow(Base):
    """A dispute's own state (S-21): who opened it and why, and the offer on
    the table. Each offer gives the other side 72 hours to answer; when a
    deadline passes with no agreement the dispute goes to staff."""

    __tablename__ = "booking_disputes"
    booking_id: Mapped[str] = mapped_column(String(40), ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True)
    by: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)
    respond_by: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    escalated_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # A refund to the renter, in minor units, that one side offered.
    offer_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offer_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offer_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class ResolutionRow(Base):
    """How a dispute was settled (H-6): by staff, or by the two sides agreeing
    (``by`` "agreement:<who accepted>"). Above the staff member's limit it
    waits for a second one (``pending_approval``)."""

    __tablename__ = "booking_resolutions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(40), ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    outcome: Mapped[str] = mapped_column(String(12))
    refund_amount: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(String(1000))
    by: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class ClaimRow(Base):
    """An owner's claim after a booking (S-12: a late return), for staff to
    confirm. Nothing is charged automatically: that needs a saved card (S-9)."""

    __tablename__ = "booking_claims"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(40), ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    by: Mapped[str] = mapped_column(String(64))
    minutes_late: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    __table_args__ = (UniqueConstraint("booking_id", "kind", name="uq_booking_claims_booking_kind"),)


Index("ix_bookings_requester_created", BookingRow.requester_id, BookingRow.created_at)
Index("ix_bookings_owner_created", BookingRow.owner_id, BookingRow.created_at)
# Busy intervals: holding bookings on a listing in a time range.
Index("ix_bookings_listing_window", BookingRow.listing_id, BookingRow.window_start)
# The sweeps: lapsed requests, and finished windows awaiting completion.
Index("ix_bookings_status_expires", BookingRow.status, BookingRow.expires_at)
Index("ix_bookings_status_window_end", BookingRow.status, BookingRow.window_end)
Index("ix_bookings_card_fingerprint", BookingRow.card_fingerprint)
Index("ix_bookings_status_updated", BookingRow.status, BookingRow.updated_at)
