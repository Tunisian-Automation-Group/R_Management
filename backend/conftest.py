"""Shared pytest fixtures.

Unit tests run on SQLite in memory and need nothing installed. Tests marked
``postgres`` exercise what only Postgres can prove (exclusion constraints,
concurrent transactions, migrations); they run when ``CAPPY_TEST_PG`` points
at a server (``make test-pg`` starts one) and are skipped otherwise. CI always
sets it.
"""

from __future__ import annotations

import os
import uuid

import pytest


@pytest.fixture()
async def postgres_url():
    """A brand-new, empty database for one test, dropped afterwards."""
    base = os.environ.get("CAPPY_TEST_PG")
    if not base:
        pytest.skip("CAPPY_TEST_PG not set; run `make test-pg`")
    import asyncpg

    admin_dsn = base.replace("postgresql+asyncpg://", "postgresql://")
    name = f"t_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
    root = base.rsplit("/", 1)[0]
    yield f"{root}/{name}"
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()
