from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.db import Base, Database
from cappy_common.events import BOOKING_RATED, CATALOG_CHANGED, make_event_bus
from cappy_common.models import Outcome, Review

from . import tables  # noqa: F401 - registers the tables on Base.metadata
from .repository import CatalogRepository
from .routes import router
from .seed import seed_if_stale
from .settings import Settings

log = logging.getLogger(__name__)


async def record_rating(repo: CatalogRepository, payload: dict) -> Review | None:
    """The write half of the loop, in one transaction.

    A rated booking changes where its owner ranks for everyone else from now on
    (``apply_outcome``), and becomes a review the next buyer reads. The review's
    id is ``rv_<bookingId>``, which is also what the app derives locally, so a
    client can tell its own review apart, and so a redelivered event is a no-op.
    """
    booking_id = payload["bookingId"]
    review_id = f"rv_{booking_id}"
    if await repo.has_review(review_id):
        return None

    outcome = Outcome.model_validate(payload["outcome"])
    await repo.apply_outcome(payload["ownerId"], outcome)

    listing_id = payload.get("listingId")
    if not listing_id or not await repo.has_listing(listing_id):
        # Rated after the listing was taken down: the record still moves, but
        # there is no page left for the words to appear on.
        return None

    requester_id = payload.get("requesterId")
    author = await repo.find_owner(requester_id) if requester_id else None
    review = Review(
        id=review_id,
        listing_id=listing_id,
        owner_id=payload["ownerId"],
        author=author.name if author else "A buyer",
        initials=author.initials if author else "??",
        author_id=requester_id,
        rating=outcome.quality,
        on_time=outcome.on_time,
        text=outcome.note or "",
        tags=outcome.tags or [],
        at=payload.get("at") or payload.get("ratedAt") or "",
    )
    await repo.add_review(review)
    return review


def build_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.database_url)
        await db.create_all(Base)
        bus = make_event_bus(settings.event_bus_url, group="catalog")

        if settings.seed_on_start:
            async with db.session() as s, s.begin():
                why = await seed_if_stale(CatalogRepository(s), settings.seed_timezone)
            if why == "empty":
                log.info("seeded the demo world")
            elif why == "changed":
                # The frontend's seed.ts moved on; the world this database held
                # is gone. Anyone holding bookings against it is told so.
                log.warning("the shipped seed changed; rebuilt the demo world from it")
                await bus.publish(CATALOG_CHANGED, {"what": "reset", "reason": "seed changed"})

        async def on_booking_rated(payload: dict) -> None:
            async with db.session() as s, s.begin():
                await record_rating(CatalogRepository(s), payload)
            await bus.publish(CATALOG_CHANGED, {"what": "owner", "id": payload["ownerId"]})

        bus.subscribe(BOOKING_RATED, on_booking_rated)
        await bus.start()

        app.state.settings = settings
        app.state.db = db
        app.state.bus = bus
        app.state.current_user = lambda header: header or settings.demo_user_id
        try:
            yield
        finally:
            await bus.stop()
            await db.dispose()

    app = create_app(settings, title="Cappy catalog", lifespan=lifespan)
    app.include_router(router)
    return app


app = build_app(Settings())
