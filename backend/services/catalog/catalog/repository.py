"""All reads and writes against the catalog tables, translated to domain models."""

from __future__ import annotations

from pydantic import TypeAdapter
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.errors import NotFound
from cappy_common.models import (
    AnyListing,
    District,
    Listing,
    Outcome,
    Owner,
    Review,
    Slot,
    World,
    apply_outcome,
)
from cappy_common.timeutil import now_iso

from .tables import DistrictRow, ListingRow, MetaRow, OwnerRow, ReviewRow, SavedRow, SlotRow

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
}


def _to_district(r: DistrictRow) -> District:
    return District(name=r.name, city=r.city, metro=r.metro, country=r.country, lat=r.lat, lng=r.lng)


def _to_owner(r: OwnerRow) -> Owner:
    return Owner(
        id=r.id,
        name=r.name,
        initials=r.initials,
        kind=r.kind,
        district=r.district,
        verified=r.verified,
        rating_sum=r.rating_sum,
        jobs_done=r.jobs_done,
        on_time_jobs=r.on_time_jobs,
        joined_year=r.joined_year,
        response_mins=r.response_mins,
    )


def _to_listing(r: ListingRow) -> AnyListing:
    return _listing.validate_python(
        {
            "id": r.id,
            "ownerId": r.owner_id,
            "category": r.category,
            "mode": r.mode,
            "title": r.title,
            "blurb": r.blurb,
            "district": r.district,
            "instructions": r.instructions,
            "rules": r.rules,
            "active": r.active,
            **r.spec,
        }
    )


def _to_slot(r: SlotRow) -> Slot:
    return Slot(id=r.id, listing_id=r.listing_id, start=r.start, end=r.end, hours_usable=r.hours_usable)


def _to_review(r: ReviewRow) -> Review:
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
        at=r.at,
    )


def _listing_row(l: AnyListing) -> ListingRow:
    # exclude_none: an absent tolerance is stored absent, and comes back absent.
    data = l.model_dump(mode="json", by_alias=True, exclude_none=True)
    spec = {k: v for k, v in data.items() if k not in _BASE_FIELDS}
    return ListingRow(
        id=l.id,
        owner_id=l.owner_id,
        category=l.category,
        mode=l.mode,
        title=l.title,
        blurb=l.blurb,
        district=l.district,
        instructions=l.instructions,
        rules=l.rules,
        active=l.active,
        spec=spec,
    )


def _slot_row(s: Slot) -> SlotRow:
    return SlotRow(id=s.id, listing_id=s.listing_id, start=s.start, end=s.end, hours_usable=s.hours_usable)


def _review_row(r: Review) -> ReviewRow:
    return ReviewRow(
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
        at=r.at,
    )


