"""Matching: rank, price and schedule, over a bounded candidate set.

Every endpoint gathers exactly the data it needs — candidates or one
listing's context from the catalog, and the intervals already booked from
the booking service, in parallel — then runs the unchanged domain rules.
Nothing is cached across requests, so nothing can go stale across replicas.
"""

from __future__ import annotations

import asyncio

from fastapi import Depends, Query, Request, Response
from pydantic import Field

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, optional_principal, require_internal
from cappy_common.errors import Conflict, Invalid, NotFound
from cappy_common.models import CamelModel, Iso, MatchView, Quote, Requirement, World
from cappy_common.timeutil import HOUR_MS, iso_from_ms, ms_from_iso, now_iso

from .clients import Bookings, Busy, Catalog
from .domain.availability import Offer, offers_for
from .domain.browse import Spotlight, available_soon
from .domain.categories import CATEGORIES, GROUP_IDS, GROUPS, CategoryMeta, GroupMeta, categories_in
from .domain.feasibility import Feasibility, assess_feasibility
from .domain.match import SortKey, distance_km, find_matches, match_for_offer, sort_matches
from .domain.pricing import hours_for, quote_for
from .domain.reviews import REVIEW_TAGS

router = ApiRouter()
# The same for everyone and rarely changing: CloudFront answers these for five minutes.
PUBLIC_CACHE = "public, max-age=300"
internal = ApiRouter(prefix="/internal", dependencies=[Depends(require_internal)])

MAX_RESULTS = 100


def _catalog(request: Request) -> Catalog:
    return request.app.state.catalog


def _bookings(request: Request) -> Bookings:
    return request.app.state.bookings


def _window(request: Request, req) -> tuple[Iso, Iso]:  # noqa: ANN001
    now = _earliest_start(request)
    until = req.latest if req.mode == "window" else req.deadline
    start = max(now, req.earliest) if req.mode == "window" else now
    return start, until


async def _candidates_and_busy(request: Request, req, exclude_owner: str | None) -> tuple[World, Busy]:  # noqa: ANN001
    start, until = _window(request, req)
    if ms_from_iso(until) <= ms_from_iso(start):
        return World(owners=[], listings=[], slots=[], districts={}, reviews=[]), {}
    world = await _catalog(request).candidates(
        origin=req.district,
        max_km=req.max_distance_km,
        start=start,
        until=until,
        category=req.category,
        exclude_owner=exclude_owner,
    )
    busy = await _bookings(request).busy([l.id for l in world.listings], start, until)
    return world, busy


async def _context(request: Request, listing_id: str, origin: str | None = None) -> tuple[World, Busy]:
    """One listing's world and bookings, fetched in parallel."""
    start = now_iso()
    until = iso_from_ms(ms_from_iso(start) + 400 * 24 * HOUR_MS)
    world, busy = await asyncio.gather(
        _catalog(request).listing_context(listing_id, after=start, origin=origin),
        _bookings(request).busy([listing_id], start, until),
    )
    return world, busy


def _earliest_start(request: Request) -> Iso:
    """The owner needs time to answer a request (and the buyer to pay), so
    nothing can be booked to start sooner than this."""
    lead = request.app.state.settings.min_lead_minutes * 60_000
    return iso_from_ms(ms_from_iso(now_iso()) + lead)


# --- shapes -------------------------------------------------------------------------


class MatchesIn(CamelModel):
    requirement: Requirement
    sort: SortKey = "best"
    limit: int = Field(default=50, ge=1, le=MAX_RESULTS)


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
    quote: Quote | None = None
    feasibility: Feasibility


# --- vocabulary ------------------------------------------------------------------------


@router.get("/groups", response_model=list[GroupMeta])
async def list_groups(
    response: Response,
) -> list[GroupMeta]:
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return GROUPS


@router.get("/categories", response_model=list[CategoryMeta])
async def list_categories(response: Response, group: str | None = None) -> list[CategoryMeta]:
    response.headers["Cache-Control"] = PUBLIC_CACHE
    if group is None:
        return CATEGORIES
    if group not in GROUP_IDS:
        raise Invalid(f"unknown group: {group}")
    return categories_in(group)


@router.get("/review-tags", response_model=list[str])
async def list_review_tags(
    response: Response,
) -> list[str]:
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return list(REVIEW_TAGS)


# --- search ----------------------------------------------------------------------------


