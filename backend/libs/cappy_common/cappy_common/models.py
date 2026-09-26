"""The capacity graph - a 1:1 port of the frontend's ``src/domain/types.ts``.

JSON is camelCase on the wire so the frontend's ``World`` and ``Booking`` types
are served verbatim. Money is integer cents everywhere; instants are ISO-8601
strings (``Iso``), exactly as the frontend stores them.

Optional fields are *omitted* from responses rather than sent as ``null``:
the app runs its own domain rules on the world it loads, and those rules test
``=== undefined``. ``cappy_common.app.ApiRouter`` enforces that on every route.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

Cents = int
Iso = str

BookingMode = Literal["window", "batch"]

# Make it, move it, or borrow the kit. Every physical job is some sequence of
# those three, and a buyer arrives knowing which one they are short of.
CategoryGroup = Literal["make", "move", "equip"]

# Nine categories across the chain. There is deliberately no consumer/industry
# split: one capacity graph, several demand pools.
CategoryId = Literal[
    # make
    "fabrication",
    "additive",
    "finishing",
    "print",
    # move
    "freight",
    "warehousing",
    # equip
    "workshop",
    "events",
    "creator",
]

Material = Literal[
    "PLA",
    "PETG",
    "ABS",
    "ASA",
    "TPU",
    "Resin",
    "Aluminium 6061",
    "Aluminium 7075",
    "Stainless 304",
    "Steel S235",
    "Brass",
    "POM",
    "Acrylic",
    "Plywood",
]

BookingStatus = Literal[
    "disputed",
    "awaiting_payment",
    "requested",
    "accepted",
    "active",
    "completed",
    "declined",
    "cancelled",
    "expired",
    "payment_failed",
]

# The things people say about a booking, as a fixed vocabulary (``REVIEW_TAGS``
# in ``src/domain/reviews.ts``). Picked rather than typed, because a tag that
# twelve buyers chose is a fact about an owner and twelve free-text sentences
# are not something anyone reads.
REVIEW_TAGS: tuple[str, ...] = (
    "As described",
    "Ready on time",
    "Clear handover",
    "Quick replies",
    "Great quality",
    "Fair price",
)


class CamelModel(BaseModel):
    """Accepts snake_case or camelCase, always emits camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="ignore",
        # JSON NaN/Infinity parse in Python; no number we take may be one (P-22).
        allow_inf_nan=False,
    )


class Dims(CamelModel):
    """Bounding box in millimetres."""

    x: float
    y: float
    z: float


class District(CamelModel):
    name: str
    city: str
    metro: str
    country: str
    lat: float
    lng: float


class Business(CamelModel):
    """A trader's identity (§ 5b UWG, § 312l BGB): public, so a renter knows
    who their contract is with. People never have one."""

    legal_name: str
    address: str
    register_number: str | None = None
    vat_id: str | None = None


class Owner(CamelModel):
    id: str
    name: str
    initials: str
    kind: Literal["person", "business"]
    district: str
    # Where they live (ISO 3166-1 alpha-2): their payout account's country (M-9).
    country: str = "DE"
    verified: bool
    rating_sum: int
    jobs_done: int
    on_time_jobs: int
    joined_year: int
    # Measured by booking over 90 days (H-1): the median minutes to answer a
    # request and the share answered before it lapsed. None until at least
    # three requests: never a made-up number.
    response_mins: int | None = None
    response_rate: float | None = None
    # As a renter: what owners said after completed bookings (two-way reviews).
    renter_rating_sum: int = 0
    renter_jobs: int = 0
    # Businesses only: who the renter contracts with.
    business: Business | None = None
    # Share of accepted bookings the owner cancelled or did not show up for,
    # over 12 months; None under 5 bookings (too few to mean anything).
    cancellation_rate: float | None = None


# What prices can be in (GOAL 16: Europe, the US and Canada), ISO 4217.
# Amounts are always minor units of the listing's own currency; nothing is
# converted, and a booking takes its listing's currency (M-3).
Currency = Literal["EUR", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "ISK", "USD", "CAD"]


class Location(CamelModel):
    """Where a listing is (M-5). Stored exactly; answered snapped to a grid of
    about 500 m (M-6) until a booking is accepted, like the address."""

    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)


# About 500 m north–south everywhere; east–west it narrows towards the poles,
# which only makes the square smaller, never larger than 500 m.
SNAP_DEG = 0.0045


def snapped(loc: Location) -> Location:
    """The middle of the grid square the point is in: stable (the same point
    always gives the same answer, so averaging answers learns nothing)."""

    def mid(v: float) -> float:
        return round((math.floor(v / SNAP_DEG) + 0.5) * SNAP_DEG, 5)

    return Location(lat=mid(loc.lat), lng=mid(loc.lng))


