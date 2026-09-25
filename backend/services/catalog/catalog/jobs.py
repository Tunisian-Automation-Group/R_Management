"""Catalog housekeeping: photos uploaded but never used on a listing."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

from cappy_common.events import jittered

from .repository import CatalogRepository

log = logging.getLogger(__name__)
ORPHAN_AFTER = timedelta(days=1)
BATCH = 500


async def sweep_orphans_once(app: FastAPI) -> int:
    """Deletes unused uploads older than a day. Photos are content-addressed
    and shared: the file goes only when nobody holds it any more."""
    gone: set[str] = set()
    async with app.state.db.transaction() as s:
        repo = CatalogRepository(s)
        rows = await repo.orphans(datetime.now(UTC) - ORPHAN_AFTER, BATCH)
        names = {r.name for r in rows}
        for r in rows:
            await s.delete(r)
        await s.flush()
        gone = {n for n in names if not await repo.still_held(n)}
    for name in gone:
        try:
            await app.state.media.delete(name)
        except Exception as e:  # noqa: BLE001 - an orphaned file costs cents; try the rest
            log.warning("could not delete photo %s: %s", name, e)
    return len(gone)


async def sweep_orphans(app: FastAPI) -> None:
    await sweep_orphans_once(app)
    await asyncio.sleep(jittered(3600))
