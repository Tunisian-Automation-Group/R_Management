"""Tables. Mode-specific listing fields live in a JSON ``spec`` column so a new
listing shape never needs a migration; the shared columns are real columns
because they are filtered and indexed."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from cappy_common.db import Base


class DistrictRow(Base):
    __tablename__ = "districts"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    city: Mapped[str] = mapped_column(String(80))
    metro: Mapped[str] = mapped_column(String(80), index=True)
    country: Mapped[str] = mapped_column(String(2))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)


class OwnerRow(Base):
    __tablename__ = "owners"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    initials: Mapped[str] = mapped_column(String(4))
    kind: Mapped[str] = mapped_column(String(10))
    district: Mapped[str] = mapped_column(String(80))
    verified: Mapped[bool] = mapped_column(Boolean)
    rating_sum: Mapped[int] = mapped_column(Integer, default=0)
    jobs_done: Mapped[int] = mapped_column(Integer, default=0)
    on_time_jobs: Mapped[int] = mapped_column(Integer, default=0)
    joined_year: Mapped[int] = mapped_column(Integer)
    response_mins: Mapped[int] = mapped_column(Integer)


class ListingRow(Base):
    __tablename__ = "listings"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(40), ForeignKey("owners.id"), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    mode: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    blurb: Mapped[str] = mapped_column(String(1000))
    district: Mapped[str] = mapped_column(String(80), ForeignKey("districts.name"), index=True)
    instructions: Mapped[str] = mapped_column(String(2000))
    rules: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Everything mode-specific, plus the optional photos:
    # WindowListing: ratePerHour, minHours, maxHours, extraFee, extraLabel
    # BatchListing:  machine, materials?, maxDims, toleranceMm?, unitsPerHour,
    #                setupHours, ratePerHour, setupFee
    spec: Mapped[dict] = mapped_column(JSON)


class SlotRow(Base):
    __tablename__ = "slots"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    listing_id: Mapped[str] = mapped_column(String(60), ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    start: Mapped[str] = mapped_column(String(30))
    end: Mapped[str] = mapped_column(String(30))
    hours_usable: Mapped[float] = mapped_column(Float)


class ReviewRow(Base):
    """A rated booking, as the next buyer reads it. Seeded ones are written from
    each owner's record; live ones arrive on ``booking.rated``."""

    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    listing_id: Mapped[str] = mapped_column(String(60), ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(String(40), ForeignKey("owners.id"), index=True)
    author: Mapped[str] = mapped_column(String(120))
    initials: Mapped[str] = mapped_column(String(4))
    author_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)
    on_time: Mapped[bool] = mapped_column(Boolean)
    text: Mapped[str] = mapped_column(String(2000))
    tags: Mapped[list] = mapped_column(JSON)
    at: Mapped[str] = mapped_column(String(30))


class MetaRow(Base):
    """Facts about the database itself: which edition of the seed it holds."""

    __tablename__ = "catalog_meta"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class SavedRow(Base):
    """A listing someone hearted. A shortlist, not a booking."""

    __tablename__ = "saved_listings"
    user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    listing_id: Mapped[str] = mapped_column(
        String(60), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    saved_at: Mapped[str] = mapped_column(String(30))


Index("ix_slots_listing_start", SlotRow.listing_id, SlotRow.start)
Index("ix_reviews_listing_at", ReviewRow.listing_id, ReviewRow.at)
Index("ix_saved_user_at", SavedRow.user_id, SavedRow.saved_at)
