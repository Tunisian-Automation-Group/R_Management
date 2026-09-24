"""Load the demo world into the catalog.

The world is rebuilt from the shipped seed whenever the seed changes, the same
way the app rebuilds it from ``seed.ts`` on every load: a database seeded from
an older edition would otherwise keep serving categories that no longer exist.
"""

from __future__ import annotations

from typing import Literal

from cappy_common.fixtures import build_world, fingerprint

from .repository import CatalogRepository

SEED_KEY = "seed_fingerprint"


async def seed_world(repo: CatalogRepository, tz: str) -> None:
    await repo.replace_all(build_world(tz))
    await repo.set_meta(SEED_KEY, fingerprint())


async def loaded_version(repo: CatalogRepository) -> str | None:
    return await repo.get_meta(SEED_KEY)


async def seed_if_stale(repo: CatalogRepository, tz: str) -> Literal["empty", "changed"] | None:
    """Seed an empty database, or reseed one built from a different edition of
    the seed. Returns why it seeded, or None if the world was already current."""
    if await repo.count_owners() == 0:
        await seed_world(repo, tz)
        return "empty"
    if await loaded_version(repo) != fingerprint():
        await seed_world(repo, tz)
        return "changed"
    return None


async def seed_if_empty(repo: CatalogRepository, tz: str) -> bool:
    return await seed_if_stale(repo, tz) is not None
