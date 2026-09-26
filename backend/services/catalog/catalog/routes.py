from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Query, Request, Response, UploadFile, status
from pydantic import Field, TypeAdapter, ValidationError, ValidationInfo, field_validator
from pydantic.alias_generators import to_camel as camel

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, optional_principal, require_internal, require_principal
from cappy_common.categories import mode_of
from cappy_common.errors import Conflict, Forbidden, Invalid, NotFound, RateLimited, Unavailable
from cappy_common.events import LISTING_CHANGED, PERSON_SIGNED_OUT, PROFILE_CREATED, PROFILE_DELETED
from cappy_common.guard import hit, revoke
from cappy_common.idempotency import IdempotencyKey, fingerprint, remember, replayed
from cappy_common.markets import Market, live_market, market
from cappy_common.models import CamelModel, District, Handover, Iso, Listing, Owner, Review, Slot, World
from cappy_common.pagination import Page, clamp_limit
from cappy_common.runtime import ReadTx, Tx
from cappy_common.timeutil import HOUR_MS, dt_from_iso, ms_from_iso, now_iso

from . import media, schedule
from .geo import haversine_km
from .repository import CatalogRepository, to_listing
from .tables import IDEMPOTENCY, RATE_HITS

# Signed-in only (GOAL 13): nothing of the product is served to anonymous
# callers. Photos are the exception (an <img> cannot send a token; their names
# are unguessable content hashes), and so are the legal duties in moderation.
router = ApiRouter(dependencies=[Depends(require_principal)])
media_router = ApiRouter()
# The same for everyone and rarely changing: CloudFront answers these for five minutes.
PUBLIC_CACHE = "public, max-age=300"
internal = ApiRouter(prefix="/internal", dependencies=[Depends(require_internal)])

_listing = TypeAdapter(Listing)
_DECODING = asyncio.Semaphore(2)
MAX_PHOTOS = 12
# A listing's point may lie this far from its district's centre (M-5).
MAX_KM_FROM_DISTRICT = 30
MAX_RULES = 12
MAX_SLOTS_PER_CALL = 200


async def get_repo(request: Request, session=Tx) -> CatalogRepository:
    return CatalogRepository(session, bookable_only=request.app.state.settings.require_payable_owners)


async def get_read_repo(request: Request, session=ReadTx) -> CatalogRepository:
    """Public reads, served by the reader (a few ms behind the writer)."""
    return CatalogRepository(session, bookable_only=request.app.state.settings.require_payable_owners)


def _outbox(request: Request):
    return request.app.state.outbox


# --- shapes ------------------------------------------------------------------------


class ListingView(CamelModel):
    """What a card needs: the listing and who offers it."""

    listing: Listing
    owner: Owner
    saved: bool | None = None
    # Only on the owner's own listings: their upcoming idle windows, and the
    # private hand-over address.
    slots: list[Slot] | None = None
    address: str | None = None
    # Waiting for a staff check before it goes live.
    held: bool | None = None
    # Why, when it is not the price check: ``market_not_live`` or
    # ``district_not_in_country`` (V5-1). Only the owner fixes it, by moving it.
    hold_reason: str | None = None


class TagCount(CamelModel):
    tag: str
    n: int


class ReviewSummary(CamelModel):
    count: int
    average: float | None = None
    on_time_share: float | None = None
    top_tags: list[TagCount]


class ListingDetail(CamelModel):
    listing: Listing
    owner: Owner
    district: District
    slots: list[Slot]
    reviews: ReviewSummary
    saved: bool | None = None


class Me(CamelModel):
    id: str
    home_district: str
    owner: Owner | None = None


EU_VAT = re.compile(
    r"^(AT|BE|BG|CY|CZ|DE|DK|EE|EL|ES|FI|FR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK|XI)[0-9A-Z]{2,12}$"
)


