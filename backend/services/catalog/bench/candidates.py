"""Candidate search and free-text search at scale (T-10), against the local
Postgres (`make up`). Builds a throwaway database `scale` with N synthetic
listings (3 windows each over the next month), then times each query as the
mean of 10 runs after one warm-up. Results: docs/bench.md.

    make bench            # 100k listings
    cd backend && uv run python services/catalog/bench/candidates.py 20000
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from cappy_common.db import Database
from cappy_common.fixtures import build_world
from cappy_common.migrations import upgrade
from catalog.repository import CatalogRepository

BASE = "postgresql+asyncpg://cappy:cappy@localhost:5433/"
MIG = Path("services/catalog/catalog/migrations")


async def main(n):
    admin = Database(BASE + "postgres")
    async with admin.engine.connect() as c:
        await c.execute(text("COMMIT"))
        await c.execute(text("DROP DATABASE IF EXISTS scale WITH (FORCE)"))
        await c.execute(text("CREATE DATABASE scale"))
    await admin.dispose()
    await asyncio.to_thread(upgrade, MIG, BASE + "scale")
    db = Database(BASE + "scale", pool_size=5, statement_timeout_ms=600_000)
    async with db.transaction() as s:
        await CatalogRepository(s).load_seed(build_world())
    # n synthetic listings, each with 3 windows over the next month, spread over the districts.
    async with db.engine.begin() as c:
        await c.execute(
            text("""
          INSERT INTO listings (id, owner_id, category, mode, title, blurb, district, instructions, rules, photos,
                                active, spec, created_at, updated_at)
          SELECT 'ls_s' || g, 'o1', (ARRAY['workshop','creator','events','warehousing'])[1 + g % 4],
                 'window', 'Synthetic machine ' || g || ' ' || md5(g::text), 'blurb ' || md5((g*7)::text),
                 (SELECT name FROM districts ORDER BY name OFFSET (g % (SELECT count(*) FROM districts)) LIMIT 1),
                 'x', '[]'::jsonb, '[]'::jsonb, true,
                 CAST(:spec AS jsonb), now(), now()
          FROM generate_series(1, :n) g"""),
            {"n": n, "spec": '{"ratePerHour":1000,"minHours":1,"maxHours":8,"extraFee":0,"extraLabel":""}'},
        )
        await c.execute(
            text("""
          INSERT INTO slots (id, listing_id, start, "end", hours_usable)
          SELECT 'sl_s' || g || '_' || k, 'ls_s' || g, now() + (k * 7 + g % 5) * interval '1 day',
                 now() + (k * 7 + g % 5) * interval '1 day' + interval '8 hours', 8
          FROM generate_series(1, :n) g, generate_series(0, 2) k"""),
            {"n": n},
        )
        await c.execute(text("ANALYZE"))
    now = datetime.now(UTC)
    async with db.session() as s:
        repo = CatalogRepository(s)
        origin = await repo.district("Kreuzberg")
        for label, fn in [
            (
                "candidates workshop 25km 7d",
                lambda: repo.candidates(
                    origin=origin, max_km=25, start=now, until=now + timedelta(days=7), category="workshop", cap=300
                ),
            ),
            (
                "candidates any 500km 30d",
                lambda: repo.candidates(
                    origin=origin, max_km=500, start=now, until=now + timedelta(days=30), category=None, cap=300
                ),
            ),
            (
                "search 'machine 4242'",
                lambda: repo.search(q="machine 4242", metro=None, category=None, cursor=None, limit=20),
            ),
            ("search 'saw' Berlin", lambda: repo.search(q="saw", metro="Berlin", category=None, cursor=None, limit=20)),
        ]:
            await fn()
            t = time.perf_counter()
            for _ in range(10):
                await fn()
            print(f"{n:>7} listings  {label:32} {(time.perf_counter() - t) / 10 * 1000:7.1f} ms")
    await db.dispose()
    # Leave nothing behind: the throwaway database goes.
    admin = Database(BASE + "postgres")
    async with admin.engine.connect() as c:
        await c.execute(text("COMMIT"))
        await c.execute(text("DROP DATABASE IF EXISTS scale WITH (FORCE)"))
    await admin.dispose()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 100_000))