class WeeklyHours(CamelModel):
    """Open every week on one day (1 = Monday … 7 = Sunday, ISO), local time."""

    day: int = Field(ge=1, le=7)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")


class Availability(CamelModel):
    """A weekly schedule (H-4): the server keeps windows open from it, eight
    weeks ahead, in the listing's own time zone, so a listing never goes
    dark because nobody added windows by hand."""

    weekly: list[WeeklyHours] = Field(min_length=1, max_length=21)
    time_zone: str = "Europe/Berlin"


class _ListingBase(CamelModel):
    id: str
    owner_id: str
    category: CategoryId
    title: str
    blurb: str
    district: str
    # What the owner photographed. The first is the cover. Optional, because a
    # listing is valid before anyone uploads anything.
    photos: list[str] | None = None
    instructions: str
    rules: list[str]
    active: bool
    # Booked without the owner answering: confirmed once the card is held.
    instant_book: bool = False
    # What a renter gets back if they cancel an accepted booking (see
    # booking/cancellation.py). Only "flexible" is offered until counsel
    # confirms the others against the EU withdrawal right.
    cancellation_policy: Literal["flexible", "moderate", "strict"] = "flexible"
    # Longer bookings cost less per hour: percent off the hourly base from a
    # day (8 h) and from a week (40 h) of use. 0 to 50.
    day_discount_pct: int = Field(default=0, ge=0, le=50)
    week_discount_pct: int = Field(default=0, ge=0, le=50)
    # The currency its prices are in.
    currency: Currency = "EUR"
    # Opening hours the server turns into windows (H-4); None: windows by hand.
    availability: Availability | None = None
    # Where it is (M-5): the district stays as the place's name and the search
    # bucket; this is the point. Public answers snap it (M-6); the postal code
    # goes with the address, after acceptance.
    location: Location | None = None
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    postal_code: str | None = Field(default=None, max_length=12)


class WindowListing(_ListingBase):
    mode: Literal["window"]
    rate_per_hour: Cents
    min_hours: float
    max_hours: float
    extra_fee: Cents
    extra_label: str


class BatchListing(_ListingBase):
    mode: Literal["batch"]
    # The machine, the line, or the vehicle. Whatever actually does the work.
    machine: str
    # Absent where the question does not apply: a truck does not stock a material.
    materials: list[Material] | None = None
    max_dims: Dims
    # Tightest tolerance held, in mm. Absent where nothing is being held to one.
    tolerance_mm: float | None = None
    units_per_hour: float
    setup_hours: float
    rate_per_hour: Cents
    setup_fee: Cents
    # The most one booking can take, in the category's unit: two pallet
    # spaces in a van (V5-22). Absent: no limit beyond the time it takes.
    max_quantity: int | None = Field(default=None, ge=1, le=1_000_000)


Listing = Annotated[WindowListing | BatchListing, Field(discriminator="mode")]
AnyListing = WindowListing | BatchListing


class Slot(CamelModel):
    """An idle window. This is the product."""

    id: str
    listing_id: str
    start: Iso
    end: Iso
    hours_usable: float


class WindowRequest(CamelModel):
    mode: Literal["window"]
    category: CategoryId
    hours: float
    earliest: Iso
    latest: Iso
    district: str
    max_distance_km: float


class BatchRequest(CamelModel):
    mode: Literal["batch"]
    category: CategoryId
    quantity: int
    material: Material | None = None
    dims: Dims | None = None
    tolerance_mm: float | None = None
    deadline: Iso
    district: str
    max_distance_km: float


Requirement = Annotated[WindowRequest | BatchRequest, Field(discriminator="mode")]
AnyRequirement = WindowRequest | BatchRequest


class Quote(CamelModel):
    # Every amount below is in minor units of this currency (the listing's).
    currency: str = "EUR"
    hours: float
    base: Cents
    # What a duration discount took off the base (already out of `total`).
    discount: Cents = 0
    discount_label: str = ""
    extra: Cents
    extra_label: str
    total: Cents
    platform_fee: Cents
    owner_net: Cents


class Match(CamelModel):
    listing_id: str
    owner_id: str
    slot_id: str
    start: Iso
    end: Iso
    score: float
    confidence: float
    reasons: list[str]
    quote: Quote
    distance_km: float


class Outcome(CamelModel):
    on_time: bool
    quality: int = Field(ge=1, le=5)
    # What the buyer wrote. Becomes a review the next buyer reads.
    note: str | None = Field(default=None, max_length=1000)
    # The short things people say most, picked rather than typed.
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _known_tags(cls, tags: list[str] | None) -> list[str] | None:
        if tags is None:
            return None
        unknown = [t for t in tags if t not in REVIEW_TAGS]
        if unknown:
            raise ValueError(f"unknown review tags: {', '.join(unknown)}")
        # Keep order, drop repeats: a tag is a fact, not a count.
        return list(dict.fromkeys(tags))