class BusinessIn(CamelModel):
    """What a trader has to tell renters (§ 5b UWG, § 312l BGB)."""

    legal_name: str = Field(min_length=2, max_length=160)
    address: str = Field(min_length=8, max_length=300)
    register_number: str | None = Field(default=None, max_length=60)
    vat_id: str | None = Field(default=None, max_length=20)

    @field_validator("vat_id")
    @classmethod
    def _vat(cls, v: str | None) -> str | None:
        vat = re.sub(r"[\s.-]", "", v or "").upper() or None
        if vat is not None and not (re.fullmatch(r"DE\d{9}", vat) if vat.startswith("DE") else EU_VAT.fullmatch(vat)):
            raise ValueError("that VAT ID does not look right: a German one is DE and 9 digits")
        return vat

    def normalised(self) -> dict:
        vat = self.vat_id
        return {
            "legalName": self.legal_name.strip(),
            "address": self.address.strip(),
            "registerNumber": (self.register_number or "").strip() or None,
            "vatId": vat,
        }


class ProfileIn(CamelModel):
    name: str = Field(min_length=2, max_length=80)
    kind: str = Field(pattern=r"^(person|business)$")
    district: str = Field(max_length=80)
    # Required for a business: who renters contract with.
    business: BusinessIn | None = Field(default=None, validate_default=True)
    # Required when the profile is created: Cappy is for adults (the terms).
    adult: bool | None = None
    # Country of residence, ISO 3166-1 alpha-2 (payouts are set up there, M-9).
    country: str = Field(default="DE", pattern="^[A-Z]{2}$")

    @field_validator("business")
    @classmethod
    def _business_says_who_it_is(cls, v: BusinessIn | None, info: ValidationInfo) -> BusinessIn | None:
        # Checked with the other fields, so the form hears every problem at once.
        if info.data.get("kind") == "business" and v is None:
            raise ValueError(
                "a business says who it is: legal name and address (and register number and VAT ID if it has them)"
            )
        return v


class City(CamelModel):
    city: str
    country: str
    lat: float
    lng: float
    listings: int


class NearestDistrict(CamelModel):
    district: District
    km: float


class SlotIn(CamelModel):
    start: Iso
    end: Iso
    hours_usable: float = Field(gt=0, le=24 * 366)


class ListingIn(CamelModel):
    """A new or edited listing. Ids and the owner come from the server and the
    caller's token, never from the body."""

    listing: dict
    slots: list[SlotIn] = Field(default_factory=list, max_length=MAX_SLOTS_PER_CALL)
    # The hand-over address: kept private until a booking is accepted.
    address: str | None = Field(default=None, max_length=200)


class Uploaded(CamelModel):
    url: str
    width: int
    height: int
    bytes: int


class CandidatesIn(CamelModel):
    origin: str
    max_km: float = Field(gt=0, le=2000)
    start: Iso
    until: Iso
    category: str | None = None
    exclude_owner: str | None = None
    cap: int | None = Field(default=None, ge=1, le=1000)


# --- helpers -----------------------------------------------------------------------


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    return ("".join(p[0] for p in parts[:2]) or name[:2]).upper()[:4]


def _summary(stats) -> ReviewSummary:
    return ReviewSummary(
        count=stats.count,
        average=stats.average,
        on_time_share=stats.on_time_share,
        top_tags=[TagCount(tag=t, n=n) for t, n in stats.top_tags],
    )


async def _views(repo: CatalogRepository, listings: list, viewer: str | None) -> list[ListingView]:
    owners = await repo.owners({l.owner_id for l in listings})
    saved = await repo.saved_ids(viewer, {l.id for l in listings}) if viewer else set()
    return [
        ListingView(listing=l, owner=owners[l.owner_id], saved=(l.id in saved) if viewer else None)
        for l in listings
        if l.owner_id in owners
    ]


def _validate_slots(slots: list[SlotIn]) -> list[Slot]:
    out = []
    for s in slots:
        wall = (ms_from_iso(s.end) - ms_from_iso(s.start)) / HOUR_MS
        if wall <= 0:
            raise Invalid("a window must end after it starts")
        if s.hours_usable > wall + 1e-9:
            raise Invalid(f"a {wall:g}-hour window cannot have {s.hours_usable:g} usable hours")
        if ms_from_iso(s.end) <= ms_from_iso(now_iso()):
            raise Invalid("a window must end in the future")
        out.append(Slot(id="pending", listing_id="pending", start=s.start, end=s.end, hours_usable=s.hours_usable))
    return out


