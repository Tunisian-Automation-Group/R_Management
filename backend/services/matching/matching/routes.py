from __future__ import annotations

from fastapi import Depends, Query, Request

from cappy_common.app import ApiRouter
from cappy_common.errors import Invalid, NotFound
from cappy_common.models import (
    CamelModel,
    Iso,
    Match,
    Quote,
    Requirement,
    Review,
    World,
)
from cappy_common.timeutil import iso_from_ms, ms_from_iso, now_iso

from .domain.availability import Offer, offers_for
from .domain.browse import (
    CityStat,
    IdleSummary,
    NearestDistrict,
    Spotlight,
    available_soon,
    cities,
    idle_europe,
    idle_nearby,
    nearest_district,
)
from .domain.categories import CATEGORIES, GROUP_IDS, GROUPS, CategoryMeta, GroupMeta, categories_in
from .domain.feasibility import Feasibility, assess_feasibility
from .domain.match import SortKey, distance_km, find_matches, match_for_offer, sort_matches
from .domain.pricing import quote_for
from .domain.reviews import REVIEW_TAGS, ReviewSummary, by_recent, summarise

router = ApiRouter()


async def get_world(request: Request) -> World:
    return await request.app.state.world_provider.get()


def _now(now: str | None) -> Iso:
    return now or now_iso()


class MatchesIn(CamelModel):
    requirement: Requirement
    now: Iso | None = None
    sort: SortKey = "best"


class MatchForOfferIn(CamelModel):
    requirement: Requirement
    listing_id: str
    slot_id: str
    start: Iso
    end: Iso


class QuoteIn(CamelModel):
    requirement: Requirement
    listing_id: str


class QuoteOut(CamelModel):
    quote: Quote | None
    feasibility: Feasibility


class ReviewsOut(CamelModel):
    summary: ReviewSummary
    reviews: list[Review]


def _listing_and_owner(world: World, listing_id: str):
    listing = next((l for l in world.listings if l.id == listing_id), None)
    if not listing:
        raise NotFound(f"listing {listing_id} not found")
    owner = next((o for o in world.owners if o.id == listing.owner_id), None)
    if not owner:
        raise NotFound(f"owner {listing.owner_id} not found")
    return listing, owner


# --- vocabulary: what a client needs to draw the browse screen without a seed --


@router.get("/groups", response_model=list[GroupMeta])
async def list_groups() -> list[GroupMeta]:
    """Make, move, equip. The three tabs of the browse screen."""
    return GROUPS


@router.get("/categories", response_model=list[CategoryMeta])
async def list_categories(group: str | None = None) -> list[CategoryMeta]:
    if group is None:
        return CATEGORIES
    if group not in GROUP_IDS:
        raise Invalid(f"unknown group: {group}")
    return categories_in(group)


@router.get("/review-tags", response_model=list[str])
async def list_review_tags() -> list[str]:
    """The fixed vocabulary a buyer picks from when rating a booking."""
    return list(REVIEW_TAGS)


# --- matching ------------------------------------------------------------------


@router.post("/matches", response_model=list[Match])
async def matches(body: MatchesIn, world: World = Depends(get_world)) -> list[Match]:
    found = find_matches(body.requirement, world, _now(body.now))
    return sort_matches(found, body.sort)


@router.post("/match-for-offer", response_model=Match)
async def match_for_offer_route(body: MatchForOfferIn, world: World = Depends(get_world)) -> Match:
    """The match for a window the buyer chose. The booking service calls this so
    a booking's quote is computed here, never trusted from the client."""
    listing, owner = _listing_and_owner(world, body.listing_id)
    origin = world.districts.get(body.requirement.district)
    dest = world.districts.get(listing.district)
    if not origin or not dest:
        raise Invalid("unknown district")

    slot = next((s for s in world.slots if s.id == body.slot_id and s.listing_id == listing.id), None)
    if not slot:
        raise NotFound(f"slot {body.slot_id} not found on listing {listing.id}")
    start, end = ms_from_iso(body.start), ms_from_iso(body.end)
    if not (ms_from_iso(slot.start) <= start < end <= ms_from_iso(slot.end)):
        raise Invalid("the requested window does not sit inside that idle slot")

    km = distance_km((origin.lat, origin.lng), (dest.lat, dest.lng))
    offer = Offer(slot_id=slot.id, start=iso_from_ms(start), end=iso_from_ms(end))
    match = match_for_offer(body.requirement, listing, owner, offer, km)
    if not match:
        fit = assess_feasibility(body.requirement, listing)
        raise Invalid("not feasible: " + "; ".join(fit.blockers))
    return match


