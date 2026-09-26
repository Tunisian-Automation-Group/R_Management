"""Catalog housekeeping: photos uploaded but never used on a listing (or
left by a deleted account), and reporters' details once a case is closed."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

from cappy_common.errors import NotFound
from cappy_common.events import LISTING_CHANGED, jittered

from .media import rendition, renditions_of, resize_stored
from .repository import CatalogRepository

log = logging.getLogger(__name__)
ORPHAN_AFTER = timedelta(days=1)
BATCH = 500
# A decision can be contested for six months (DSA Art. 20(1)); after that the
# case keeps what was decided and why, not who reported it or their words (D-3).
REPORTER_KEPT = timedelta(days=183)


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
    files = {f for n in gone for f in (n, *renditions_of(n))}
    for name in files:
        try:
            await app.state.media.delete(name)
            await app.state.evidence.delete(name)
        except Exception as e:  # noqa: BLE001 - an orphaned file costs cents; try the rest
            log.warning("could not delete photo %s: %s", name, e)
    # A deleted file must not live on at the edge either (a deleted account's
    # photos above all): the CDN drops the copies now, renditions too.
    await app.state.cdn.purge(sorted(f"/media/{n}" for n in files))
    return len(gone)


async def forget_reporters_once(app: FastAPI, now: datetime | None = None) -> int:
    from sqlalchemy import update

    from .tables import ReportRow

    cutoff = (now or datetime.now(UTC)) - REPORTER_KEPT
    async with app.state.db.transaction() as s:
        r = await s.execute(
            update(ReportRow)
            .where(
                ReportRow.decided_at < cutoff,
                ReportRow.reporter_email.is_not(None) | ReportRow.reporter_id.is_not(None),
            )
            .values(reporter_id=None, reporter_email=None, details="[removed after the case closed]")
        )
    return r.rowcount or 0


async def keep_schedules_once(app: FastAPI, now: datetime | None = None) -> int:
    """H-4: roll weekly schedules on, so a scheduled listing always has eight
    weeks of windows; then tell owners whose live listing has no free time
    in the next week (at most once a week each)."""
    from cappy_common.events import LISTING_IDLE
    from cappy_common.models import Availability

    now = now or datetime.now(UTC)
    added = 0
    async with app.state.db.transaction() as s:
        repo = CatalogRepository(s)
        for listing_id, spec in await repo.schedules_due(now, BATCH):
            if spec.get("availability"):
                added += await repo.apply_schedule(
                    listing_id, Availability.model_validate(spec["availability"]), now, replace=False
                )
    async with app.state.db.transaction() as s:
        for row in await CatalogRepository(s).idle_listings(now, BATCH):
            row.idle_notice_at = now
            await app.state.outbox.add(
                s, LISTING_IDLE, {"listingId": row.id, "ownerId": row.owner_id, "title": row.title}
            )
    return added


async def attribute_decisions_once(app: FastAPI) -> int:
    """Decisions on messages made before each decision recorded its person
    (747ed6b): ask booking who wrote the message, so the author's data export
    finds them. A message booking no longer knows stays unattributed.
    ponytail: runs hourly until done; drop it once no such rows remain."""
    from sqlalchemy import select

    from .tables import ModerationActionRow

    async with app.state.db.transaction() as s:
        rows = (
            (
                await s.execute(
                    select(ModerationActionRow)
                    .where(ModerationActionRow.target_type == "message", ModerationActionRow.person_id.is_(None))
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        done = 0
        for row in rows:
            try:
                row.person_id = await app.state.bookings.message_author(row.target_id)
            except Exception as e:  # noqa: BLE001 - booking down or the message gone: next hour, or never
                log.info("decision %s: no author for message %s (%s)", row.id, row.target_id, e)
                continue
            done += row.person_id is not None
    return done


async def hold_out_of_market_once(app: FastAPI) -> int:
    """V5-1: listings published before places were checked against the
    owner's market stay out of search and detail until the owner moves them
    into an open market; each is logged so staff can see what went."""
    from cappy_common.markets import markets

    live = {cc for cc, m in markets().items() if m.live}
    async with app.state.db.transaction() as s:
        repo = CatalogRepository(s)
        found = await repo.out_of_market(live, BATCH)
        for row, reason in found:
            await repo.hold(row.id, reason)
            log.warning("listing %s (%s) held: %s", row.id, row.district, reason)
            await app.state.outbox.add(s, LISTING_CHANGED, {"listingId": row.id, "change": "held"})
    return len(found)


async def make_renditions_once(app: FastAPI, batch: int = 50) -> int:
    """Uploads from before renditions (U-40) get their widths and colour.
    ponytail: a batch an hour; a one-off script if a backlog ever matters."""
    from sqlalchemy import select, update

    from .tables import MediaRow

    async with app.state.db.transaction() as s:
        names = list(
            (await s.execute(select(MediaRow.name).where(MediaRow.color.is_(None)).distinct().limit(batch))).scalars()
        )
    done = 0
    for name in names:
        try:
            data = await app.state.media.get(name)
        except NotFound:
            data = None  # an evidence photo (private store) or gone: nothing to make
        color = ""
        if data is not None:
            widths, color = await asyncio.to_thread(resize_stored, data)
            for width, rendered in widths.items():
                await app.state.media.put(rendition(name, width), rendered)
        async with app.state.db.transaction() as s:
            await s.execute(update(MediaRow).where(MediaRow.name == name).values(color=color))
        done += 1
    return done


async def sweep_orphans(app: FastAPI) -> None:
    await sweep_orphans_once(app)
    await make_renditions_once(app)
    await forget_reporters_once(app)
    await keep_schedules_once(app)
    await attribute_decisions_once(app)
    await hold_out_of_market_once(app)
    await asyncio.sleep(jittered(3600))