async def _district_in(repo: CatalogRepository, name: str, country: str) -> None:
    """A district that exists, in the country the person or listing is in: a
    Swiss profile (prices in CHF) is never in a Berlin district."""
    if not await repo.has_district(name):
        raise Invalid(f"unknown district: {name}", fields=[{"field": "district", "message": "unknown district"}])
    d = await repo.district(name)
    if d.country != country:
        raise Invalid(
            f"{name} is in {d.country}, not {country}",
            code="district_not_in_country",
            fields=[{"field": "district", "message": f"pick a district in {country}"}],
        )


async def _validate_listing(
    request: Request, repo: CatalogRepository, raw: dict, owner_id: str, already_shown: frozenset[str] = frozenset()
):
    # The listing's market is its owner's (M-2): it must be open, and prices
    # are in its currency, never converted (ADR 0013).
    owner = await repo.find_owner(owner_id)
    where = live_market(owner.country if owner else None)
    if raw.get("currency") is None:
        raw = {**raw, "currency": where.currency}
    elif str(raw["currency"]).upper() != where.currency:
        raise Invalid(f"listings in {where.code} are priced in {where.currency}", code="currency_not_in_market")
    try:
        listing = _listing.validate_python({**raw, "id": "pending", "ownerId": owner_id})
    except ValidationError as e:
        raise Invalid("that listing does not validate: " + "; ".join(err["msg"] for err in e.errors()[:5])) from e
    limits = {"title": 120, "blurb": 500, "instructions": 2000}
    for field, n in limits.items():
        value = getattr(listing, field)
        if not value.strip() or len(value) > n:
            raise Invalid(f"{field} must be 1 to {n} characters")
    if len(listing.rules) > MAX_RULES or any(len(r) > 200 for r in listing.rules):
        raise Invalid(f"at most {MAX_RULES} rules of 200 characters each")
    if mode_of(listing.category) != listing.mode:
        raise Invalid(f"category {listing.category} is booked by {mode_of(listing.category)}, not {listing.mode}")
    if listing.rate_per_hour <= 0:
        raise Invalid("ratePerHour must be positive")
    _check_numbers(listing, where)
    if listing.availability is not None:
        schedule.check(listing.availability)
    await _district_in(repo, listing.district, where.code)
    if listing.country and listing.country.upper() != where.code:
        raise Invalid(
            f"a listing of an owner in {where.code} is in {where.code}",
            code="district_not_in_country",
            fields=[{"field": "country", "message": f"must be {where.code}"}],
        )
    if listing.location is not None:
        # The district is the search bucket (candidates walk districts nearest
        # first, T-10): a point far from its district would be missed by it.
        # ponytail: districts as buckets; a point index (PostGIS or H3) when a
        # market has no districts yet (M-5).
        home = await repo.district(listing.district)
        km = haversine_km(home.lat, home.lng, listing.location.lat, listing.location.lng)
        if km > MAX_KM_FROM_DISTRICT:
            raise Invalid(
                f"that point is {km:.0f} km from {listing.district}; pick the district it is in",
                code="location_outside_district",
            )
    photos = listing.photos or []
    if len(photos) > MAX_PHOTOS:
        raise Invalid(f"at most {MAX_PHOTOS} photos per listing")
    settings = request.app.state.settings
    # Photos the listing already shows may stay (an edit resends them); every
    # new one must be the owner's own upload.
    new = [u for u in photos if u not in already_shown]
    names = [media.name_from_url(settings, u) for u in new]
    if any(n is None for n in names):
        raise Invalid("photos must be uploaded to Cappy first (POST /uploads)")
    owned = await repo.media_owned_by({n for n in names if n}, owner_id)
    if len(owned) != len(set(names)):
        raise Invalid("a listing can only show photos its owner uploaded")
    await repo.mark_used(owned, owner_id)
    return listing


async def _owned(repo: CatalogRepository, listing_id: str, user: str):
    # The owner may edit or withdraw a listing that waits for review.
    row = await repo.listing_row(listing_id, include_held=True)
    if row.owner_id != user:
        # Someone else's listing is indistinguishable from none at all.
        raise NotFound(f"listing {listing_id} not found")
    return row


