"""Port of ``src/domain/match.ts``."""

from __future__ import annotations

import math
from typing import Literal

from cappy_common.jsmath import js_round, to_fixed
from cappy_common.models import (
    AnyListing,
    AnyRequirement,
    Iso,
    Match,
    Owner,
    Quote,
    World,
    rating,
    reliability,
)
from cappy_common.timeutil import ms_from_iso

from .availability import Offer, earliest_offer
from .categories import duration_label
from .feasibility import assess_feasibility
from .pricing import hours_for, quote_for

EARTH_KM = 6371


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Haversine between two (lat, lng) pairs."""
    lat1, lng1 = a
    lat2, lng2 = b
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def _normalise(values: list[float]) -> list[float]:
    """Min-max to 0..1. All-equal collapses to 0.5 rather than dividing by zero."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


# Hand-tuned weights. A learned ranker only makes sense once there is real outcome
# data to learn from, which is what the rating loop is accumulating.
W = {"price": 0.3, "soon": 0.2, "trust": 0.3, "near": 0.2}


def trust_of(o: Owner) -> float:
    """Reliability dominates; stars break ties; an unrated owner sits mid-scale."""
    stars = rating(o)
    return 0.6 * reliability(o) + 0.4 * (0.5 if stars is None else stars / 5)


def track_record(o: Owner) -> str:
    if o.jobs_done == 0:
        return "New on Cappy"
    pct = js_round((o.on_time_jobs / o.jobs_done) * 100)
    return f"{o.jobs_done} booking{'' if o.jobs_done == 1 else 's'} · {pct}% on time"


def _window_end(req: AnyRequirement) -> Iso:
    return req.latest if req.mode == "window" else req.deadline


def _reasons(fit_reasons: list[str], hours: float, km: float, owner: Owner) -> list[str]:
    return [
        *fit_reasons,
        f"{duration_label(hours)} of idle time",
        f"{to_fixed(km, 1)} km away",
        track_record(owner),
    ]


def find_matches(req: AnyRequirement, world: World, now: Iso) -> list[Match]:
    """Pure. Every input arrives as an argument, including ``now``."""
    origin = world.districts.get(req.district)
    if not origin:
        return []

    owners = {o.id: o for o in world.owners}
    until = _window_end(req)
    if ms_from_iso(until) <= ms_from_iso(now):
        return []

    slots_by_listing: dict[str, list] = {}
    for s in world.slots:
        slots_by_listing.setdefault(s.listing_id, []).append(s)

    candidates: list[tuple[Owner, dict]] = []

    for listing in world.listings:
        owner = owners.get(listing.owner_id)
        if not owner:
            continue

        fit = assess_feasibility(req, listing)
        if not fit.feasible:
            continue

        dest = world.districts.get(listing.district)
        if not dest:
            continue
        km = distance_km((origin.lat, origin.lng), (dest.lat, dest.lng))
        if km > req.max_distance_km:
            continue

        hours = hours_for(req, listing)
        quote = quote_for(req, listing)
        if hours is None or quote is None:
            continue

        offer = earliest_offer(slots_by_listing.get(listing.id, []), hours, now, until)
        if not offer:
            continue

        candidates.append(
            (
                owner,
                dict(
                    listing_id=listing.id,
                    owner_id=owner.id,
                    slot_id=offer.slot_id,
                    start=offer.start,
                    end=offer.end,
                    confidence=fit.confidence,
                    reasons=_reasons(fit.reasons, hours, km, owner),
                    quote=quote,
                    distance_km=km,
                ),
            )
        )

    if not candidates:
        return []

    cheap = _normalise([-c["quote"].total for _, c in candidates])
    soon = _normalise([-ms_from_iso(c["start"]) for _, c in candidates])
    near = _normalise([-c["distance_km"] for _, c in candidates])
    trust = _normalise([trust_of(o) for o, _ in candidates])

    matches = [
        Match(
            **c,
            score=W["price"] * cheap[i] + W["soon"] * soon[i] + W["near"] * near[i] + W["trust"] * trust[i],
        )
        for i, (_, c) in enumerate(candidates)
    ]
    return sorted(matches, key=lambda m: -m.score)


SortKey = Literal["best", "price", "soonest", "nearest"]


def sort_matches(matches: list[Match], key: SortKey) -> list[Match]:
    if key == "price":
        return sorted(matches, key=lambda m: m.quote.total)
    if key == "soonest":
        return sorted(matches, key=lambda m: ms_from_iso(m.start))
    if key == "nearest":
        return sorted(matches, key=lambda m: m.distance_km)
    return sorted(matches, key=lambda m: -m.score)


def match_for_offer(req: AnyRequirement, listing: AnyListing, owner: Owner, offer: Offer, km: float) -> Match | None:
    """Build the match for a window the buyer picked themselves, rather than the
    soonest one we suggested. Same shape, same reasons, so everything downstream
    (quote, booking, receipt) is identical whichever route they took."""
    fit = assess_feasibility(req, listing)
    if not fit.feasible:
        return None
    hours = hours_for(req, listing)
    quote: Quote | None = quote_for(req, listing)
    if hours is None or quote is None:
        return None

    return Match(
        listing_id=listing.id,
        owner_id=owner.id,
        slot_id=offer.slot_id,
        start=offer.start,
        end=offer.end,
        score=1,
        confidence=fit.confidence,
        reasons=_reasons(fit.reasons, hours, km, owner),
        quote=quote,
        distance_km=km,
    )
