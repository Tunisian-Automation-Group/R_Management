"""What only Postgres can prove: the migration, and that a window is never sold twice."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient

from booking.main import build_app
from booking.settings import Settings
from booking.tables import Base
from cappy_common.db import Database
from cappy_common.migrations import upgrade
from cappy_common.testing import TestIssuer

from .test_booking_api import FakeMatching, FakePayments, _body

pytestmark = pytest.mark.postgres
MIGRATIONS = Path(__file__).parents[1] / "booking" / "migrations"


async def test_migrations_build_exactly_the_models(postgres_url):
    await asyncio.to_thread(upgrade, MIGRATIONS, postgres_url)
    db = Database(postgres_url)
    try:
        async with db.engine.connect() as conn:
            diff = await conn.run_sync(lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata))
    finally:
        await db.dispose()
    assert diff == [], diff


def test_simultaneous_bookings_of_one_window_yield_exactly_one(postgres_url):
    upgrade(MIGRATIONS, postgres_url)
    issuer = TestIssuer()
    settings = Settings(app_env="test", database_url=postgres_url, internal_token="i" * 40)
    app = build_app(settings, matching=FakeMatching(), payments=FakePayments(), verifier=issuer.verifier())
    body = _body()

    with TestClient(app) as client:

        async def one(n: int) -> int:
            # Straight at the ASGI app, concurrently on one loop, so the
            # friendly pre-check races and only the constraint can decide.
            import httpx

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.post("/bookings", json=body, headers=issuer.headers(f"buyer-{n}"))
                return r.status_code

        codes = client.portal.call(lambda: asyncio.gather(*(one(n) for n in range(20))))
    assert sorted(codes).count(201) == 1, codes
    assert set(codes) == {201, 409}, codes