def _check_numbers(listing, where: Market) -> None:
    """Every number a listing carries within sane bounds, so no listing can
    break pricing for others (P-1). Money in minor units, capped per market."""
    money = where.max_rate_per_hour
    bounds = {
        "rate_per_hour": (1, money),
        "extra_fee": (0, money),
        "setup_fee": (0, money),
        "min_hours": (0.5, 24 * 90),
        "max_hours": (0.5, 24 * 90),
        "units_per_hour": (0.001, 1_000_000),
        "setup_hours": (0, 24 * 7),
        "tolerance_mm": (0, 1_000),
    }
    for field, (lo, hi) in bounds.items():
        value = getattr(listing, field, None)
        if value is None:
            continue
        if not math.isfinite(value) or not lo <= value <= hi:
            raise Invalid(f"{camel(field)} must be between {lo} and {hi}")
    if listing.mode == "window" and listing.min_hours > listing.max_hours:
        raise Invalid("minHours cannot be more than maxHours")


# --- me ----------------------------------------------------------------------------


@router.get("/me", response_model=Me)
async def get_me(request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)) -> Me:
    """Who the caller is on Cappy. ``owner`` is absent until they have created
    a profile, which the app asks for right after sign-up."""
    owner = await repo.find_owner(p.sub)
    home = owner.district if owner else request.app.state.settings.home_district
    return Me(id=p.sub, home_district=home, owner=owner)


@router.put("/me", response_model=Owner)
async def put_me(
    body: ProfileIn, request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)
) -> Owner:
    """Create the caller's profile, or update its name, kind and district.
    Idempotent: calling it twice with the same body is one profile."""
    where = live_market(body.country)
    await _district_in(repo, body.district, where.code)
    business = body.business.normalised() if body.kind == "business" and body.business else None
    name = body.name.strip()
    owner, created = await repo.upsert_profile(
        p.sub,
        name=name,
        initials=_initials(name),
        kind=body.kind,
        district=body.district,
        business=business,
        adult=bool(body.adult),
        minimum_age=where.minimum_age,
        country=body.country,
    )
    if created:
        await _outbox(request).add(repo.s, PROFILE_CREATED, {"ownerId": owner.id, "district": owner.district})
    return owner


# --- places ------------------------------------------------------------------------


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)) -> Response:
    """Delete my account (App Store 5.1.1(v), GDPR Art. 17). Refused while a
    booking is open on either side or a payout is pending: those finish first.
    ``profile.deleted`` then reaches every service: each erases what it holds
    (the register in cappy_common/privacy.py), notifications deletes the
    sign-in (Cognito AdminDeleteUser), and every token issued before now stops
    working. What the law keeps (bookings, payments and invoices for
    accounting) stays, with the person's names, contact details, hand-over
    details and free text redacted (docs/retention.md)."""
    opened = await request.app.state.bookings.open_for(p.sub)
    payouts = await request.app.state.payments.pending_payouts(p.sub)
    if opened["open"] or payouts:
        # Deleting would strand the other side of a booking, or money owed to
        # them: say what is in the way and until when (Apple 5.1.1(v) allows
        # a delay if the app says why).
        raise Conflict(
            "finish or cancel your open bookings, and wait for your payouts, before deleting your account",
            code="open_obligations",
            details={"openBookings": opened["open"], "pendingPayouts": payouts, "until": opened.get("until")},
        )
    await repo.forget(p.sub)
    await _end_sessions(request, repo.s, p.sub)
    await _outbox(request).add(repo.s, PROFILE_DELETED, {"ownerId": p.sub})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _end_sessions(request: Request, session, sub: str) -> None:  # noqa: ANN001
    """Tokens issued so far stop counting here at once; the other services
    record the same when the event reaches them (P-24)."""
    await revoke(session, request.app.state.runtime.revoked_table, sub, datetime.now(UTC))
    request.app.state.revocations.forget(sub)


@router.post("/me/sign-out-everywhere", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out_everywhere(
    request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)
) -> Response:
    """A lost phone: every session of theirs ends. Here at once; the other
    services within seconds (person.signed_out); notifications then revokes
    every refresh token in Cognito and forgets their devices."""
    await hit(
        repo.s,
        RATE_HITS,
        f"sign-out:{p.sub}",
        limit=5,
        window=timedelta(hours=1),
        message="you have signed out everywhere several times this hour; try again later",
    )
    await _end_sessions(request, repo.s, p.sub)
    await _outbox(request).add(repo.s, PERSON_SIGNED_OUT, {"personId": p.sub})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/export")
