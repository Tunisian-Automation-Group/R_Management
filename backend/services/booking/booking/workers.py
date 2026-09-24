"""Background work: the simulated hosts, and the seeded inbox request."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, func, select

from cappy_common.errors import ApiError
from cappy_common.events import BOOKING_STATUS_CHANGED
from cappy_common.models import Match, Outcome, Requirement, WindowRequest
from cappy_common.timeutil import DAY_MS, MINUTE_MS, iso_from_ms, now_iso, now_ms

from .tables import BookingRow, MetaRow

log = logging.getLogger(__name__)

WORLD_KEY = "world_version"
_requirement = TypeAdapter(Requirement)


async def wipe_bookings(app: FastAPI, world_version: str | None = None) -> int:
    """Forget every booking. The demo reset does this, and so does a world
    rebuilt from a new seed: a booking against a listing that no longer exists
    is not history, it is a broken reference. Returns how many went."""
    async with app.state.db.session() as s, s.begin():
        n = (await s.execute(select(func.count()).select_from(BookingRow))).scalar_one()
        await s.execute(delete(BookingRow))
        if world_version is not None:
            row = await s.get(MetaRow, WORLD_KEY)
            if row:
                row.value = world_version
            else:
                s.add(MetaRow(key=WORLD_KEY, value=world_version))
    return n


async def drop_unreadable(app: FastAPI) -> int:
    """Delete bookings whose stored requirement, match or outcome no longer
    validates (a category that no longer exists, say). Returns how many."""
    gone = 0
    async with app.state.db.session() as s, s.begin():
        for row in (await s.execute(select(BookingRow))).scalars():
            try:
                _requirement.validate_python(row.requirement)
                Match.model_validate(row.match)
                if row.outcome:
                    Outcome.model_validate(row.outcome)
            except ValidationError:
                log.info("booking %s no longer reads against the current world; dropping it", row.id)
                await s.delete(row)
                gone += 1
    return gone


async def reconcile_world(app: FastAPI) -> bool:
    """At startup: is the world these bookings were made against still the one
    the catalog serves? If the catalog has been reseeded from a newer edition
    of the frontend's seed, the bookings point at nothing and are dropped.
    Returns True when that happened."""
    # First, whatever the version says: a row that cannot even be parsed
    # against today's models (a category that no longer exists) is a broken
    # reference by construction and would 500 every listing. Cheap, and it
    # covers a database from before the world was versioned.
    unreadable = await drop_unreadable(app)
    if unreadable:
        log.warning("dropped %d booking(s) that no longer read against the current world", unreadable)

    current = await app.state.catalog.world_version()
    async with app.state.db.session() as s:
        row = await s.get(MetaRow, WORLD_KEY)
        seen = row.value if row else None
    if seen == current:
        return unreadable > 0
    if seen is None:
        async with app.state.db.session() as s, s.begin():
            s.add(MetaRow(key=WORLD_KEY, value=current))
        return unreadable > 0
    n = await wipe_bookings(app, current)
    log.warning("the catalog's world changed (%s -> %s); dropped %d booking(s) made against it", seen, current, n)
    return True


async def accept_due(app: FastAPI) -> int:
    """Accept every request whose simulated host has "replied". Returns how many."""
    now = now_iso()
    accepted: list[str] = []
    async with app.state.db.session() as s, s.begin():
        q = select(BookingRow).where(
            BookingRow.status == "requested",
            BookingRow.auto_accept_at.is_not(None),
            BookingRow.auto_accept_at <= now,
        )
        for row in (await s.execute(q)).scalars():
            row.status = "accepted"
            row.updated_at = now
            row.auto_accept_at = None
            accepted.append(row.id)
    for booking_id in accepted:
        await app.state.bus.publish(
            BOOKING_STATUS_CHANGED,
            {"bookingId": booking_id, "from": "requested", "to": "accepted", "by": "demo-host"},
        )
    return len(accepted)


async def auto_accept_loop(app: FastAPI, interval: float = 1.0) -> None:
    while True:
        try:
            await accept_due(app)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("auto-accept sweep failed")
        await asyncio.sleep(interval)


async def seed_inbox(app: FastAPI) -> bool:
    """One request already waiting in the Earn inbox, so the owner side is not
    empty on first run. Somebody in the neighbourhood wants two hours of the
    machine that would otherwise sit idle tonight."""
    settings = app.state.settings
    if not settings.demo_seed_inbox:
        return False

    async with app.state.db.session() as s:
        count = (await s.execute(select(func.count()).select_from(BookingRow))).scalar_one()
    if count > 0:
        return False

    now = now_iso()
    latest = iso_from_ms(now_ms() + 5 * DAY_MS)
    req = WindowRequest(
        mode="window",
        category=settings.demo_seed_category,
        hours=settings.demo_seed_hours,
        earliest=now,
        latest=latest,
        district=settings.demo_seed_district,
        max_distance_km=10,
    )
    matching = app.state.matching
    offer = await matching.first_offer(settings.demo_seed_listing_id, settings.demo_seed_hours, now, latest)
    if not offer:
        log.warning("no idle window on %s to seed the inbox with", settings.demo_seed_listing_id)
        return False
    match = await matching.match_for_offer(req, settings.demo_seed_listing_id, offer.slot_id, offer.start, offer.end)

    async with app.state.db.session() as s, s.begin():
        s.add(
            BookingRow(
                id="bk_seed_1",
                requester_id=settings.demo_seed_requester_id,
                owner_id=match.owner_id,
                listing_id=match.listing_id,
                status="requested",
                created_at=iso_from_ms(now_ms() - 22 * MINUTE_MS),
                updated_at=now,
                requirement=req.model_dump(mode="json", by_alias=True),
                match=match.model_dump(mode="json", by_alias=True),
                auto_accept_at=None,
            )
        )
    log.info("seeded the inbox request")
    return True


async def on_catalog_changed(app: FastAPI, payload: dict) -> None:
    """A rebuilt world (demo reset, or a new seed) invalidates every booking."""
    if payload.get("what") != "reset":
        return
    try:
        version = await app.state.catalog.world_version()
    except ApiError:
        version = None
    n = await wipe_bookings(app, version)
    log.warning("the catalog was reset (%s); dropped %d booking(s)", payload.get("reason", "demo reset"), n)
    await seed_inbox_with_retry(app)


async def seed_inbox_with_retry(app: FastAPI, attempts: int = 30, delay: float = 2.0) -> None:
    """The matching and catalog services may still be starting; keep trying.
    First makes sure the bookings on disk belong to the world the catalog now
    serves, then puts the seeded request in the inbox if it is empty."""
    for attempt in range(1, attempts + 1):
        try:
            await reconcile_world(app)
            await seed_inbox(app)
            return
        except asyncio.CancelledError:
            raise
        except ApiError as e:
            log.info("inbox seed attempt %d/%d waiting on upstream: %s", attempt, attempts, e.message)
        except Exception:  # noqa: BLE001
            log.exception("inbox seed attempt %d/%d failed", attempt, attempts)
        await asyncio.sleep(delay)
    log.warning("gave up seeding the inbox; POST /admin/reset will try again")
