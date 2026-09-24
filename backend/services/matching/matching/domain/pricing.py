"""Port of ``src/domain/pricing.ts``."""

from __future__ import annotations

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


def quote_for(req: AnyRequirement, listing: AnyListing) -> Quote | None:
    hours = hours_for(req, listing)
    if hours is None:
        return None

    base: Cents = js_round(hours * listing.rate_per_hour)
    if listing.mode == "window":
        extra, extra_label = listing.extra_fee, listing.extra_label
    else:
        extra, extra_label = listing.setup_fee, "Setup and programming"
    total: Cents = base + extra
    platform_fee = bps(total, PLATFORM_FEE_BPS)

    return Quote(
        hours=hours,
        base=base,
        extra=extra,
        extra_label=extra_label,
        total=total,
        platform_fee=platform_fee,
        owner_net=total - platform_fee,
    )