async def export_me(request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)) -> Response:
    """A copy of everything held about me, as one JSON file. A few a day: each
    asks four services for everything they hold (P-12)."""
    await hit(
        repo.s,
        RATE_HITS,
        f"export:{p.sub}",
        limit=5,
        window=timedelta(days=1),
        message="you have downloaded your data several times today; try again tomorrow",
    )
    data = await repo.export(p.sub)
    data.update(await request.app.state.bookings.all_for(p.sub))
    data["payments"] = await request.app.state.payments.export_for(p.sub)
    data["notifications"] = await request.app.state.notifications.export_for(p.sub)
    data["exportedAt"] = now_iso()
    return Response(
        content=json.dumps(data, indent=1, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="cappy-my-data.json"'},
    )


@router.get("/districts", response_model=dict[str, District])
async def districts(response: Response, repo=Depends(get_read_repo)) -> dict[str, District]:
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return await repo.districts()


@router.get("/cities", response_model=list[City])
async def cities(response: Response, repo=Depends(get_read_repo)) -> list[City]:
    response.headers["Cache-Control"] = PUBLIC_CACHE
    return [
        City(city=c.metro, country=c.country, lat=c.lat, lng=c.lng, listings=c.listings) for c in await repo.cities()
    ]


@router.get("/districts/nearest", response_model=NearestDistrict)
async def nearest(
    lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180), repo=Depends(get_read_repo)
) -> NearestDistrict:
    found = await repo.nearest_district(lat, lng)
    if not found:
        raise NotFound("no districts")
    return NearestDistrict(district=found[0], km=found[1])


# --- owners and listings (public reads) --------------------------------------------------


@router.get("/owners/{owner_id}", response_model=Owner)
async def owner(owner_id: str, repo=Depends(get_read_repo)) -> Owner:
    return await repo.owner(owner_id)


@router.get("/listings/{listing_id}", response_model=ListingDetail)
async def listing_detail(
    listing_id: str, repo=Depends(get_read_repo), p: Principal | None = Depends(optional_principal)
) -> ListingDetail:
    # The owner sees their own listing while it waits for review, or paused
    # ("View as a guest", FL-6); nobody else does.
    row = await repo.listing_row(listing_id, include_held=True)
    mine = p is not None and p.sub == row.owner_id
    if (row.held_at is not None or not row.active) and not mine:
        raise NotFound(f"listing {listing_id} not found")
    saved = (listing_id in await repo.saved_ids(p.sub, {listing_id})) if p else None
    return await detail_of(repo, row, saved)


async def detail_of(repo, row, saved: bool | None = None) -> ListingDetail:
    """The listing page's answer for a row: shared with the staff preview."""
    listing = to_listing(row)
    listing_id = row.id
    return ListingDetail(
        listing=listing,
        owner=await repo.owner(listing.owner_id),
        district=await repo.district(listing.district),
        slots=await repo.upcoming_slots({listing_id}, after=dt_from_iso(now_iso())),
        reviews=_summary(await repo.review_stats(listing_id)),
        saved=saved,
    )


@router.get("/listings/{listing_id}/reviews", response_model=Page[Review])
async def listing_reviews(
    listing_id: str, cursor: str | None = None, limit: int | None = None, repo=Depends(get_read_repo)
) -> Page[Review]:
    await repo.listing_row(listing_id)
    items, nxt = await repo.reviews(listing_id, cursor=cursor, limit=clamp_limit(limit))
    return Page(items=items, next_cursor=nxt)


@router.get("/search", response_model=Page[ListingView])
async def search(
    # Three characters: what the trigram index needs to avoid a full scan.
    q: str = Query(min_length=3, max_length=80),
    metro: str | None = None,
    category: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    repo=Depends(get_read_repo),
    p: Principal | None = Depends(optional_principal),
) -> Page[ListingView]:
    items, nxt = await repo.search(q=q, metro=metro, category=category, cursor=cursor, limit=clamp_limit(limit))
    return Page(items=await _views(repo, items, p.sub if p else None), next_cursor=nxt)


