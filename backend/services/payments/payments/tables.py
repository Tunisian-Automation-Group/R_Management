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
    # Stripe's fingerprint of the card (the same for the same card on any
    # account): booking links it to suspended accounts (S-17).
    card_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class IdentityRow(Base):
    """Whether Stripe Identity has verified who someone is. The document and
    selfie stay with Stripe; we keep only the outcome."""

    __tablename__ = "identities"
    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # The person's explicit consent to the ID and selfie check, before it
    # starts (GDPR Art. 9(2)(a), CPRA sensitive data, BIPA; P-18): when, and
    # which wording they agreed to.
    consent_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(40), nullable=True)


class InvoiceRow(Base):
    """The platform's invoice to an owner for its fee (Art. 226 VAT Directive;
    GoBD: numbered without gaps, kept 10 years, never changed once issued)."""

    __tablename__ = "invoices"
    number: Mapped[str] = mapped_column(String(20), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(40), unique=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    net: Mapped[int] = mapped_column(Integer)
    vat_rate_bps: Mapped[int] = mapped_column(Integer)
    vat: Mapped[int] = mapped_column(Integer)
    gross: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    issued_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # What and for whom, copied at issue (invoices never change). Null on
    # invoices issued before 0006.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_start: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    service_end: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recipient_address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    recipient_vat_id: Mapped[str | None] = mapped_column(String(20), nullable=True)


class InvoiceCounterRow(Base):
    """One row per year: the last number issued. Taken under a row lock, so
    numbers never repeat or skip, however many payouts run at once."""

    __tablename__ = "invoice_counters"
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last: Mapped[int] = mapped_column(Integer)


class ConnectAccountRow(Base):
    """An owner's Stripe Express account. Stripe holds their identity and bank
    details; we keep the id and whether they can be paid."""

    __tablename__ = "connect_accounts"
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(80), unique=True)
    payouts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    details_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
