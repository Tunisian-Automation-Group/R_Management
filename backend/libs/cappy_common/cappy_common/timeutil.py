"""ISO-8601 instants the way JavaScript writes them.

The frontend stores every instant as ``Date.prototype.toISOString()`` output:
UTC, millisecond precision, trailing ``Z``, and compares them via
``Date.parse``. These helpers reproduce both so timestamps round-trip
byte-for-byte between the two codebases.
"""

from __future__ import annotations

from datetime import UTC, datetime

HOUR_MS = 3_600_000
MINUTE_MS = 60_000
DAY_MS = 86_400_000


def ms_from_iso(iso: str) -> int:
    """``Date.parse`` for ISO-8601 input. Naive strings are taken as UTC."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(round(dt.timestamp() * 1000))


def iso_from_ms(ms: int) -> str:
    """``new Date(ms).toISOString()``."""
    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def now_iso() -> str:
    return iso_from_ms(now_ms())


def iso_from_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return iso_from_ms(int(round(dt.timestamp() * 1000)))
