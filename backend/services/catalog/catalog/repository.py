"""Every read and write against the catalog's tables, as domain models.

Nothing here returns the whole database. Lists are keyset-paginated; search
returns a bounded candidate set; the one exception, ``load_seed``, is a
developer tool (ADR 0010).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter
from sqlalchemy import Integer, and_, cast, delete, exists, func, insert, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common import idempotency
from cappy_common.errors import Invalid, NotFound
from cappy_common.ids import new_id
from cappy_common.models import (
    AnyListing,
    Availability,
    District,
    Listing,
    Location,
    Outcome,
    Owner,
    Review,
    Slot,
    World,
    snapped,
)
from cappy_common.pagination import decode_cursor, encode_cursor
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from . import schedule
from .tables import (
    IDEMPOTENCY,
    DistrictRow,
    ListingRow,
    MediaRow,
    ModerationActionRow,
    OwnerRow,
    PayableOwnerRow,
    ReportRow,
    ReviewRow,
    SavedRow,
    SlotRow,
)

_listing = TypeAdapter(Listing)

_BASE_FIELDS = {
    "id",
    "ownerId",
    "category",
    "mode",
    "title",
    "blurb",
    "district",
    "instructions",
    "rules",
    "active",
    "photos",
}

KM_PER_DEG_LAT = 110.574


# Far in the past: a photo marked so is swept on the next run (forget).
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


def _now() -> datetime:
    return datetime.now(UTC)


# --- rows <-> models ------------------------------------------------------------


def to_district(r: DistrictRow) -> District:
    return District(name=r.name, city=r.city, metro=r.metro, country=r.country, lat=r.lat, lng=r.lng)


def to_owner(r: OwnerRow) -> Owner:
    return Owner(
        id=r.id,
        name=r.name,
        initials=r.initials,
        kind=r.kind,
        district=r.district,
        country=r.country or "DE",
        verified=r.verified,
        rating_sum=r.rating_sum,
        jobs_done=r.jobs_done,
        on_time_jobs=r.on_time_jobs,
        joined_year=r.joined_year,
        response_mins=r.response_mins,
        response_rate=r.response_rate,
        renter_rating_sum=r.renter_rating_sum or 0,
        renter_jobs=r.renter_jobs or 0,
        # A person's address is never public; a trader's must be.
        business=r.business if r.kind == "business" and r.business else None,
        cancellation_rate=r.cancellation_rate,
    )


def to_listing(r: ListingRow, *, private: bool = False) -> AnyListing:
    """``private`` for the owner's own views: hand-over instructions (door
    codes, where the key is) are never in a public answer; renters get them
    with the address once a booking is accepted (/internal/.../handover)."""
    data = {
        "id": r.id,
        "ownerId": r.owner_id,
        "category": r.category,
        "mode": r.mode,
        "title": r.title,
        "blurb": r.blurb,
        "district": r.district,
        "instructions": r.instructions if private else "",
        "rules": r.rules,
        "active": r.active,
        **r.spec,
    }
    if r.photos:
        data["photos"] = r.photos
    if not private:
        # Where exactly and the postal code wait for an accepted booking (M-6).
        data.pop("postalCode", None)
        if data.get("location"):
            data["location"] = snapped(Location.model_validate(data["location"])).model_dump()
    return _listing.validate_python(data)


def to_slot(r: SlotRow) -> Slot:
    return Slot(
        id=r.id,
        listing_id=r.listing_id,
        start=iso_from_datetime(r.start),
        end=iso_from_datetime(r.end),
        hours_usable=r.hours_usable,
    )


def to_review(r: ReviewRow) -> Review:
    return Review(
        id=r.id,
        listing_id=r.listing_id,
        owner_id=r.owner_id,
        author=r.author,
        initials=r.initials,
        author_id=r.author_id,
        rating=r.rating,
        on_time=r.on_time,
        text=r.text,
        tags=list(r.tags or []),
        at=iso_from_datetime(r.at),
    )


# Free text inside a listing's spec, cleared when its owner's account goes.
_SPEC_WORDS = ("extraLabel", "machine")


def _spec(l: AnyListing) -> dict:
    data = l.model_dump(mode="json", by_alias=True, exclude_none=True)
    return {k: v for k, v in data.items() if k not in _BASE_FIELDS}


@dataclass(frozen=True)
class ReviewStats:
    count: int
    average: float | None
    on_time_share: float | None
    top_tags: list[tuple[str, int]]


@dataclass(frozen=True)
class CityRow:
    metro: str
    country: str
    lat: float
    lng: float
    listings: int


NEAREST_DISTRICTS = 200


class CatalogRepository:
    def __init__(self, session: AsyncSession, *, bookable_only: bool = False) -> None:
        self.s = session
        self.bookable_only = bookable_only

    def _bookable(self) -> list:
        """With ``bookable_only``, listings of owners payments cannot pay are
        not offered to buyers at all."""
        if not self.bookable_only:
            return []
        return [ListingRow.owner_id.in_(select(PayableOwnerRow.owner_id).where(PayableOwnerRow.ready))]

    async def forget(self, owner_id: str) -> None:
        """An account deletion: their listings come down, their shortlist goes,
        and their profile keeps only an anonymous shell, so bookings and
        reviews that point at it still make sense to the other side."""
        now = _now()
        # Their listings' words and photos too (D-2): instructions can hold a
        # door code. The row stays so reviews and bookings still point at it.
        await self.s.execute(
            update(ListingRow)
            .where(ListingRow.owner_id == owner_id)
            .values(
                deleted_at=func.coalesce(ListingRow.deleted_at, now),
                active=False,
                updated_at=now,
                address=None,
                title="Removed listing",
                blurb="",
                instructions="",
                rules=[],
                photos=[],
            )
        )
        # The spec's own words too (what the extra is, which machine): the
        # numbers stay so an old booking's listing still reads as one.
        for row in (await self.s.execute(select(ListingRow).where(ListingRow.owner_id == owner_id))).scalars():
            words = {k: "" for k in _SPEC_WORDS if k in (row.spec or {})}
            if words:
                row.spec = {**row.spec, **words}
        # Every photo they uploaded, listing or hand-over (D-1): the hourly
        # sweep deletes the files, keeping any another person also holds.
        await self.s.execute(update(MediaRow).where(MediaRow.owner_id == owner_id).values(used=False, created_at=EPOCH))
        # Reports they filed keep the case (DSA records), not the reporter (D-3).
        await self.s.execute(
            update(ReportRow)
            .where(ReportRow.reporter_id == owner_id)
            .values(reporter_id=None, reporter_email=None, details="[removed: the account was deleted]")
        )
        await idempotency.forget(self.s, IDEMPOTENCY, owner_id)
        await self.s.execute(delete(SavedRow).where(SavedRow.user_id == owner_id))
        await self.s.execute(delete(PayableOwnerRow).where(PayableOwnerRow.owner_id == owner_id))
        await self.s.execute(
            update(OwnerRow)
            .where(OwnerRow.id == owner_id)
            .values(
                name="Former member",
                initials="—",
                updated_at=now,
                deleted_at=now,
                business=None,
                verified=False,
                cancellation_rate=None,
                response_mins=None,
                response_rate=None,
            )
        )
        await self.s.execute(
            update(ReviewRow)
            .where(ReviewRow.author_id == owner_id)
            .values(author="Former member", initials="—", author_id=None)
        )

    async def export(self, owner_id: str) -> dict:
        """Everything the catalog holds about them (GDPR art. 15/20)."""
        owner = await self.find_owner(owner_id)
        listings = (await self.s.execute(select(ListingRow).where(ListingRow.owner_id == owner_id))).scalars()
        saved = (await self.s.execute(select(SavedRow).where(SavedRow.user_id == owner_id))).scalars()
        reviews = (await self.s.execute(select(ReviewRow).where(ReviewRow.author_id == owner_id))).scalars()
        about = (await self.s.execute(select(ReviewRow).where(ReviewRow.owner_id == owner_id).limit(10_000))).scalars()
        media = (await self.s.execute(select(MediaRow).where(MediaRow.owner_id == owner_id))).scalars()
        filed = (await self.s.execute(select(ReportRow).where(ReportRow.reporter_id == owner_id))).scalars()
        decided = (
            await self.s.execute(
                select(ModerationActionRow).where(
                    # Decisions about them, their listings, messages and reviews;
                    # rows from before person_id matched by target.
                    (ModerationActionRow.person_id == owner_id)
                    | ModerationActionRow.target_id.in_(
                        select(ListingRow.id).where(ListingRow.owner_id == owner_id).scalar_subquery()
                    )
                    | (ModerationActionRow.target_id == owner_id)
                )
            )
        ).scalars()
        return {
            "profile": owner.model_dump(mode="json", by_alias=True) if owner else None,
            "listings": [to_listing(r, private=True).model_dump(mode="json", by_alias=True) for r in listings],
            "saved": [{"listingId": r.listing_id, "savedAt": r.saved_at.isoformat()} for r in saved],
            "reviewsWritten": [
                {"listingId": r.listing_id, "rating": r.rating, "text": r.text, "at": r.at.isoformat()} for r in reviews
            ],
            "reviewsAboutMe": [
                {"listingId": r.listing_id, "rating": r.rating, "text": r.text, "at": r.at.isoformat()} for r in about
            ],
            # The files themselves: each name is fetched at /media/<name> (D-10).
            "photos": [{"name": r.name, "createdAt": r.created_at.isoformat()} for r in media],
            "reportsFiled": [
                {
                    "targetType": r.target_type,
                    "targetId": r.target_id,
                    "reason": r.reason,
                    "details": r.details,
                    "email": r.reporter_email,
                    "status": r.status,
                    "at": r.created_at.isoformat(),
                }
                for r in filed
            ],
            "moderationDecisionsAboutMe": [
                {
                    "action": a.action,
                    "targetType": a.target_type,
                    "targetId": a.target_id,
                    "statement": a.statement,
                    "statementOfReasons": a.statement_of_reasons,
                    "at": a.at.isoformat(),
                }
                for a in decided
            ],
        }

    async def set_payable(self, owner_id: str, ready: bool, as_of: datetime) -> None:
        row = await self.s.get(PayableOwnerRow, owner_id, with_for_update=True)
        if row is None:
            self.s.add(PayableOwnerRow(owner_id=owner_id, ready=ready, as_of=as_of))
        elif as_of > row.as_of:
            row.ready, row.as_of = ready, as_of
        await self.s.flush()

    # --- districts and places ---------------------------------------------------

    async def districts(self) -> dict[str, District]:
        rows = (await self.s.execute(select(DistrictRow).order_by(DistrictRow.name))).scalars()
        return {r.name: to_district(r) for r in rows}

    async def district(self, name: str) -> District:
        row = await self.s.get(DistrictRow, name)
        if not row:
            raise NotFound(f"unknown district: {name}")
        return to_district(row)

    async def has_district(self, name: str) -> bool:
        return await self.s.get(DistrictRow, name) is not None

    async def cities(self) -> list[CityRow]:
        """One row per metro with how many live listings it has, busiest first.
        An aggregate over indexed columns, not a scan of every listing's slots."""
        live = and_(ListingRow.deleted_at.is_(None), ListingRow.active.is_(True))
        q = (
            select(
                DistrictRow.metro,
                func.min(DistrictRow.country),
                func.avg(DistrictRow.lat),
                func.avg(DistrictRow.lng),
                func.count(ListingRow.id),
            )
            .join(ListingRow, and_(ListingRow.district == DistrictRow.name, live), isouter=True)
            .group_by(DistrictRow.metro)
        )
        rows = [CityRow(m, c, float(la), float(ln), int(n)) for m, c, la, ln, n in (await self.s.execute(q)).all()]
        return sorted(rows, key=lambda r: (-r.listings, r.metro))

    async def nearest_district(self, lat: float, lng: float) -> tuple[District, float] | None:
        """Districts are a small reference table (hundreds of rows, not
        millions), so ranking them in memory is the simple, correct answer."""
        from .geo import haversine_km

        best: tuple[District, float] | None = None
        for d in (await self.districts()).values():
            km = haversine_km(lat, lng, d.lat, d.lng)
            if best is None or km < best[1]:
                best = (d, km)
        return best

    # --- owners and profiles -------------------------------------------------------

    async def find_owner(self, owner_id: str) -> Owner | None:
        row = await self.s.get(OwnerRow, owner_id)
        return to_owner(row) if row and row.deleted_at is None else None

    async def listings_since(self, owner_id: str, since: datetime) -> int:
        q = select(func.count()).where(ListingRow.owner_id == owner_id, ListingRow.created_at >= since)
        return (await self.s.execute(q)).scalar_one()

    async def held_ids(self, listing_ids: set[str]) -> set[str]:
        if not listing_ids:
            return set()
        q = select(ListingRow.id).where(ListingRow.id.in_(listing_ids), ListingRow.held_at.is_not(None))
        return set((await self.s.execute(q)).scalars())

    async def hold(self, listing_id: str) -> None:
        row = await self.s.get(ListingRow, listing_id)
        row.held_at = _now()
        await self.s.flush()

    async def is_suspended(self, owner_id: str) -> bool:
        row = await self.s.get(OwnerRow, owner_id)
        return row is not None and row.suspended_at is not None

    async def owner(self, owner_id: str) -> Owner:
        found = await self.find_owner(owner_id)
        if not found:
            raise NotFound(f"owner {owner_id} not found")
        return found

    async def owners(self, ids: set[str]) -> dict[str, Owner]:
        if not ids:
            return {}
        rows = (await self.s.execute(select(OwnerRow).where(OwnerRow.id.in_(ids)))).scalars()
        return {r.id: to_owner(r) for r in rows}

    async def upsert_profile(
        self,
        owner_id: str,
        *,
        name: str,
        initials: str,
        kind: str,
        district: str,
        business: dict | None = None,
        adult: bool = False,
        minimum_age: int = 18,
        country: str = "DE",
    ) -> tuple[Owner, bool]:
        """Create a person's profile on first use, or update the fields they
        control. A track record is earned, never set: rating and job counts are
        untouched by an update. Returns (owner, created). A new profile needs
        the 18+ confirmation; one made before the question keeps its own."""
        now = _now()
        row = await self.s.get(OwnerRow, owner_id, with_for_update=True)
        fresh = row is not None and row.deleted_at is not None
        if row is None or row.adult_confirmed_at is None or fresh:
            if not adult:
                raise Invalid(f"Cappy is for people aged {minimum_age} or over: confirm your age to continue")
        if fresh:
            # The same sign-in after an account deletion (FL-11): a fresh start,
            # nothing of the old record comes back. A suspension does stay.
            row.deleted_at, row.verified, row.business, row.cancellation_rate = None, False, None, None
            row.rating_sum = row.jobs_done = row.on_time_jobs = row.renter_rating_sum = row.renter_jobs = 0
            row.response_mins = row.response_rate = None
            row.joined_year, row.created_at, row.adult_confirmed_at = now.year, now, now
        if row is None:
            row = OwnerRow(
                business=business,
                adult_confirmed_at=now,
                id=owner_id,
                name=name,
                initials=initials,
                kind=kind,
                district=district,
                country=country,
                verified=False,
                rating_sum=0,
                jobs_done=0,
                on_time_jobs=0,
                joined_year=now.year,
                created_at=now,
                updated_at=now,
            )
            self.s.add(row)
            await self.s.flush()
            return to_owner(row), True
        row.name, row.initials, row.kind, row.district, row.updated_at = name, initials, kind, district, now
        row.country = country
        row.business = business
        row.adult_confirmed_at = row.adult_confirmed_at or now
        await self.s.flush()
        return to_owner(row), fresh

    async def apply_renter_rating(self, renter_id: str, quality: int) -> None:
        """Atomic, like apply_outcome. A renter without a profile has no record to move."""
        await self.s.execute(
            update(OwnerRow)
            .where(OwnerRow.id == renter_id)
            .values(renter_rating_sum=OwnerRow.renter_rating_sum + quality, renter_jobs=OwnerRow.renter_jobs + 1)
        )

    async def apply_outcome(self, owner_id: str, outcome: Outcome) -> None:
        """One atomic UPDATE: no read-modify-write, so concurrent ratings can
        never overwrite each other's increment."""
        result = await self.s.execute(
            update(OwnerRow)
            .where(OwnerRow.id == owner_id)
            .values(
                rating_sum=OwnerRow.rating_sum + outcome.quality,
                jobs_done=OwnerRow.jobs_done + 1,
                on_time_jobs=OwnerRow.on_time_jobs + (1 if outcome.on_time else 0),
                updated_at=_now(),
            )
        )
        if result.rowcount == 0:
            raise NotFound(f"owner {owner_id} not found")

    # --- listings ------------------------------------------------------------------

    def _live(self):
        return ListingRow.deleted_at.is_(None) & ListingRow.moderated_at.is_(None) & ListingRow.held_at.is_(None)

    async def listing_row(
        self, listing_id: str, *, include_deleted: bool = False, include_held: bool = False
    ) -> ListingRow:
        row = await self.s.get(ListingRow, listing_id)
        held = row is not None and row.held_at is not None and not include_held
        hidden = row is not None and ((row.deleted_at or row.moderated_at) is not None or held)
        if not row or (hidden and not include_deleted):
            raise NotFound(f"listing {listing_id} not found")
        return row

    async def listing(self, listing_id: str) -> AnyListing:
        return to_listing(await self.listing_row(listing_id))

    async def listings_by_owner(
        self, owner_id: str, *, cursor: str | None, limit: int
    ) -> tuple[list[AnyListing], str | None]:
        # The owner sees their listings waiting for review too.
        mine = ListingRow.deleted_at.is_(None) & ListingRow.moderated_at.is_(None)
        q = select(ListingRow).where(ListingRow.owner_id == owner_id, mine)
        key = decode_cursor(cursor)
        if key:
            at = dt_from_iso(key["at"])
            q = q.where(or_(ListingRow.created_at < at, and_(ListingRow.created_at == at, ListingRow.id < key["id"])))
        rows = list(
            (
                await self.s.execute(q.order_by(ListingRow.created_at.desc(), ListingRow.id.desc()).limit(limit + 1))
            ).scalars()
        )
        more = len(rows) > limit
        rows = rows[:limit]
        nxt = encode_cursor({"at": rows[-1].created_at.isoformat(), "id": rows[-1].id}) if more else None
        return [to_listing(r, private=True) for r in rows], nxt

    async def create_listing(self, listing: AnyListing, slots: list[Slot]) -> tuple[AnyListing, list[Slot]]:
        """Mints the ids. Whatever ids the client sent are ignored."""
        now = _now()
        listing_id = new_id("ls")
        row = ListingRow(
            id=listing_id,
            owner_id=listing.owner_id,
            category=listing.category,
            mode=listing.mode,
            title=listing.title,
            blurb=listing.blurb,
            district=listing.district,
            instructions=listing.instructions,
            rules=listing.rules,
            photos=listing.photos or [],
            active=listing.active,
            spec=_spec(listing),
            created_at=now,
            updated_at=now,
        )
        self.s.add(row)
        await self.s.flush()
        saved = [await self._add_slot(listing_id, s) for s in slots]
        await self.s.flush()
        return to_listing(row, private=True), saved

    async def update_listing(self, listing_id: str, listing: AnyListing) -> AnyListing:
        row = await self.listing_row(listing_id, include_held=True)
        row.title, row.blurb, row.instructions = listing.title, listing.blurb, listing.instructions
        row.rules, row.photos, row.district = listing.rules, listing.photos or [], listing.district
        row.spec, row.updated_at = _spec(listing), _now()
        await self.s.flush()
        return to_listing(row, private=True)

    async def set_address(self, listing_id: str, address: str | None) -> None:
        row = await self.listing_row(listing_id, include_held=True)
        row.address = (address or "").strip() or None
        await self.s.flush()

    async def addresses(self, listing_ids: set[str]) -> dict[str, str]:
        if not listing_ids:
            return {}
        q = select(ListingRow.id, ListingRow.address).where(
            ListingRow.id.in_(listing_ids), ListingRow.address.is_not(None)
        )
        return dict((await self.s.execute(q)).all())

    async def set_active(self, listing_id: str, active: bool) -> AnyListing:
        row = await self.listing_row(listing_id, include_held=True)
        row.active, row.updated_at = active, _now()
        await self.s.flush()
        return to_listing(row, private=True)

    async def soft_delete(self, listing_id: str) -> None:
        row = await self.listing_row(listing_id, include_held=True)
        row.deleted_at = row.updated_at = _now()
        row.active = False
        # Hearts on something that is gone help nobody; its reviews stay, so the
        # owner's record keeps the evidence it was built from.
        await self.s.execute(delete(SavedRow).where(SavedRow.listing_id == listing_id))

    # --- slots -----------------------------------------------------------------------

    async def _add_slot(self, listing_id: str, s: Slot) -> Slot:
        slot_id = new_id("sl")
        self.s.add(
            SlotRow(
                id=slot_id,
                listing_id=listing_id,
                start=dt_from_iso(s.start),
                end=dt_from_iso(s.end),
                hours_usable=s.hours_usable,
            )
        )
        return s.model_copy(update={"id": slot_id, "listing_id": listing_id})

    async def add_slots(self, listing_id: str, slots: list[Slot]) -> list[Slot]:
        out = [await self._add_slot(listing_id, s) for s in slots]
        await self.s.flush()
        return out

    async def apply_schedule(
        self, listing_id: str, availability: Availability | None, now: datetime, *, replace: bool
    ) -> int:
        """Windows from the weekly schedule, up to eight weeks ahead (H-4).
        ``replace`` (the owner changed the schedule): the windows it made
        before that have not ended go first. Bookings are the booking service's: a window
        removed under one leaves the booking as it is. Rolling on (``replace``
        false) only adds, so an offer a buyer is looking at keeps its window.
        Never overlaps a window already there. Returns how many it added."""
        row = await self.s.get(ListingRow, listing_id, with_for_update=True)
        if row is None:
            return 0
        if replace:
            await self.s.execute(
                delete(SlotRow).where(SlotRow.listing_id == listing_id, SlotRow.generated, SlotRow.end > now)
            )
        if availability is None:
            row.scheduled_until = None
            return 0
        until = now + schedule.HORIZON
        taken = [
            (r.start, r.end)
            for r in (
                await self.s.execute(select(SlotRow).where(SlotRow.listing_id == listing_id, SlotRow.end > now))
            ).scalars()
        ]
        added = 0
        for start, end in schedule.free_of(schedule.windows(availability, now, until), taken):
            self.s.add(
                SlotRow(
                    id=new_id("sl"),
                    listing_id=listing_id,
                    start=start,
                    end=end,
                    hours_usable=(end - start).total_seconds() / 3600,
                    generated=True,
                )
            )
            added += 1
        row.scheduled_until = until
        await self.s.flush()
        return added

    async def schedules_due(self, now: datetime, limit: int) -> list[tuple[str, dict]]:
        """Scheduled listings whose windows reach less than a week short of
        the horizon: the job rolls them on, a day or so at a time."""
        rows = (
            await self.s.execute(
                select(ListingRow.id, ListingRow.spec)
                .where(
                    ListingRow.scheduled_until < now + schedule.HORIZON - timedelta(days=1),
                    ListingRow.deleted_at.is_(None),
                )
                .order_by(ListingRow.scheduled_until)
                .limit(limit)
            )
        ).all()
        return [(r.id, r.spec) for r in rows]

    async def idle_listings(self, now: datetime, limit: int) -> list[ListingRow]:
        """Live listings with no window open in the next seven days whose owner
        has not been told this week (H-4): a listing that went dark."""
        soon = now + timedelta(days=7)
        has_time = exists().where(SlotRow.listing_id == ListingRow.id, SlotRow.end > now, SlotRow.start < soon)
        q = (
            select(ListingRow)
            .where(
                ListingRow.deleted_at.is_(None),
                ListingRow.active,
                ListingRow.held_at.is_(None),
                or_(ListingRow.idle_notice_at.is_(None), ListingRow.idle_notice_at < now - timedelta(days=7)),
                ~has_time,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.s.execute(q)).scalars())

    async def remove_slot(self, listing_id: str, slot_id: str) -> None:
        result = await self.s.execute(delete(SlotRow).where(SlotRow.id == slot_id, SlotRow.listing_id == listing_id))
        if result.rowcount == 0:
            raise NotFound(f"slot {slot_id} not found on listing {listing_id}")

    async def upcoming_slots(
        self, listing_ids: set[str], *, after: datetime, until: datetime | None = None, per_listing: int = 200
    ) -> list[Slot]:
        if not listing_ids:
            return []
        q = select(SlotRow).where(SlotRow.listing_id.in_(listing_ids), SlotRow.end > after)
        if until is not None:
            q = q.where(SlotRow.start < until)
        rows = (await self.s.execute(q.order_by(SlotRow.listing_id, SlotRow.start))).scalars()
        kept: dict[str, int] = {}
        out = []
        for r in rows:
            n = kept.get(r.listing_id, 0)
            if n < per_listing:
                out.append(to_slot(r))
                kept[r.listing_id] = n + 1
        return out

    # --- search: the candidate set (ADR 0001) ------------------------------------------

    async def candidates(
        self,
        *,
        origin: District,
        max_km: float,
        start: datetime,
        until: datetime,
        category: str | None,
        cap: int,
        exclude_owner: str | None = None,
    ) -> World:
        """The listings that could possibly answer a search, and only what they
        reference: live, in the category, inside a bounding box around the
        origin, with an idle window overlapping the requested time. Nearest
        first, capped. Exact distance and feasibility are decided afterwards by
        the domain rules, on this small set.
        """
        dlat = max_km / KM_PER_DEG_LAT
        dlng = max_km / max(1e-6, 111.320 * math.cos(math.radians(origin.lat)))
        coslat = math.cos(math.radians(origin.lat))
        # Squared degree distance is monotone in real distance at these scales:
        # good enough to pick the nearest `cap`; the domain computes km exactly.
        nearness = (DistrictRow.lat - origin.lat) * (DistrictRow.lat - origin.lat) + (
            (DistrictRow.lng - origin.lng) * coslat
        ) * ((DistrictRow.lng - origin.lng) * coslat)
        # Districts nearest first (a small table), and for each only as many
        # listings as are still needed: the scan stops once `cap` are found, so
        # an EU-wide search costs what a local one does (resilience F10),
        # instead of sorting every match in the box.
        near = (
            select(DistrictRow.name.label("district"), nearness.label("nearness"))
            .where(
                DistrictRow.lat.between(origin.lat - dlat, origin.lat + dlat),
                DistrictRow.lng.between(origin.lng - dlng, origin.lng + dlng),
            )
            # The nearest districts are plenty to find `cap` listings; this bounds
            # the work however wide the radius or however many districts exist.
            .order_by(nearness)
            .limit(NEAREST_DISTRICTS)
            .subquery("near")
        )
        conds = [
            ListingRow.district == near.c.district,
            self._live(),
            ListingRow.active.is_(True),
            exists().where(SlotRow.listing_id == ListingRow.id, SlotRow.end > start, SlotRow.start < until),
            *self._bookable(),
        ]
        if category:
            conds.append(ListingRow.category == category)
        if exclude_owner:
            conds.append(ListingRow.owner_id != exclude_owner)
        if self.s.bind.dialect.name == "postgresql":
            # No ORDER BY inside: any `cap` listings of one district are equally
            # near, and without one the (category, district) index answers it.
            per_district = select(ListingRow.id).where(*conds).limit(cap).lateral("pick")
            ids_q = (
                select(per_district.c.id)
                .select_from(near.join(per_district, true()))
                .order_by(near.c.nearness, per_district.c.id)
                .limit(cap)
            )
        else:
            # SQLite (tests) has no LATERAL; its data is small enough to sort.
            ids_q = (
                select(ListingRow.id)
                .select_from(near)
                .where(*conds)
                .order_by(near.c.nearness, ListingRow.id)
                .limit(cap)
            )
        ids = list((await self.s.execute(ids_q)).scalars())
        order = {lid: i for i, lid in enumerate(ids)}
        q = (
            select(ListingRow, DistrictRow)
            .join(DistrictRow, DistrictRow.name == ListingRow.district)
            .where(ListingRow.id.in_(ids))
        )
        pairs = sorted((await self.s.execute(q)).all(), key=lambda p: order[p[0].id])
        listings = [to_listing(l) for l, _ in pairs]
        districts = {origin.name: origin, **{d.name: to_district(d) for _, d in pairs}}
        owners = await self.owners({l.owner_id for l in listings})
        slots = await self.upcoming_slots({l.id for l in listings}, after=start, until=until)
        return World(
            owners=list(owners.values()),
            listings=listings,
            slots=slots,
            districts=districts,
            reviews=[],
        )

    async def listing_context(self, listing_id: str, *, after: datetime, origin: str | None = None) -> World:
        """One listing and everything needed to price and schedule it. A
        paused listing has nothing to offer anyone."""
        listing = await self.listing(listing_id)
        if not listing.active:
            raise NotFound(f"listing {listing_id} is not taking bookings")
        owner = await self.owner(listing.owner_id)
        names = {listing.district} | ({origin} if origin else set())
        rows = (await self.s.execute(select(DistrictRow).where(DistrictRow.name.in_(names)))).scalars()
        return World(
            owners=[owner],
            listings=[listing],
            slots=await self.upcoming_slots({listing_id}, after=after),
            districts={r.name: to_district(r) for r in rows},
            reviews=[],
        )

    async def search(
        self, *, q: str, metro: str | None, category: str | None, cursor: str | None, limit: int
    ) -> tuple[list[AnyListing], str | None]:
        """Free-text search over titles and blurbs. A trigram index backs the
        ILIKE on Postgres (see the migration)."""
        needle = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        conds = [
            self._live(),
            ListingRow.active.is_(True),
            *self._bookable(),
            or_(
                func.lower(ListingRow.title).like(needle, escape="\\"),
                func.lower(ListingRow.blurb).like(needle, escape="\\"),
            ),
        ]
        stmt = select(ListingRow)
        if metro:
            stmt = stmt.join(DistrictRow, DistrictRow.name == ListingRow.district)
            conds.append(DistrictRow.metro == metro)
        if category:
            conds.append(ListingRow.category == category)
        key = decode_cursor(cursor)
        if key:
            at = dt_from_iso(key["at"])
            conds.append(or_(ListingRow.created_at < at, and_(ListingRow.created_at == at, ListingRow.id < key["id"])))
        rows = list(
            (
                await self.s.execute(
                    stmt.where(*conds).order_by(ListingRow.created_at.desc(), ListingRow.id.desc()).limit(limit + 1)
                )
            ).scalars()
        )
        more = len(rows) > limit
        rows = rows[:limit]
        nxt = encode_cursor({"at": rows[-1].created_at.isoformat(), "id": rows[-1].id}) if more else None
        return [to_listing(r) for r in rows], nxt

    # --- reviews ----------------------------------------------------------------------

    async def reviews(self, listing_id: str, *, cursor: str | None, limit: int) -> tuple[list[Review], str | None]:
        q = select(ReviewRow).where(ReviewRow.listing_id == listing_id)
        key = decode_cursor(cursor)
        if key:
            at = dt_from_iso(key["at"])
            q = q.where(or_(ReviewRow.at < at, and_(ReviewRow.at == at, ReviewRow.id > key["id"])))
        rows = list((await self.s.execute(q.order_by(ReviewRow.at.desc(), ReviewRow.id).limit(limit + 1))).scalars())
        more = len(rows) > limit
        rows = rows[:limit]
        nxt = encode_cursor({"at": rows[-1].at.isoformat(), "id": rows[-1].id}) if more else None
        return [to_review(r) for r in rows], nxt

    async def review_stats(self, listing_id: str, *, tag_window: int = 500) -> ReviewStats:
        count, avg, on_time = (
            await self.s.execute(
                select(
                    func.count(ReviewRow.id),
                    func.avg(ReviewRow.rating),
                    func.avg(cast(ReviewRow.on_time, Integer)),
                ).where(ReviewRow.listing_id == listing_id)
            )
        ).one()
        if not count:
            return ReviewStats(0, None, None, [])
        # Tags from the most recent reviews: what people say now, bounded.
        recent = (
            await self.s.execute(
                select(ReviewRow.tags)
                .where(ReviewRow.listing_id == listing_id)
                .order_by(ReviewRow.at.desc())
                .limit(tag_window)
            )
        ).scalars()
        counts: dict[str, int] = {}
        for tags in recent:
            for t in tags or []:
                counts[t] = counts.get(t, 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        return ReviewStats(int(count), float(avg), float(on_time), top)

    async def has_review(self, review_id: str) -> bool:
        return await self.s.get(ReviewRow, review_id) is not None

    async def add_review(self, review: Review) -> None:
        self.s.add(
            ReviewRow(
                id=review.id,
                listing_id=review.listing_id,
                owner_id=review.owner_id,
                author=review.author,
                initials=review.initials,
                author_id=review.author_id,
                rating=review.rating,
                on_time=review.on_time,
                text=review.text,
                tags=review.tags,
                at=dt_from_iso(review.at),
            )
        )
        await self.s.flush()

    # --- saved ---------------------------------------------------------------------------

    async def saved(self, user_id: str, *, cursor: str | None, limit: int) -> tuple[list[AnyListing], str | None]:
        q = (
            select(ListingRow, SavedRow.saved_at)
            .join(SavedRow, SavedRow.listing_id == ListingRow.id)
            .where(SavedRow.user_id == user_id, self._live())
        )
        key = decode_cursor(cursor)
        if key:
            at = dt_from_iso(key["at"])
            q = q.where(or_(SavedRow.saved_at < at, and_(SavedRow.saved_at == at, SavedRow.listing_id < key["id"])))
        rows = list(
            (
                await self.s.execute(q.order_by(SavedRow.saved_at.desc(), SavedRow.listing_id.desc()).limit(limit + 1))
            ).all()
        )
        more = len(rows) > limit
        rows = rows[:limit]
        nxt = encode_cursor({"at": rows[-1][1].isoformat(), "id": rows[-1][0].id}) if more else None
        return [to_listing(r) for r, _ in rows], nxt

    async def saved_ids(self, user_id: str, listing_ids: set[str]) -> set[str]:
        if not listing_ids:
            return set()
        q = select(SavedRow.listing_id).where(SavedRow.user_id == user_id, SavedRow.listing_id.in_(listing_ids))
        return set((await self.s.execute(q)).scalars())

    async def save(self, user_id: str, listing_id: str) -> None:
        """Idempotent: hearting twice is one heart."""
        if await self.s.get(SavedRow, (user_id, listing_id)) is None:
            self.s.add(SavedRow(user_id=user_id, listing_id=listing_id, saved_at=_now()))
            await self.s.flush()

    async def unsave(self, user_id: str, listing_id: str) -> None:
        await self.s.execute(delete(SavedRow).where(SavedRow.user_id == user_id, SavedRow.listing_id == listing_id))

    # --- media ------------------------------------------------------------------------------

    async def record_media(self, name: str, owner_id: str, size: int, width: int, height: int) -> None:
        if await self.s.get(MediaRow, (name, owner_id)) is None:
            self.s.add(
                MediaRow(name=name, owner_id=owner_id, bytes=size, width=width, height=height, created_at=_now())
            )
            await self.s.flush()

    async def uploads_since(self, owner_id: str, since: datetime) -> int:
        q = select(func.count()).where(MediaRow.owner_id == owner_id, MediaRow.created_at >= since)
        return (await self.s.execute(q)).scalar_one()

    async def mark_used(self, names: set[str], owner_id: str) -> None:
        if names:
            await self.s.execute(
                update(MediaRow).where(MediaRow.name.in_(names), MediaRow.owner_id == owner_id).values(used=True)
            )

    async def orphans(self, older_than: datetime, limit: int) -> list[MediaRow]:
        q = (
            select(MediaRow)
            .where(MediaRow.used.is_(False), MediaRow.created_at < older_than)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.s.execute(q)).scalars())

    async def still_held(self, name: str) -> bool:
        return (await self.s.execute(select(MediaRow.name).where(MediaRow.name == name).limit(1))).first() is not None

    async def media_owned_by(self, names: set[str], owner_id: str) -> set[str]:
        if not names:
            return set()
        q = select(MediaRow.name).where(MediaRow.name.in_(names), MediaRow.owner_id == owner_id)
        return set((await self.s.execute(q)).scalars())

    # --- the demo world (ADR 0010: a developer tool, additive only) -------------------------

    async def load_seed(self, world: World) -> dict[str, int]:
        """Insert whatever of the demo world is missing. Never updates, never
        deletes: running it against a database with real data changes nothing
        that is already there."""
        added = {"districts": 0, "owners": 0, "listings": 0, "slots": 0, "reviews": 0}
        now = _now()
        have = set((await self.s.execute(select(DistrictRow.name))).scalars())
        for d in world.districts.values():
            if d.name not in have:
                self.s.add(DistrictRow(**d.model_dump(by_alias=False)))
                added["districts"] += 1
        await self.s.flush()
        have = set((await self.s.execute(select(OwnerRow.id))).scalars())
        for o in world.owners:
            if o.id not in have:
                self.s.add(
                    OwnerRow(**o.model_dump(by_alias=False), created_at=now, updated_at=now, adult_confirmed_at=now)  # type: ignore[arg-type]
                )
                added["owners"] += 1
        await self.s.flush()
        have = set((await self.s.execute(select(ListingRow.id))).scalars())
        fresh = set()
        for l in world.listings:
            if l.id not in have:
                fresh.add(l.id)
                self.s.add(
                    ListingRow(
                        id=l.id,
                        owner_id=l.owner_id,
                        category=l.category,
                        mode=l.mode,
                        title=l.title,
                        blurb=l.blurb,
                        district=l.district,
                        instructions=l.instructions,
                        rules=l.rules,
                        photos=l.photos or [],
                        active=l.active,
                        spec=_spec(l),
                        created_at=now,
                        updated_at=now,
                    )
                )
                added["listings"] += 1
        await self.s.flush()
        for s in world.slots:
            if s.listing_id in fresh:
                self.s.add(
                    SlotRow(
                        id=s.id,
                        listing_id=s.listing_id,
                        start=dt_from_iso(s.start),
                        end=dt_from_iso(s.end),
                        hours_usable=s.hours_usable,
                    )
                )
                added["slots"] += 1
        for r in world.reviews:
            if r.listing_id in fresh:
                await self.s.execute(
                    insert(ReviewRow).values(
                        id=r.id,
                        listing_id=r.listing_id,
                        owner_id=r.owner_id,
                        author=r.author,
                        initials=r.initials,
                        author_id=r.author_id,
                        rating=r.rating,
                        on_time=r.on_time,
                        text=r.text,
                        tags=r.tags,
                        at=dt_from_iso(r.at),
                    )
                )
                added["reviews"] += 1
        await self.s.flush()
        return added