@router.post("/quote", response_model=QuoteOut)
async def quote(body: QuoteIn, world: World = Depends(get_world)) -> QuoteOut:
    listing, _ = _listing_and_owner(world, body.listing_id)
    return QuoteOut(
        quote=quote_for(body.requirement, listing),
        feasibility=assess_feasibility(body.requirement, listing),
    )


@router.post("/feasibility", response_model=Feasibility)
async def feasibility(body: QuoteIn, world: World = Depends(get_world)) -> Feasibility:
    listing, _ = _listing_and_owner(world, body.listing_id)
    return assess_feasibility(body.requirement, listing)


@router.get("/listings/{listing_id}/offers", response_model=list[Offer])
async def offers(
    listing_id: str,
    hours: float = Query(gt=0),
    from_: str | None = Query(default=None, alias="from"),
    until: str | None = None,
    limit: int = Query(default=60, ge=1, le=500),
    world: World = Depends(get_world),
) -> list[Offer]:
    _listing_and_owner(world, listing_id)
    start = _now(from_)
    end = until or iso_from_ms(ms_from_iso(start) + 7 * 24 * 3_600_000)
    slots = [s for s in world.slots if s.listing_id == listing_id]
    return offers_for(slots, hours, start, end, limit)


@router.get("/listings/{listing_id}/reviews/summary", response_model=ReviewsOut)
async def reviews_summary(listing_id: str, world: World = Depends(get_world)) -> ReviewsOut:
    """What the listing screen leads with: the average, the share ready on time,
    the tags people pick most, and then the words, newest first."""
    _listing_and_owner(world, listing_id)
    mine = [r for r in world.reviews if r.listing_id == listing_id]
    return ReviewsOut(summary=summarise(mine), reviews=by_recent(mine))


# --- browse --------------------------------------------------------------------


@router.get("/browse/spotlight", response_model=list[Spotlight])
async def spotlight(
    district: str,
    max_km: float = Query(default=10, alias="maxKm", gt=0),
    now: str | None = None,
    within_hours: float = Query(default=24, alias="withinHours", gt=0),
    limit: int = Query(default=12, ge=1, le=100),
    world: World = Depends(get_world),
) -> list[Spotlight]:
    return available_soon(world, district, max_km, _now(now), within_hours, limit)


@router.get("/browse/idle", response_model=IdleSummary)
async def idle(
    district: str,
    max_km: float = Query(default=10, alias="maxKm", gt=0),
    now: str | None = None,
    horizon_hours: float = Query(default=24, alias="horizonHours", gt=0),
    world: World = Depends(get_world),
) -> IdleSummary:
    return idle_nearby(world, district, max_km, _now(now), horizon_hours)


@router.get("/browse/cities", response_model=list[CityStat])
async def browse_cities(
    now: str | None = None,
    horizon_hours: float = Query(default=168, alias="horizonHours", gt=0),
    world: World = Depends(get_world),
) -> list[CityStat]:
    return cities(world, _now(now), horizon_hours)


@router.get("/browse/europe", response_model=IdleSummary)
async def browse_europe(
    now: str | None = None,
    horizon_hours: float = Query(default=168, alias="horizonHours", gt=0),
    world: World = Depends(get_world),
) -> IdleSummary:
    return idle_europe(world, _now(now), horizon_hours)


@router.get("/districts/nearest", response_model=NearestDistrict)
async def nearest(lat: float, lng: float, world: World = Depends(get_world)) -> NearestDistrict:
    found = nearest_district(world, lat, lng)
    if not found:
        raise NotFound("no districts in the world")
    return found