class Review(CamelModel):
    """The feedback loop, as the next buyer sees it: an outcome with the reason
    attached, which is the part a stranger deciding whether to trust an owner
    actually reads."""

    id: str
    listing_id: str
    owner_id: str
    author: str
    initials: str
    rating: int = Field(ge=1, le=5)
    on_time: bool
    text: str
    tags: list[str]
    at: Iso
    # Who wrote it, when they are an account on the platform. Lets a client
    # label its own reviews "You"; seeded reviews have no account behind them.
    author_id: str | None = None


class ListingSnapshot(CamelModel):
    """What the listing looked like when it was booked: enough to draw a
    booking card without asking the catalog about every row, and the record of
    what was actually agreed even if the listing changes or is removed later."""

    title: str
    district: str
    category: CategoryId
    owner_name: str
    photo: str | None = None
    instant_book: bool = False
    cancellation_policy: str = "flexible"
    # Who the renter contracted with, when the owner is a trader (§ 5b UWG).
    owner_business: Business | None = None
    # Where the listing is (IANA): times in emails and the app read in it.
    time_zone: str | None = None


class MatchView(CamelModel):
    """A match with what a card needs to draw it: matching returns it for a
    search, and for the one window a buyer picked when booking."""

    match: Match
    listing: Listing
    owner: Owner


class Handover(CamelModel):
    address: str | None = None
    instructions: str
    # The exact point and postal code (M-6), once a booking is accepted.
    location: Location | None = None
    postal_code: str | None = None


class Booking(CamelModel):
    id: str
    match: Match
    requirement: Requirement
    status: BookingStatus
    created_at: Iso
    requester_id: str | None = None
    decline_reason: str | None = None
    # The reason's code when it is one of ours (cappy_common.reasons), so the
    # app words it in the reader's language; absent for a person's own words.
    decline_reason_code: str | None = None
    outcome: Outcome | None = None
    listing: ListingSnapshot | None = None
    # While a request waits for payment or for the owner: when it lapses.
    expires_at: Iso | None = None
    # Once accepted: where and how the hand-over happens.
    handover: Handover | None = None
    # When either side may first mark the hand-over (the server's rule).
    can_start_from: Iso | None = None
    # From when the owner may report a late return (S-12): the booked end,
    # earlier with the local testing shortcut. The app asks this, not a rule.
    late_return_from: Iso | None = None
    # The owner's rating of the renter (1-5), once given.
    renter_rating: int | None = None
    # What a cancellation refunded (minor units of ``currency``), once cancelled.
    refund_amount: int | None = None
    # The listing's currency, ISO 4217 uppercase like the listing and quote:
    # every amount on the booking and its quote is in it (M-3).
    currency: str = "EUR"
    # Who did not turn up, when a no-show ended the booking.
    no_show: Literal["owner", "renter"] | None = None
    # An extension names the booking it extends (S-12, V6-22).
    extends_id: str | None = None
    # Where the money stands (V7-2, V7-3), minor units of ``currency``:
    # what the card was charged, what went back, the owner's share of the
    # rest, and what has actually reached the owner. ``paid_out`` only where
    # payments said so (the detail): a list cannot know whether a payout was
    # held (payouts off, a chargeback), so it leaves it out rather than guess.
    charged: int = 0
    refunded: int = 0
    owner_share: int = 0
    paid_out: int | None = None


class World(CamelModel):
    owners: list[Owner]
    listings: list[Listing]
    slots: list[Slot]
    districts: dict[str, District]
    reviews: list[Review] = Field(default_factory=list)


# --- the few pure helpers types.ts ships alongside the shapes -----------------


def rating(o: Owner) -> float | None:
    """None until rated at all: new is not the same as bad."""
    return o.rating_sum / o.jobs_done if o.jobs_done > 0 else None


def reliability(o: Owner) -> float:
    """Unrated owners sit mid-scale rather than at zero."""
    return o.on_time_jobs / o.jobs_done if o.jobs_done > 0 else 0.5


def apply_outcome(o: Owner, outcome: Outcome) -> Owner:
    """Fold a finished booking into the owner's record. Pure: returns a new owner."""
    return o.model_copy(
        update={
            "rating_sum": o.rating_sum + outcome.quality,
            "jobs_done": o.jobs_done + 1,
            "on_time_jobs": o.on_time_jobs + (1 if outcome.on_time else 0),
        }
    )


def is_window(l: AnyListing) -> bool:
    return l.mode == "window"


def is_batch(l: AnyListing) -> bool:
    return l.mode == "batch"
