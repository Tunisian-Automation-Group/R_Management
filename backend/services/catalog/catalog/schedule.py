"""Weekly opening hours into windows (H-4).

Local wall-clock times in the listing's own time zone, turned into UTC one day
at a time, so a Sunday 09:00–17:00 is 07:00–15:00 UTC in summer and 08:00–16:00
UTC after the clocks go back, and always eight real hours.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cappy_common.errors import Invalid
from cappy_common.models import Availability

HORIZON = timedelta(weeks=8)


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise Invalid(f"unknown time zone: {name}") from e


def check(a: Availability) -> None:
    zone(a.time_zone)
    for w in a.weekly:
        if w.end != "24:00" and w.end <= w.start:
            raise Invalid(f"opening hours must end after they start ({w.start}–{w.end})")


def _at(day: date, hhmm: str, tz: ZoneInfo) -> datetime:
    if hhmm == "24:00":
        return datetime.combine(day + timedelta(days=1), time(0), tz).astimezone(UTC)
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, m), tz).astimezone(UTC)


def windows(a: Availability, now: datetime, until: datetime) -> list[tuple[datetime, datetime]]:
    """Every opening from ``now`` to ``until``, UTC, soonest first. One that
    already started is left out rather than cut: half a window is a surprise."""
    tz = zone(a.time_zone)
    out = []
    day = now.astimezone(tz).date()
    while _at(day, "00:00", tz) < until:
        for w in a.weekly:
            if w.day == day.isoweekday():
                start, end = _at(day, w.start, tz), _at(day, w.end, tz)
                if start >= now and start < until:
                    out.append((start, end))
        day += timedelta(days=1)
    return sorted(out)


def free_of(candidates: list[tuple[datetime, datetime]], taken: list[tuple[datetime, datetime]]):
    """The candidates that overlap nothing already there (hand-made windows,
    or ones generated before)."""
    return [(s, e) for s, e in candidates if all(e <= ts or s >= te for ts, te in taken)]
