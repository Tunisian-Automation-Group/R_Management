"""Port of ``src/domain/browse.ts``."""

from __future__ import annotations

from cappy_common.jsmath import js_round
from cappy_common.models import AnyListing, CamelModel, Cents, District, Iso, Listing, Owner, World
from cappy_common.timeutil import HOUR_MS, ms_from_iso

from .availability import Offer, earliest_offer
from .match import distance_km, trust_of


class Spotlight(CamelModel):
    listing: Listing
    owner: Owner
    offer: Offer
    distance_km: float
    # Cheapest real booking you could make: the minimum, not an average.
    from_price: Cents
    # The idle window is already open, so this is available this second.
    free_now: bool
    # When the underlying window opened or opens: the honest answer to "when?".
    window_start: Iso


class IdleSummary(CamelModel):
    hours: float
    value: Cents
    listings: int
    owners: int
    free_now_count: int


class CityStat(CamelModel):
    city: str
    country: str
    lat: float
    lng: float
    listings: int
    idle: IdleSummary


class NearestDistrict(CamelModel):
    district: District
    km: float


_EMPTY = IdleSummary(hours=0, value=0, listings=0, owners=0, free_now_count=0)


def from_price(listing: AnyListing) -> Cents:
    """The smallest booking this listing will accept, priced."""
    if listing.mode == "window":
        return js_round(listing.min_hours * listing.rate_per_hour) + listing.extra_fee
    return listing.setup_fee + js_round((listing.setup_hours + 1) * listing.rate_per_hour)


def _probe_hours(listing: AnyListing) -> float:
    """The shortest booking worth offering, used to answer "is this free soon?"."""
    return listing.min_hours if listing.mode == "window" else listing.setup_hours + 1


def _slots_by_listing(world: World) -> dict[str, list]:
    out: dict[str, list] = {}
    for s in world.slots:
        out.setdefault(s.listing_id, []).append(s)
    return out


def available_soon(
    world: World, district: str, max_km: float, now: Iso, within_hours: float = 24, limit: int = 12
) -> list[Spotlight]:
    """What is genuinely free near you in the next ``within_hours``, soonest first."""
    origin = world.districts.get(district)
    if not origin:
        return []
    now_ms = ms_from_iso(now)
    until = _iso_plus(now, within_hours)
    owners = {o.id: o for o in world.owners}
    by_listing = _slots_by_listing(world)
    out: list[Spotlight] = []

    for listing in world.listings:
        if not listing.active:
            continue
        owner = owners.get(listing.owner_id)
        dest = world.districts.get(listing.district)
        if not owner or not dest:
            continue

        km = distance_km((origin.lat, origin.lng), (dest.lat, dest.lng))
        if km > max_km:
            continue

        slots = by_listing.get(listing.id, [])
        offer = earliest_offer(slots, _probe_hours(listing), now, until)
        if not offer:
            continue

        slot = next(s for s in slots if s.id == offer.slot_id)
        out.append(
            Spotlight(
                listing=listing,
                owner=owner,
                offer=offer,
                distance_km=km,
                from_price=from_price(listing),
                free_now=ms_from_iso(slot.start) <= now_ms,
                window_start=slot.start,
            )
        )

    # Soonest first, and a better-trusted owner wins an exact tie.
    out.sort(key=lambda s: (not s.free_now, ms_from_iso(s.offer.start), -trust_of(s.owner)))
    return out[:limit]


def search_listings(listings: list[AnyListing], query: str) -> list[AnyListing]:
    """Free-text filter over the things a person would actually type."""
    q = query.strip().lower()
    if not q:
        return listings
    return [l for l in listings if q in " ".join([l.title, l.blurb, l.district, l.category]).lower()]


