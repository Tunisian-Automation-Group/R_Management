from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from cappy_common.db import Database
from cappy_common.migrations import ensure_database

pytestmark = pytest.mark.postgres


async def test_ensure_database_creates_an_owned_database_once(postgres_url):
    name = f"svc_{uuid.uuid4().hex[:8]}"
    url = make_url(postgres_url).set(username=name, password="p'w\\d;--", database=name).render_as_string(False)
    await ensure_database(postgres_url, url)
    await ensure_database(postgres_url, url)  # idempotent, and re-sets the password
    db = Database(url)
    try:
        async with db.engine.connect() as conn:
            assert await conn.scalar(text("SELECT current_user")) == name
    finally:
        await db.dispose()
    admin = Database(make_url(postgres_url).set(database="postgres").render_as_string(False))
    try:
        async with admin.engine.connect() as conn:
            await conn.execute(text("COMMIT"))
            await conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
            await conn.execute(text(f"DROP ROLE {name}"))
    finally:
        await admin.dispose()


async def test_refuses_odd_identifiers(postgres_url):
    bad = make_url(postgres_url).set(username="x; DROP", password="p", database="d").render_as_string(False)
    with pytest.raises(SystemExit):
        await ensure_database(postgres_url, bad)