def _owner_row(o: Owner) -> OwnerRow:
    return OwnerRow(
        id=o.id,
        name=o.name,
        initials=o.initials,
        kind=o.kind,
        district=o.district,
        verified=o.verified,
        rating_sum=o.rating_sum,
        jobs_done=o.jobs_done,
        on_time_jobs=o.on_time_jobs,
        joined_year=o.joined_year,
        response_mins=o.response_mins,
    )


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    # --- reads ---------------------------------------------------------------

    async def districts(self) -> dict[str, District]:
        rows = (await self.s.execute(select(DistrictRow).order_by(DistrictRow.name))).scalars()
        return {r.name: _to_district(r) for r in rows}

    async def owners(self) -> list[Owner]:
        rows = (await self.s.execute(select(OwnerRow).order_by(OwnerRow.id))).scalars()
        return [_to_owner(r) for r in rows]

    async def owner(self, owner_id: str) -> Owner:
        row = await self.s.get(OwnerRow, owner_id)
        if not row:
            raise NotFound(f"owner {owner_id} not found")
        return _to_owner(row)

    async def find_owner(self, owner_id: str) -> Owner | None:
        row = await self.s.get(OwnerRow, owner_id)
        return _to_owner(row) if row else None

    async def listings(self, owner_id: str | None = None) -> list[AnyListing]:
        q = select(ListingRow).order_by(ListingRow.id)
        if owner_id:
            q = q.where(ListingRow.owner_id == owner_id)
        return [_to_listing(r) for r in (await self.s.execute(q)).scalars()]

    async def listing(self, listing_id: str) -> AnyListing:
        row = await self.s.get(ListingRow, listing_id)
        if not row:
            raise NotFound(f"listing {listing_id} not found")
        return _to_listing(row)

    async def slots(self, listing_id: str | None = None) -> list[Slot]:
        q = select(SlotRow).order_by(SlotRow.start, SlotRow.id)
        if listing_id:
            q = q.where(SlotRow.listing_id == listing_id)
        return [_to_slot(r) for r in (await self.s.execute(q)).scalars()]

    async def reviews(self, listing_id: str | None = None) -> list[Review]:
        """Newest first."""
        q = select(ReviewRow).order_by(ReviewRow.at.desc(), ReviewRow.id)
        if listing_id:
            q = q.where(ReviewRow.listing_id == listing_id)
        return [_to_review(r) for r in (await self.s.execute(q)).scalars()]

    async def has_review(self, review_id: str) -> bool:
        return await self.s.get(ReviewRow, review_id) is not None

    async def saved(self, user_id: str) -> list[str]:
        """Listing ids this person hearted, newest first."""
        q = (
            select(SavedRow.listing_id)
            .where(SavedRow.user_id == user_id)
            .order_by(SavedRow.saved_at.desc(), SavedRow.listing_id)
        )
        return list((await self.s.execute(q)).scalars())

    async def world(self) -> World:
        return World(
            owners=await self.owners(),
            listings=await self.listings(),
            slots=await self.slots(),
            districts=await self.districts(),
            reviews=await self.reviews(),
        )

    async def count_owners(self) -> int:
        return (await self.s.execute(select(func.count()).select_from(OwnerRow))).scalar_one()

    async def has_listing(self, listing_id: str) -> bool:
        return await self.s.get(ListingRow, listing_id) is not None

    async def get_meta(self, key: str) -> str | None:
        row = await self.s.get(MetaRow, key)
        return row.value if row else None

    # --- writes ----------------------------------------------------------------

    async def set_meta(self, key: str, value: str) -> None:
        row = await self.s.get(MetaRow, key)
        if row:
            row.value = value
        else:
            self.s.add(MetaRow(key=key, value=value))
        await self.s.flush()

    async def add_owner(self, owner: Owner) -> None:
        self.s.add(_owner_row(owner))
        await self.s.flush()

    async def add_listing(self, listing: AnyListing, slots: list[Slot]) -> None:
        # No relationship() is mapped, so the unit of work will not order the
        # inserts for us: flush the parent before the rows that reference it.
        self.s.add(_listing_row(listing))
        await self.s.flush()
        self.s.add_all([_slot_row(s) for s in slots])

    async def set_active(self, listing_id: str, active: bool) -> AnyListing:
        row = await self.s.get(ListingRow, listing_id)
        if not row:
            raise NotFound(f"listing {listing_id} not found")
        row.active = active
        await self.s.flush()
        return _to_listing(row)

    async def remove_listing(self, listing_id: str) -> None:
        row = await self.s.get(ListingRow, listing_id)
        if not row:
            raise NotFound(f"listing {listing_id} not found")
        # Explicit, rather than relying on ON DELETE CASCADE, so SQLite in tests
        # behaves exactly like Postgres. A removed listing takes its windows,
        # its reviews and everyone's heart on it with it, as the app does.
        for table in (SlotRow, ReviewRow, SavedRow):
            await self.s.execute(delete(table).where(table.listing_id == listing_id))
        await self.s.delete(row)

    async def add_review(self, review: Review) -> None:
        self.s.add(_review_row(review))
        await self.s.flush()

    async def save(self, user_id: str, listing_id: str) -> list[str]:
        """Idempotent: hearting twice is one heart."""
        if await self.s.get(SavedRow, (user_id, listing_id)) is None:
            self.s.add(SavedRow(user_id=user_id, listing_id=listing_id, saved_at=now_iso()))
            await self.s.flush()
        return await self.saved(user_id)

    async def unsave(self, user_id: str, listing_id: str) -> list[str]:
        await self.s.execute(delete(SavedRow).where(SavedRow.user_id == user_id, SavedRow.listing_id == listing_id))
        return await self.saved(user_id)

    async def apply_outcome(self, owner_id: str, outcome: Outcome) -> Owner:
        row = await self.s.get(OwnerRow, owner_id, with_for_update=True)
        if not row:
            raise NotFound(f"owner {owner_id} not found")
        updated = apply_outcome(_to_owner(row), outcome)
        row.rating_sum = updated.rating_sum
        row.jobs_done = updated.jobs_done
        row.on_time_jobs = updated.on_time_jobs
        await self.s.flush()
        return updated

    async def replace_all(self, world: World) -> None:
        """Wipe and reload. Seeding and the demo reset use it; nothing else should.
        Hearts go too: a reset is "delete and start over"."""
        for table in (SavedRow, ReviewRow, SlotRow, ListingRow, OwnerRow, DistrictRow):
            await self.s.execute(delete(table))
        # Insert in foreign-key order, flushing between levels (see add_listing).
        self.s.add_all([DistrictRow(**d.model_dump()) for d in world.districts.values()])
        self.s.add_all([_owner_row(o) for o in world.owners])
        await self.s.flush()
        self.s.add_all([_listing_row(l) for l in world.listings])
        await self.s.flush()
        self.s.add_all([_slot_row(s) for s in world.slots])
        self.s.add_all([_review_row(r) for r in world.reviews])