# --- my listings (owner writes) ---------------------------------------------------------


@router.get("/me/listings", response_model=Page[ListingView])
async def my_listings(
    cursor: str | None = None,
    limit: int | None = None,
    repo=Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> Page[ListingView]:
    items, nxt = await repo.listings_by_owner(p.sub, cursor=cursor, limit=clamp_limit(limit))
    views = await _views(repo, items, p.sub)
    slots: dict[str, list[Slot]] = {}
    for s in await repo.upcoming_slots({v.listing.id for v in views}, after=datetime.now(UTC)):
        slots.setdefault(s.listing_id, []).append(s)
    addresses = await repo.addresses({v.listing.id for v in views})
    held = await repo.held_ids({v.listing.id for v in views})
    for v in views:
        v.held = v.listing.id in held or None
        v.hold_reason = held.get(v.listing.id)
        v.slots = slots.get(v.listing.id, [])
        v.address = addresses.get(v.listing.id)
    return Page(items=views, next_cursor=nxt)


class CreatedListing(CamelModel):
    listing: Listing
    slots: list[Slot]
    # True when it waits for a quick staff check before anyone can see it.
    held: bool = False


@router.post("/listings", response_model=CreatedListing, status_code=status.HTTP_201_CREATED)
async def create_listing(
    body: ListingIn,
    request: Request,
    repo=Depends(get_repo),
    p: Principal = Depends(require_principal),
    key: str | None = IdempotencyKey,
) -> CreatedListing:
    fp = fingerprint(request, body)
    if (done := await replayed(repo.s, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    if not request.app.state.settings.accepting_listings:
        raise Unavailable("new listings are paused for a moment; please try again later")
    if await repo.find_owner(p.sub) is None:
        raise Forbidden("create your profile before listing anything")
    if await repo.is_suspended(p.sub):
        raise Forbidden("your account is suspended; see the email we sent you")
    settings = request.app.state.settings
    if await repo.listings_since(p.sub, datetime.now(UTC) - timedelta(days=1)) >= settings.max_listings_per_day:
        raise RateLimited("that is a lot of new listings for one day; try again tomorrow")
    listing = await _validate_listing(request, repo, body.listing, p.sub)
    created, slots = await repo.create_listing(listing, _validate_slots(body.slots))
    await repo.set_address(created.id, body.address)
    if listing.availability is not None:
        await repo.apply_schedule(created.id, listing.availability, datetime.now(UTC), replace=False)
        slots = await repo.upcoming_slots({created.id}, after=datetime.now(UTC))
    owner = await repo.owner(p.sub)
    if owner.jobs_done == 0 and listing.rate_per_hour > market(owner.country).held_listing_above:
        await repo.hold(created.id)
        created = created.model_copy(update={"active": False})
        held = True
    else:
        held = False
    await _outbox(request).add(repo.s, LISTING_CHANGED, {"listingId": created.id, "change": "created"})
    answer = CreatedListing(listing=created, slots=slots, held=held)
    await remember(repo.s, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


@router.put("/listings/{listing_id}", response_model=Listing)
async def update_listing(
    listing_id: str,
    body: ListingIn,
    request: Request,
    repo=Depends(get_repo),
    p: Principal = Depends(require_principal),
):
    row = await _owned(repo, listing_id, p.sub)
    # An edit that does not mention the schedule keeps it; null removes it.
    raw = {**body.listing, "mode": row.mode, "category": row.category}
    if "availability" not in raw and (row.spec or {}).get("availability"):
        raw["availability"] = row.spec["availability"]
    before = (row.spec or {}).get("availability")
    listing = await _validate_listing(
        request,
        repo,
        raw,
        p.sub,
        already_shown=frozenset(row.photos or []),
    )
    if row.hold_reason:
        # Moved into an open market (the checks above passed): out of the hold.
        row.held_at, row.hold_reason, row.active = None, None, True
    updated = await repo.update_listing(listing_id, listing)
    after = listing.availability.model_dump(mode="json", by_alias=True) if listing.availability else None
    if after != before:
        await repo.apply_schedule(listing_id, listing.availability, datetime.now(UTC), replace=True)
    owner = await repo.owner(p.sub)
    if (
        owner.jobs_done == 0
        and listing.rate_per_hour > market(owner.country).held_listing_above
        and row.held_at is None
    ):
        # Raising the price past the review threshold is a new listing as far
        # as fraud goes: it waits for a staff check like one.
        await repo.hold(listing_id)
    if "address" in body.model_fields_set:
        await repo.set_address(listing_id, body.address)
    await _outbox(request).add(repo.s, LISTING_CHANGED, {"listingId": listing_id, "change": "updated"})
    return updated


@router.post("/listings/{listing_id}/slots", response_model=list[Slot], status_code=status.HTTP_201_CREATED)
async def add_slots(
    listing_id: str,
    body: list[SlotIn],
    request: Request,
    repo=Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> list[Slot]:
    await _owned(repo, listing_id, p.sub)
    if len(body) > MAX_SLOTS_PER_CALL:
        raise Invalid(f"at most {MAX_SLOTS_PER_CALL} windows per call")
    return await repo.add_slots(listing_id, _validate_slots(body))


@router.delete("/listings/{listing_id}/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_slot(
    listing_id: str, slot_id: str, repo=Depends(get_repo), p: Principal = Depends(require_principal)
) -> Response:
    await _owned(repo, listing_id, p.sub)
    await repo.remove_slot(listing_id, slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _set_active(listing_id: str, active: bool, request: Request, repo: CatalogRepository, p: Principal):
    await _owned(repo, listing_id, p.sub)
    updated = await repo.set_active(listing_id, active)
    await _outbox(request).add(
        repo.s, LISTING_CHANGED, {"listingId": listing_id, "change": "resumed" if active else "paused"}
    )
    return updated


@router.post("/listings/{listing_id}/pause", response_model=Listing)
async def pause(listing_id: str, request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)):
    return await _set_active(listing_id, False, request, repo, p)


@router.post("/listings/{listing_id}/resume", response_model=Listing)
async def resume(listing_id: str, request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)):
    return await _set_active(listing_id, True, request, repo, p)


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    listing_id: str, request: Request, repo=Depends(get_repo), p: Principal = Depends(require_principal)
) -> Response:
    await _owned(repo, listing_id, p.sub)
    await repo.soft_delete(listing_id)
    await _outbox(request).add(repo.s, LISTING_CHANGED, {"listingId": listing_id, "change": "removed"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- photos ----------------------------------------------------------------------------


@router.post("/uploads", response_model=Uploaded, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile,
    request: Request,
    purpose: str = Query(default="listing", pattern="^(listing|evidence)$"),
    repo=Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> Uploaded:
    """One photograph in, its URL out, to go in a listing's ``photos``. With
    ``purpose=evidence`` (hand-over photos) it is stored privately and the
    answer's ``url`` is a reference (``evidence:<name>``) for the booking's
    evidence, never a public link (P-27)."""
    settings = request.app.state.settings
    if await repo.uploads_since(p.sub, datetime.now(UTC) - timedelta(days=1)) >= settings.media_daily_quota:
        raise RateLimited("that is a lot of photos for one day; try again tomorrow")
    data = await file.read(settings.media_max_bytes + 1)
    # Decoding a photo takes up to ~4 bytes per pixel, twice over: at most two
    # at a time per task keeps a burst of uploads from exhausting its memory.
    async with _DECODING:
        processed = await asyncio.to_thread(
            media.process,
            data,
            max_bytes=settings.media_max_bytes,
            max_edge=settings.media_max_edge,
            max_pixels=settings.media_max_pixels,
        )
    private = purpose == "evidence"
    await (request.app.state.evidence if private else request.app.state.media).put(processed.name, processed.data)
    await repo.record_media(processed.name, p.sub, len(processed.data), processed.width, processed.height)
    return Uploaded(
        url=media.evidence_ref(processed.name) if private else media.url_for(settings, processed.name),
        width=processed.width,
        height=processed.height,
        bytes=len(processed.data),
    )


@media_router.get("/media/{name}", include_in_schema=False)
async def serve_media(name: str, request: Request) -> Response:
    """Only used where no CDN fronts the bucket (local development). In AWS,
    CloudFront serves ``/media/*`` from S3 and this is never reached."""
    data = await request.app.state.media.get(name)
    return Response(data, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})


# --- saved --------------------------------------------------------------------------------


@router.get("/saved", response_model=Page[ListingView])
async def saved(
    cursor: str | None = None,
    limit: int | None = None,
    repo=Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> Page[ListingView]:
    items, nxt = await repo.saved(p.sub, cursor=cursor, limit=clamp_limit(limit))
    return Page(items=await _views(repo, items, p.sub), next_cursor=nxt)


@router.put("/saved/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def save(listing_id: str, repo=Depends(get_repo), p: Principal = Depends(require_principal)) -> Response:
    await repo.listing_row(listing_id)
    await repo.save(p.sub, listing_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/saved/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave(listing_id: str, repo=Depends(get_repo), p: Principal = Depends(require_principal)) -> Response:
    await repo.unsave(p.sub, listing_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- internal: for matching and booking --------------------------------------------------------


@internal.post("/candidates", response_model=World)
async def candidates(body: CandidatesIn, request: Request, repo=Depends(get_read_repo)) -> World:
    origin = await repo.district(body.origin)
    cap = body.cap or request.app.state.settings.candidate_cap
    return await repo.candidates(
        origin=origin,
        max_km=body.max_km,
        start=dt_from_iso(body.start),
        until=dt_from_iso(body.until),
        category=body.category,
        cap=cap,
        exclude_owner=body.exclude_owner,
    )


@internal.get("/revocations/{sub}")
async def revocation(sub: str, request: Request) -> dict:
    """When this person's sessions ended (sign out everywhere, deletion), for
    matching, which keeps no database of its own (P-24). Catalog records the
    revocation first, in the same request that asked for it."""
    return {"notBefore": await request.app.state.revocations.not_before(sub)}


@internal.get("/listings/{listing_id}/context", response_model=World)
async def listing_context(
    listing_id: str,
    after: str | None = None,
    origin: str | None = None,
    staff: bool = False,
    repo=Depends(get_read_repo),
) -> World:
    """``staff``: a held listing too, for the staff preview's free times and
    quote (V6-2); matching asks it only on its admin routes."""
    return await repo.listing_context(
        listing_id, after=dt_from_iso(after or now_iso()), origin=origin, include_held=staff
    )


class EvidenceIn(CamelModel):
    owner_id: str = Field(max_length=64)
    urls: list[str] = Field(min_length=1, max_length=12)


@internal.post("/media/evidence", status_code=status.HTTP_204_NO_CONTENT)
async def keep_evidence(body: EvidenceIn, request: Request, repo=Depends(get_repo)) -> Response:
    """Booking keeps these as check-in/out evidence: they must be the person's
    own private uploads (``POST /uploads?purpose=evidence``), and they are
    never swept as unused."""
    names = [media.name_from_ref(u) for u in body.urls]
    if any(n is None for n in names):
        raise Invalid("hand-over photos must be uploaded as evidence first (POST /uploads?purpose=evidence)")
    owned = await repo.media_owned_by({n for n in names if n}, body.owner_id)
    if len(owned) != len(set(names)):
        raise Invalid("those photos were not uploaded by you")
    await repo.mark_used(owned, body.owner_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@internal.get("/evidence/{name}", include_in_schema=False)
async def evidence_photo(name: str, request: Request) -> Response:
    """For booking, which decides who may see it (P-27)."""
    data = await request.app.state.evidence.get(name)
    return Response(data, media_type="image/webp", headers={"Cache-Control": "private, no-store"})


@internal.get("/people/{person}/name")
async def person_name(person: str, repo=Depends(get_repo)) -> dict:
    """The name a person goes by, for booking to tell an owner who asked
    (V7-23). Nothing for someone without a profile, or gone."""
    owner = await repo.find_owner(person)
    return {"name": owner.name if owner else None}


@internal.get("/listings/{listing_id}/handover", response_model=Handover)
async def handover(listing_id: str, repo=Depends(get_repo)) -> Handover:
    """For booking to give the two sides of an accepted booking. Works for a
    listing removed since, because the booking still happens."""
    row = await repo.listing_row(listing_id, include_deleted=True)
    spec = row.spec or {}
    return Handover(
        address=row.address,
        instructions=row.instructions,
        location=spec.get("location"),
        postal_code=spec.get("postalCode"),
    )
