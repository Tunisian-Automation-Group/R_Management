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