def idle_nearby(world: World, district: str, max_km: float, now: Iso, horizon_hours: float = 24) -> IdleSummary:
    """The size of the waste, nearby, right now. Priced at each owner's own rate."""
    origin = world.districts.get(district)
    if not origin:
        return _EMPTY

    now_ms = ms_from_iso(now)
    until_ms = now_ms + horizon_hours * HOUR_MS
    owners: set[str] = set()
    hours = 0.0
    value = 0
    listings = 0
    free_now_count = 0
    by_listing = _slots_by_listing(world)

    for listing in world.listings:
        if not listing.active:
            continue
        dest = world.districts.get(listing.district)
        if not dest or distance_km((origin.lat, origin.lng), (dest.lat, dest.lng)) > max_km:
            continue

        listing_hours = 0.0
        live = False
        for slot in by_listing.get(listing.id, []):
            start = ms_from_iso(slot.start)
            end = ms_from_iso(slot.end)
            # Only the part of the window that is still ahead of us and inside the horizon.
            lo = max(start, now_ms)
            hi = min(end, until_ms)
            if hi <= lo:
                continue
            wall = (end - start) / HOUR_MS
            overlap = (hi - lo) / HOUR_MS
            # Scale declared usable hours by how much of the window is left.
            listing_hours += slot.hours_usable * (overlap / wall) if wall > 0 else 0
            if start <= now_ms:
                live = True

        if listing_hours <= 0:
            continue
        hours += listing_hours
        value += js_round(listing_hours * listing.rate_per_hour)
        listings += 1
        owners.add(listing.owner_id)
        if live:
            free_now_count += 1

    return IdleSummary(hours=hours, value=value, listings=listings, owners=len(owners), free_now_count=free_now_count)


def _any_district_in(world: World, metro: str) -> str | None:
    return next((d.name for d in world.districts.values() if d.metro == metro), None)


def cities(world: World, now: Iso, horizon_hours: float = 168) -> list[CityStat]:
    """Every market with capacity on the platform, busiest first."""
    by_city: dict[str, dict] = {}
    for d in world.districts.values():
        seen = by_city.get(d.metro)
        if seen:
            # Running mean of the districts, so the marker sits over the city centre.
            seen["lat"] += (d.lat - seen["lat"]) / (seen["n"] + 1)
            seen["lng"] += (d.lng - seen["lng"]) / (seen["n"] + 1)
            seen["n"] += 1
        else:
            by_city[d.metro] = {"country": d.country, "lat": d.lat, "lng": d.lng, "n": 1}

    counts: dict[str, int] = {}
    for l in world.listings:
        if not l.active:
            continue
        d = world.districts.get(l.district)
        if d:
            counts[d.metro] = counts.get(d.metro, 0) + 1

    out = [
        CityStat(
            city=city,
            country=c["country"],
            lat=c["lat"],
            lng=c["lng"],
            listings=counts.get(city, 0),
            # A city-wide radius: big enough to cover the metro area and its industry.
            idle=idle_nearby(world, _any_district_in(world, city) or "", 60, now, horizon_hours),
        )
        for city, c in by_city.items()
    ]
    out = [c for c in out if c.listings > 0]
    out.sort(key=lambda c: (-c.idle.hours, c.city))
    return out


def idle_europe(world: World, now: Iso, horizon_hours: float = 168) -> IdleSummary:
    """Europe-wide total. A week, like ``cities``."""
    acc = _EMPTY
    for c in cities(world, now, horizon_hours):
        acc = IdleSummary(
            hours=acc.hours + c.idle.hours,
            value=acc.value + c.idle.value,
            listings=acc.listings + c.idle.listings,
            owners=acc.owners + c.idle.owners,
            free_now_count=acc.free_now_count + c.idle.free_now_count,
        )
    return acc


def nearest_district(world: World, lat: float, lng: float) -> NearestDistrict | None:
    """The seeded district closest to a real coordinate, and how far away it is."""
    all_districts = list(world.districts.values())
    if not all_districts:
        return None
    best = all_districts[0]
    best_km = distance_km((lat, lng), (best.lat, best.lng))
    for d in all_districts[1:]:
        km = distance_km((lat, lng), (d.lat, d.lng))
        if km < best_km:
            best, best_km = d, km
    return NearestDistrict(district=best, km=best_km)


def _iso_plus(iso: Iso, hours: float) -> Iso:
    from cappy_common.timeutil import iso_from_ms

    return iso_from_ms(ms_from_iso(iso) + int(hours * HOUR_MS))
