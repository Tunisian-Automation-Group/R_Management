"""Catalog tables.

Mode-specific listing fields live in a JSON ``spec`` column so a new listing
shape needs no migration; everything that is filtered, joined or sorted on is
a real column with an index. Instants are ``timestamptz``.

Listings are soft-deleted (``deleted_at``): a booking made against a listing
must keep pointing at something, and a removed listing's reviews still count
toward its owner's record.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cappy_common.db import JsonType, UtcDateTime, new_metadata
from cappy_common.events import event_tables


class Base(DeclarativeBase):
    metadata = new_metadata()


OUTBOX, PROCESSED = event_tables(Base.metadata)


class DistrictRow(Base):
    __tablename__ = "districts"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    city: Mapped[str] = mapped_column(String(80))
    metro: Mapped[str] = mapped_column(String(80), index=True)
    country: Mapped[str] = mapped_column(String(2))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)


class OwnerRow(Base):
    """A person or business on the platform. For anyone who signed up, the id
    is their Cognito ``sub``; the catalog never stores their email or
    password, which stay with the identity provider."""

    __tablename__ = "owners"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    initials: Mapped[str] = mapped_column(String(4))
    kind: Mapped[str] = mapped_column(String(10))
    district: Mapped[str] = mapped_column(String(80), ForeignKey("districts.name"))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rating_sum: Mapped[int] = mapped_column(Integer, default=0)
    jobs_done: Mapped[int] = mapped_column(Integer, default=0)
    on_time_jobs: Mapped[int] = mapped_column(Integer, default=0)
    joined_year: Mapped[int] = mapped_column(Integer)
    response_mins: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ListingRow(Base):
    __tablename__ = "listings"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("owners.id"), index=True)
    category: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(120))
    blurb: Mapped[str] = mapped_column(String(500))
    district: Mapped[str] = mapped_column(String(80), ForeignKey("districts.name"))
    instructions: Mapped[str] = mapped_column(String(2000))
    rules: Mapped[list] = mapped_column(JsonType)
    photos: Mapped[list] = mapped_column(JsonType, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # WindowListing: ratePerHour, minHours, maxHours, extraFee, extraLabel
    # BatchListing:  machine, materials?, maxDims, toleranceMm?, unitsPerHour,
    #                setupHours, ratePerHour, setupFee
    spec: Mapped[dict] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


# The search path: category + live + where. District carries the coordinates.
Index("ix_listings_search", ListingRow.category, ListingRow.active, ListingRow.district)
# Only live listings are ever searched; a partial index keeps removed and
# paused ones out of it however many accumulate.
Index(
    "ix_listings_live",
    ListingRow.category,
    ListingRow.district,
    postgresql_where=ListingRow.deleted_at.is_(None) & ListingRow.active,
)

# Created in the migration with raw SQL, because they index expressions with a
# Postgres-only operator class (trigrams behind ILIKE search). The drift test
# allows exactly these and nothing else.
MIGRATION_ONLY_INDEXES = frozenset({"ix_listings_title_trgm", "ix_listings_blurb_trgm"})
Index("ix_listings_owner_created", ListingRow.owner_id, ListingRow.created_at)
Index("ix_districts_lat_lng", DistrictRow.lat, DistrictRow.lng)


class SlotRow(Base):
    """An idle window: the product."""

    __tablename__ = "slots"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    listing_id: Mapped[str] = mapped_column(String(40), ForeignKey("listings.id", ondelete="CASCADE"))
    start: Mapped[datetime] = mapped_column(UtcDateTime)
    end: Mapped[datetime] = mapped_column(UtcDateTime)
    hours_usable: Mapped[float] = mapped_column(Float)


# "Does this listing have a window still open after T?" is the hot predicate.
Index("ix_slots_listing_end", SlotRow.listing_id, SlotRow.end)


class ReviewRow(Base):
    """A rated booking, as the next buyer reads it."""

    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    listing_id: Mapped[str] = mapped_column(String(40), ForeignKey("listings.id", ondelete="CASCADE"))
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("owners.id"), index=True)
    author: Mapped[str] = mapped_column(String(120))
    initials: Mapped[str] = mapped_column(String(4))
    author_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)
    on_time: Mapped[bool] = mapped_column(Boolean)
    text: Mapped[str] = mapped_column(String(1000))
    tags: Mapped[list] = mapped_column(JsonType)
    at: Mapped[datetime] = mapped_column(UtcDateTime)


Index("ix_reviews_listing_at", ReviewRow.listing_id, ReviewRow.at)


class SavedRow(Base):
    """A listing someone hearted. A shortlist, not a booking."""

    __tablename__ = "saved_listings"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    listing_id: Mapped[str] = mapped_column(String(40), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    saved_at: Mapped[datetime] = mapped_column(UtcDateTime)


Index("ix_saved_user_at", SavedRow.user_id, SavedRow.saved_at)


class PayableOwnerRow(Base):
    """Owners payments can pay out to, as payments last told us. Kept apart
    from profiles so it does not matter which of the two arrives first."""

    __tablename__ = "payable_owners"
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    since: Mapped[datetime] = mapped_column(UtcDateTime)


class MediaRow(Base):
    """A photograph someone uploaded. Tracks who owns which object, so a
    listing can only show its owner's own uploads and orphans can be swept."""

    __tablename__ = "media"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
