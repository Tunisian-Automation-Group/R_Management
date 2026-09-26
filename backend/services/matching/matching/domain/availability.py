"""Port of ``src/domain/availability.ts``."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from cappy_common.models import CamelModel, Iso, Slot
from cappy_common.timeutil import HOUR_MS, MINUTE_MS, iso_from_ms, ms_from_iso


class Offer(CamelModel):
    """A concrete bookable window: not the whole idle gap, the bit you would take."""

    slot_id: str
    start: Iso
    end: Iso


def _step_ms(hours: float) -> int:
    """Short bookings are offered on the half hour; long ones daily."""
    if hours <= 12:
        return 30 * MINUTE_MS
    if hours <= 48:
        return 3 * HOUR_MS
    return 24 * HOUR_MS


def _align_up(ms: int, step: int) -> int:
    return math.ceil(ms / step) * step


Interval = tuple[int, int]  # [start_ms, end_ms)


def offers_for(
    slots: list[Slot],
    hours: float,
    from_: Iso,
    until: Iso,
    limit: int = 60,
    busy: Sequence[Interval] | None = None,
    per_day: int | None = None,
    time_zone: str = "UTC",
) -> list[Offer]:
    """Every start time at which ``hours`` of work fits inside one of these idle
    windows, between ``from_`` and ``until``, without touching anything already
    booked. Pure and deterministic.

    ``busy`` is the listing's held bookings (requested, accepted, active). An
    offer never overlaps one, and a window's usable hours shrink by what has
    already been sold inside it: a factory gap with 30 usable machine-hours
    and 20 of them booked has 10 left, however long the gap is on the clock.

    ``per_day`` caps the starts on any one day, so a busy near day cannot use
    up ``limit`` and hide the days after it (V6-23: an every-day schedule ran
    out after four days). Days are the listing's own (``time_zone``), so an
    evening start after midnight UTC still counts on its local day. A day
    with more starts than the cap is thinned evenly (every k-th start), never
    cut: the evening stays bookable (V7-1: a 24 h listing showed only
    00:00-13:30).
    """
    zone = ZoneInfo(time_zone)
    from_ms = ms_from_iso(from_)
    until_ms = ms_from_iso(until)
    duration_ms = math.ceil(hours * HOUR_MS)
    step = _step_ms(hours)
    taken = sorted(busy or [])
    out: list[Offer] = []

    for slot in sorted(slots, key=lambda s: ms_from_iso(s.start)):
        slot_start = ms_from_iso(slot.start)
        slot_end = ms_from_iso(slot.end)

        sold = sum(max(0, min(b_end, slot_end) - max(b_start, slot_start)) for b_start, b_end in taken) / HOUR_MS
        # A 3-day factory gap is not 72 usable machine-hours; respect the real figure.
        if hours > slot.hours_usable - sold + 1e-9:
            continue

        first = _align_up(max(slot_start, from_ms), step)
        last_start = min(slot_end, until_ms) - duration_ms

        t = first
        while t <= last_start:
            clash = next((b for b in taken if b[0] < t + duration_ms and t < b[1]), None)
            if clash is not None:
                # Jump past the booking to the next aligned start.
                t = _align_up(clash[1], step)
                continue
            out.append(Offer(slot_id=slot.id, start=iso_from_ms(t), end=iso_from_ms(t + duration_ms)))
            if per_day is None and len(out) >= limit:
                return out
            t += step

    if per_day is None:
        return out
    by_day: dict[date, list[Offer]] = {}
    for offer in sorted(out, key=lambda o: ms_from_iso(o.start)):
        by_day.setdefault(datetime.fromtimestamp(ms_from_iso(offer.start) / 1000, zone).date(), []).append(offer)
    thinned = [o for day in sorted(by_day) for o in by_day[day][:: math.ceil(len(by_day[day]) / per_day)]]
    return thinned[:limit]


def earliest_offer(
    slots: list[Slot], hours: float, from_: Iso, until: Iso, busy: Sequence[Interval] | None = None
) -> Offer | None:
    """The soonest window that works, or None. Used for ranking."""
    found = offers_for(slots, hours, from_, until, 1, busy)
    return found[0] if found else None


def idle_hours(slots: list[Slot]) -> float:
    """Idle hours across these windows that nobody has bought."""
    return sum(s.hours_usable for s in slots)
