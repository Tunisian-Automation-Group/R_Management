from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from payments.tables import Base

from cappy_common.db import Database
from cappy_common.migrations import upgrade

pytestmark = pytest.mark.postgres
MIGRATIONS = Path(__file__).parents[1] / "payments" / "migrations"


async def test_migrations_build_exactly_the_models(postgres_url):
    await asyncio.to_thread(upgrade, MIGRATIONS, postgres_url)
    db = Database(postgres_url)
    try:
        async with db.engine.connect() as conn:
            diff = await conn.run_sync(lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata))
    finally:
        await db.dispose()
    assert diff == [], diff


def test_racing_intent_requests_make_one_payment(postgres_url):
    """Five concurrent requests for one booking's intent (a client retrying
    while the first is in flight): one intent, one row, every caller served."""
    import httpx
    from fastapi.testclient import TestClient
    from payments.main import build_app
    from payments.provider import FakeProvider
    from payments.settings import Settings

    from cappy_common.testing import TestIssuer

    upgrade(MIGRATIONS, postgres_url)
    settings = Settings(app_env="test", database_url=postgres_url, internal_token="i" * 40)
    app = build_app(settings, provider=FakeProvider(), verifier=TestIssuer().verifier())
    body = {"bookingId": "bk_r", "requesterId": "b", "ownerId": "h", "amount": 100, "ownerNet": 80, "currency": "eur"}
    headers = {"X-Internal-Token": "i" * 40}

    async def race():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await asyncio.gather(*(c.post("/internal/intents", json=body, headers=headers) for _ in range(5)))

    with TestClient(app) as client:
        results = client.portal.call(race)
    assert [r.status_code for r in results] == [200] * 5, [r.text for r in results]
    assert len({r.json()["intentId"] for r in results}) == 1


async def test_invoice_numbers_have_no_gaps_under_concurrency(postgres_url):
    from payments.invoices import issue

    await asyncio.to_thread(upgrade, MIGRATIONS, postgres_url)
    db = Database(postgres_url, pool_size=10)
    try:

        async def one(n: int) -> str:
            async with db.transaction() as s:
                row = await issue(s, booking_id=f"bk_{n}", owner_id="o", fee_gross=600, currency="eur")
                return row.number

        numbers = await asyncio.gather(*(one(n) for n in range(20)))
        tails = sorted(int(x.rsplit("-", 1)[1]) for x in numbers)
        assert tails == list(range(1, 21))
    finally:
        await db.dispose()
