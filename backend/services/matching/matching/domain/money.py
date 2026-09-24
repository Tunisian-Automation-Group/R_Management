"""Port of ``src/domain/money.ts``. Formatting lives in the app; the server keeps the maths."""

from __future__ import annotations

from cappy_common.jsmath import js_round
from cappy_common.models import Cents


def euros(n: float) -> Cents:
    return js_round(n * 100)


def bps(amount: Cents, points: int) -> Cents:
    """Basis points of a cent amount, rounded to the nearest cent."""
    return js_round((amount * points) / 10_000)