@router.post("/matches", response_model=list[MatchView])
async def matches(
    body: MatchesIn, request: Request, p: Principal | None = Depends(optional_principal)
) -> list[MatchView]:
    """Ranked capacity for a requirement. Your own listings are never results."""
    req = body.requirement
    world, busy = await _candidates_and_busy(request, req, p.sub if p else None)
    found = sort_matches(find_matches(req, world, _earliest_start(request), busy), body.sort)[: body.limit]
    listings = {l.id: l for l in world.listings}
    owners = {o.id: o for o in world.owners}
    return [MatchView(match=m, listing=listings[m.listing_id], owner=owners[m.owner_id]) for m in found]


@router.get("/browse/spotlight", response_model=list[Spotlight])
async def spotlight(
    request: Request,
    district: str,
    max_km: float = Query(default=10, alias="maxKm", gt=0, le=500),
    within_hours: float = Query(default=24, alias="withinHours", gt=0, le=24 * 14),
    limit: int = Query(default=12, ge=1, le=60),
    p: Principal | None = Depends(optional_principal),
) -> list[Spotlight]:
    """What is genuinely free near you soon, across every category."""
    now = _earliest_start(request)
    until = iso_from_ms(ms_from_iso(now) + int(within_hours * HOUR_MS))
    world = await _catalog(request).candidates(
        origin=district, max_km=max_km, start=now, until=until, category=None, exclude_owner=p.sub if p else None
    )
    busy = await _bookings(request).busy([l.id for l in world.listings], now, until)
    return available_soon(world, district, max_km, now, within_hours, limit, busy)


@router.get("/listings/{listing_id}/offers", response_model=list[Offer])
async def offers(
    listing_id: str,
    request: Request,
    hours: float = Query(gt=0, le=24 * 90),
    from_: str | None = Query(default=None, alias="from"),
    until: str | None = None,
    limit: int = Query(default=60, ge=1, le=500),
) -> list[Offer]:
    """Every start that fits ``hours`` of work, excluding what is already booked."""
    world, busy = await _context(request, listing_id)
    start = max(from_ or now_iso(), _earliest_start(request))
    end = until or iso_from_ms(ms_from_iso(start) + 28 * 24 * HOUR_MS)
    return offers_for(world.slots, hours, start, end, limit, busy.get(listing_id))


@router.post("/quote", response_model=QuoteOut)
async def quote(body: QuoteIn, request: Request) -> QuoteOut:
    world, _ = await _context(request, body.listing_id)
    listing = world.listings[0]
    return QuoteOut(
        quote=quote_for(body.requirement, listing), feasibility=assess_feasibility(body.requirement, listing)
    )


@router.post("/feasibility", response_model=Feasibility)
async def feasibility(body: QuoteIn, request: Request) -> Feasibility:
    world, _ = await _context(request, body.listing_id)
    return assess_feasibility(body.requirement, world.listings[0])


# --- internal: the booking service prices every booking here -------------------------------


@internal.post("/match-for-offer", response_model=MatchView)
async def match_for_offer_route(body: MatchForOfferIn, request: Request) -> MatchView:
    """The match for a window the buyer chose. The quote is computed here, never
    trusted from the client, and the window must still be free."""
    req = body.requirement
    world, busy = await _context(request, body.listing_id, origin=req.district)
    listing, owner = world.listings[0], world.owners[0]
    origin, dest = world.districts.get(req.district), world.districts.get(listing.district)
    if not origin or not dest:
        raise Invalid("unknown district")
    if not listing.active:
        raise NotFound(f"listing {listing.id} is not taking bookings")

    slot = next((s for s in world.slots if s.id == body.slot_id), None)
    if not slot:
        raise NotFound(f"slot {body.slot_id} not found on listing {listing.id}")
    start, end = ms_from_iso(body.start), ms_from_iso(body.end)
    if not (ms_from_iso(slot.start) <= start < end <= ms_from_iso(slot.end)):
        raise Invalid("the requested window does not sit inside that idle slot")
    if start < ms_from_iso(_earliest_start(request)):
        raise Invalid("that window starts too soon for the owner to answer; pick a later one")
    hours = hours_for(req, listing)
    if hours is not None and abs((end - start) / HOUR_MS - hours) > 0.01:
        raise Invalid(f"that requirement needs {hours:g} hours, not {(end - start) / HOUR_MS:g}")
    if any(a < end and start < b for a, b in busy.get(listing.id, [])):
        raise Conflict("that window was just taken; pick another")

    km = distance_km((origin.lat, origin.lng), (dest.lat, dest.lng))
    offer = Offer(slot_id=slot.id, start=iso_from_ms(start), end=iso_from_ms(end))
    match = match_for_offer(req, listing, owner, offer, km)
    if not match:
        raise Invalid("not feasible: " + "; ".join(assess_feasibility(req, listing).blockers))
    return MatchView(match=match, listing=listing, owner=owner)
