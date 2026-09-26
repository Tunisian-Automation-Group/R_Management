"""Port of ``src/domain/pricing.ts``."""

from __future__ import annotations

import math

from cappy_common.jsmath import js_round
from cappy_common.models import AnyListing, AnyRequirement, Cents, Quote

from .money import bps

# 15% take rate. The fee sits inside the total the buyer pays: it is not added on
# top at the last step, because that is the thing everyone hates about marketplaces.
PLATFORM_FEE_BPS = 1500


def hours_for(req: AnyRequirement, listing: AnyListing) -> float | None:
    """How many hours of the asset this request consumes.

    window: the buyer names the duration.
    batch:  setup plus run time, derived from quantity and throughput.
    None when the request and listing are different shapes; feasibility rejects those.
    """
    if req.mode == "window" and listing.mode == "window":
        return req.hours
    if req.mode == "batch" and listing.mode == "batch":
        return listing.setup_hours + req.quantity / listing.units_per_hour
    return None


DAY_HOURS, WEEK_HOURS = 8, 40


def duration_discount(hours: float, base: Cents, listing: AnyListing) -> tuple[Cents, str]:
    """The owner's discount for longer bookings: the week rate from 40 hours,
    the day rate from 8. Taken off the hourly base, never the extras."""
    week, day = getattr(listing, "week_discount_pct", 0), getattr(listing, "day_discount_pct", 0)
    if hours >= WEEK_HOURS and week:
        return js_round(base * week / 100), f"Week rate −{week}%"
    if hours >= DAY_HOURS and day:
        return js_round(base * day / 100), f"Day rate −{day}%"
    return 0, ""


def quote_for(req: AnyRequirement, listing: AnyListing) -> Quote | None:
    # A listing that cannot be priced (zero throughput, a negative fee: older
    # rows from before the write-time bounds) is no offer, never a 500 (P-1).
    if listing.mode == "batch" and (listing.units_per_hour <= 0 or listing.setup_fee < 0):
        return None
    hours = hours_for(req, listing)
    if hours is None or not math.isfinite(hours):
        return None

    base: Cents = js_round(hours * listing.rate_per_hour)
    discount, discount_label = duration_discount(hours, base, listing)
    if listing.mode == "window":
        extra, extra_label = listing.extra_fee, listing.extra_label
    else:
        extra, extra_label = listing.setup_fee, "Setup and programming"
    total: Cents = base - discount + extra
    platform_fee = bps(total, PLATFORM_FEE_BPS)

    return Quote(
        currency=listing.currency,
        hours=hours,
        base=base,
        discount=discount,
        discount_label=discount_label,
        extra=extra,
        extra_label=extra_label,
        total=total,
        platform_fee=platform_fee,
        owner_net=total - platform_fee,
    )
