"""Operator commands. ``python -m catalog.cli --help``.

``seed-demo`` loads the demo world (ADR 0010): only where APP_ENV is local or
staging, additive only, never touching what is already there.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from cappy_common.db import Database
from cappy_common.fixtures import build_world

from .repository import CatalogRepository
from .settings import Settings


def _remap(world, owner_map: dict[str, str]):
    """Point seeded owners at real (Cognito) ids, so demo users who sign in
    see the listings, reviews and records the seed gave them."""
    if not owner_map:
        return world
    m = lambda i: owner_map.get(i, i)  # noqa: E731
    return world.model_copy(
        update={
            "owners": [o.model_copy(update={"id": m(o.id)}) for o in world.owners],
            "listings": [l.model_copy(update={"owner_id": m(l.owner_id)}) for l in world.listings],
            "reviews": [
                r.model_copy(update={"owner_id": m(r.owner_id), "author_id": m(r.author_id) if r.author_id else None})
                for r in world.reviews
            ],
        }
    )


async def seed_demo(owner_map: dict[str, str]) -> dict[str, int]:
    settings = Settings()
    if settings.app_env not in ("local", "staging", "test"):
        raise SystemExit(f"refusing to load demo data into APP_ENV={settings.app_env}")
    db = Database(settings.database_url)
    try:
        async with db.transaction() as s:
            return await CatalogRepository(s).load_seed(_remap(build_world(), owner_map))
    finally:
        await db.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="catalog")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed-demo", help="load the demo world (local/staging only; additive)")
    seed.add_argument("--owner-map", default="", help="seeded=real owner ids, comma-separated (o1=<sub>)")
    args = parser.parse_args(argv)
    if args.cmd == "seed-demo":
        pairs = [p.split("=", 1) for p in args.owner_map.split(",") if "=" in p]
        added = asyncio.run(seed_demo(dict(pairs)))
        json.dump(added, sys.stdout)
        print()


if __name__ == "__main__":
    main()
