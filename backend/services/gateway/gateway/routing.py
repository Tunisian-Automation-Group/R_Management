"""Which service answers which path. Order matters: first match wins."""

from __future__ import annotations

import re

CATALOG = "catalog"
MATCHING = "matching"
BOOKING = "booking"

# (regex over the path *after* the /api prefix, upstream)
RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/bookings(/|$)"), BOOKING),
    (re.compile(r"^/(matches|match-for-offer|quote|feasibility|categories|groups|review-tags)$"), MATCHING),
    (re.compile(r"^/browse(/|$)"), MATCHING),
    (re.compile(r"^/districts/nearest$"), MATCHING),
    (re.compile(r"^/listings/[^/]+/offers$"), MATCHING),
    (re.compile(r"^/listings/[^/]+/reviews/summary$"), MATCHING),
    (re.compile(r"^/(world|me|districts|owners|listings|reviews|saved)(/|$)"), CATALOG),
]


def resolve(path: str) -> str | None:
    """``path`` is relative to ``/api``, e.g. ``/listings/l1/offers``."""
    for pattern, upstream in RULES:
        if pattern.search(path):
            return upstream
    return None
