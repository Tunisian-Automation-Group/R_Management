"""Which service answers which public path. First match wins.

This is an allow-list: anything not listed is a 404 at the gateway. That is
what keeps every service's ``/internal/*`` routes off the internet, whatever
the services themselves expose.
"""

from __future__ import annotations

import re

CATALOG = "catalog"
MATCHING = "matching"
BOOKING = "booking"
PAYMENTS = "payments"
NOTIFICATIONS = "notifications"

# (regex over the path after the /api prefix, upstream)
RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/bookings(/|$)"), BOOKING),
    (re.compile(r"^/payments(/|$)"), PAYMENTS),
    (re.compile(r"^/notifications/devices(/[^/]+)?$"), NOTIFICATIONS),
    (re.compile(r"^/(matches|quote|feasibility|categories|groups|review-tags)$"), MATCHING),
    (re.compile(r"^/browse/[a-z-]+$"), MATCHING),
    (re.compile(r"^/listings/[^/]+/offers$"), MATCHING),
    (re.compile(r"^/(me|districts|cities|owners|listings|search|saved|uploads)(/|$)"), CATALOG),
]


def resolve(path: str) -> str | None:
    """``path`` is relative to ``/api``, e.g. ``/listings/l1/offers``."""
    if "/internal" in path or ".." in path:
        return None
    for pattern, upstream in RULES:
        if pattern.search(path):
            return upstream
    return None
