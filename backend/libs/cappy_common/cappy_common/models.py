"""The capacity graph - a 1:1 port of the frontend's ``src/domain/types.ts``.

JSON is camelCase on the wire so the frontend's ``World`` and ``Booking`` types
are served verbatim. Money is integer cents everywhere; instants are ISO-8601
strings (``Iso``), exactly as the frontend stores them.

Optional fields are *omitted* from responses rather than sent as ``null``:
the app runs its own domain rules on the world it loads, and those rules test
``=== undefined``. ``cappy_common.app.ApiRouter`` enforces that on every route.
"""

from __future__ import annotations

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

BookingStatus = Literal["requested", "accepted", "declined", "active", "completed", "cancelled"]

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


class Owner(CamelModel):
    id: str
    name: str
    initials: str
    kind: Literal["person", "business"]
    district: str
    verified: bool
    rating_sum: int
    jobs_done: int
    on_time_jobs: int
    joined_year: int
    response_mins: int


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
    hours: float
    base: Cents
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
    note: str | None = None
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


class Booking(CamelModel):
    id: str
    match: Match
    requirement: Requirement
    status: BookingStatus
    created_at: Iso
    requester_id: str | None = None
    decline_reason: str | None = None
    outcome: Outcome | None = None


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
