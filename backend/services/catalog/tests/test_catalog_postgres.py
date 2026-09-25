"""What only Postgres can prove: the migrations, and behaviour under concurrency."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from cappy_common.db import Database
from cappy_common.events import BOOKING_RATED, Event
from cappy_common.fixtures import build_world
from cappy_common.ids import new_id
from cappy_common.migrations import upgrade
from cappy_common.timeutil import now_iso
from catalog.repository import CatalogRepository
from catalog.tables import MIGRATION_ONLY_INDEXES, Base

pytestmark = pytest.mark.postgres
MIGRATIONS = Path(__file__).parents[1] / "catalog" / "migrations"


async def test_migrations_build_exactly_the_models(postgres_url):
    await asyncio.to_thread(upgrade, MIGRATIONS, postgres_url)
    db = Database(postgres_url)
    try:
        async with db.engine.connect() as conn:
            diff = await conn.run_sync(lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata))
    finally:
        await db.dispose()
    diff = [d for d in diff if not (d[0] == "remove_index" and d[1].name in MIGRATION_ONLY_INDEXES)]
    # A model change without a migration fails here, not in production.
    assert diff == [], diff


async def test_concurrent_ratings_never_lose_an_increment(postgres_url):
    from cappy_common.events import Dispatcher

    await asyncio.to_thread(upgrade, MIGRATIONS, postgres_url)
    db = Database(postgres_url, pool_size=10)
    try:
        async with db.transaction() as s:
            await CatalogRepository(s).load_seed(build_world())
        from catalog.handlers import on_booking_rated
        from catalog.tables import PROCESSED

        dispatcher = Dispatcher(db, PROCESSED, {BOOKING_RATED: on_booking_rated})
        async with db.session() as s:
            before = (await CatalogRepository(s).owner("o5")).rating_sum

        def ev(n: int) -> Event:
            return Event(
                id=new_id("ev"),
                type=BOOKING_RATED,
                source="booking",
                occurred_at=now_iso(),
                data={
                    "bookingId": f"bk_c{n}",
                    "ownerId": "o5",
                    "listingId": "l8",
                    "outcome": {"onTime": True, "quality": 4},
                    "at": now_iso(),
                },
            )

        events = [ev(n) for n in range(10)]
        # Ten different ratings at once, plus every one of them delivered twice.
        results = await asyncio.gather(*(dispatcher.handle(e) for e in events + events))
        assert sum(results) == 10
        async with db.session() as s:
            after = await CatalogRepository(s).owner("o5")
        assert after.rating_sum == before + 40
    finally:
        await db.dispose()
