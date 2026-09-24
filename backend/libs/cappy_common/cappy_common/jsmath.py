"""JavaScript number semantics where Python differs.

The pricing, ranking and copy in the frontend were written against
``Math.round`` and ``Number.prototype.toFixed``. Python ``round`` is
banker's rounding and its ``f"{x:.1f}"`` rounds the binary value, so a
naive port would disagree with the app on exactly the cents that matter.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal


def js_round(x: float) -> int:
    """``Math.round``: half rounds toward +infinity."""
    return math.floor(x + 0.5)


def to_fixed(x: float, digits: int) -> str:
    """``x.toFixed(digits)`` for non-negative x."""
    q = Decimal(1).scaleb(-digits)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))


def plus_to_fixed(x: float, digits: int) -> str:
    """``String(+x.toFixed(digits))``: toFixed, then drop trailing zeros."""
    s = to_fixed(x, digits)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s
