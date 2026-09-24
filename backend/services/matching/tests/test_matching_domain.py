"""Port of the app's ``src/domain/check.ts`` (``npm run check``).

Same assertions, same seed. If these pass and the app's check passes, the two
codebases agree on every rule.
"""

from __future__ import annotations

import pytest

from cappy_common.fixtures import build_world
from cappy_common.models import (
    REVIEW_TAGS,
    BatchRequest,
    Outcome,
    Owner,
    Slot,
    WindowRequest,
    World,
    apply_outcome,
)
from cappy_common.timeutil import HOUR_MS, iso_from_ms, ms_from_iso, now_iso
from matching.domain.availability import offers_for
from matching.domain.browse import cities, idle_europe, idle_nearby, nearest_district
from matching.domain.categories import category
from matching.domain.feasibility import assess_feasibility
from matching.domain.match import find_matches, sort_matches, track_record, trust_of
from matching.domain.pricing import PLATFORM_FEE_BPS, hours_for, quote_for
from matching.domain.reviews import summarise


@pytest.fixture(scope="module")
def world() -> World:
    return build_world()


@pytest.fixture(scope="module")
def now() -> str:
    return now_iso()


def plus(now: str, hours: float) -> str:
    return iso_from_ms(ms_from_iso(now) + int(hours * HOUR_MS))


def listing(world: World, id: str):
    found = next((l for l in world.listings if l.id == id), None)
    assert found, f"missing listing {id}"
    return found


def owner(world: World, id: str) -> Owner:
    found = next((o for o in world.owners if o.id == id), None)
    assert found, f"missing owner {id}"
    return found


@pytest.fixture(scope="module")
def saw(now: str) -> WindowRequest:
    return WindowRequest(
        mode="window",
        category="workshop",
        hours=2,
        earliest=now,
        latest=plus(now, 24 * 7),
        district="Kreuzberg",
        max_distance_km=10,
    )


@pytest.fixture(scope="module")
def brackets(now: str) -> BatchRequest:
    return BatchRequest(
        mode="batch",
        category="fabrication",
        quantity=500,
        material="Aluminium 6061",
        dims={"x": 120, "y": 80, "z": 25},
        tolerance_mm=0.05,
        deadline=plus(now, 24 * 21),
        district="Kreuzberg",
        max_distance_km=90,
    )


# 1 - seed integrity
def test_seed_integrity(world: World):
    owner_ids = {o.id for o in world.owners}
    listing_ids = {l.id for l in world.listings}
    for l in world.listings:
        assert l.owner_id in owner_ids, f"{l.id} has no owner"
        assert l.district in world.districts, f"{l.id} sits in an unknown district"
        assert category(l.category).mode == l.mode, f"{l.id} mode disagrees with its category"
    for s in world.slots:
        assert s.listing_id in listing_ids, f"slot {s.id} points at nothing"
        assert ms_from_iso(s.end) > ms_from_iso(s.start), f"slot {s.id} ends before it starts"
        wall = (ms_from_iso(s.end) - ms_from_iso(s.start)) / HOUR_MS
        assert s.hours_usable <= wall + 1e-9, f"slot {s.id} claims more usable hours than it lasts"
    for o in world.owners:
        assert o.on_time_jobs <= o.jobs_done, f"{o.id} was on time more often than it worked"


# 2 - a window request matches only window listings in that category
def test_window_request_matches_window_listings(world, now, saw):
    m = find_matches(saw, world, now)
    assert m, "no saw capacity found"
    for x in m:
        l = listing(world, x.listing_id)
        assert l.mode == "window", "a batch listing answered a window request"
        assert l.category == "workshop"


# 3 - a batch request matches only batch listings, and respects tolerance
def test_batch_request_respects_tolerance(world, now, brackets):
    m = find_matches(brackets, world, now)
    assert m, "no milling capacity found"
    for x in m:
        l = listing(world, x.listing_id)
        assert l.mode == "batch" and l.tolerance_mm is not None and l.tolerance_mm <= 0.05, (
            "a machine that cannot hold tolerance matched"
        )
    assert find_matches(brackets.model_copy(update={"tolerance_mm": 0.001}), world, now) == []


# 3b - the optional questions. A van has no tolerance and no materials: asking
#      for either is a blocker, not a crash, and not a silent pass.
def test_absent_tolerance_and_materials_block(world, brackets):
    van = next(l for l in world.listings if l.category == "freight" and l.tolerance_mm is None and not l.materials)
    pallets = brackets.model_copy(update={"category": "freight", "quantity": 3, "dims": None})
    fit = assess_feasibility(pallets, van)
    assert not fit.feasible
    assert "does not work to a tolerance" in fit.blockers
    assert "does not stock Aluminium 6061" in fit.blockers
    loose = pallets.model_copy(update={"tolerance_mm": None, "material": None})
    assert assess_feasibility(loose, van).feasible


# 4 - time actually constrains
def test_time_constrains(world, now, saw, brackets):
    assert find_matches(brackets.model_copy(update={"deadline": now}), world, now) == []
    assert find_matches(brackets.model_copy(update={"quantity": 500_000}), world, now) == []
    assert find_matches(saw.model_copy(update={"hours": 400}), world, now) == []


# 5 - booking limits are enforced in both directions
def test_booking_limits(world, saw):
    pa = listing(world, "l12")  # minimum 8 h
    events = saw.model_copy(update={"category": "events"})
    assert not assess_feasibility(events.model_copy(update={"hours": 2}), pa).feasible
    assert not assess_feasibility(events.model_copy(update={"hours": 200}), pa).feasible
    assert assess_feasibility(events.model_copy(update={"hours": 24}), pa).feasible


# 6 - offers sit inside their window, never overlap its end, and are ordered
def test_offers_inside_windows(world, now):
    drill = [s for s in world.slots if s.listing_id == "l8"]
    offers = offers_for(drill, 2, now, plus(now, 24 * 5))
    assert len(offers) > 3, "expected several drill slots this week"
    for o in offers:
        slot = next(s for s in drill if s.id == o.slot_id)
        assert ms_from_iso(o.start) >= ms_from_iso(slot.start)
        assert ms_from_iso(o.end) <= ms_from_iso(slot.end)
        assert ms_from_iso(o.start) >= ms_from_iso(now)
    starts = [ms_from_iso(o.start) for o in offers]
    assert starts == sorted(starts)


# 7 - pricing: the fee is inside the total, and the split always reconciles
def test_pricing_reconciles(world, saw, brackets):
    for req in (saw, brackets):
        for l in world.listings:
            q = quote_for(req, l)
            if not q:
                continue
            assert q.base + q.extra == q.total
            assert q.platform_fee + q.owner_net == q.total
            assert q.platform_fee == round(q.total * PLATFORM_FEE_BPS / 10_000 + 1e-9)
            assert isinstance(q.total, int)
    drill = quote_for(saw, listing(world, "l8"))
    assert drill and drill.hours == 2
    assert drill.total == 2 * 250


# 8 - batch hours come from throughput, not from the buyer
def test_batch_hours_from_throughput(world, brackets):
    mill = listing(world, "l20")
    assert mill.mode == "batch"
    assert hours_for(brackets, mill) == mill.setup_hours + 500 / mill.units_per_hour


# 9 - sorting does what it says
def test_sorting(world, now, brackets):
    m = find_matches(brackets, world, now)
    by_price = [x.quote.total for x in sort_matches(m, "price")]
    assert by_price == sorted(by_price)
    by_soon = [ms_from_iso(x.start) for x in sort_matches(m, "soonest")]
    assert by_soon == sorted(by_soon)


# 10 - THE LOOP: a clean record lifts an owner above an identical one with none
def test_outcomes_compound(world, now, brackets):
    def twin(id: str, rated: bool) -> Owner:
        return owner(world, "b2").model_copy(
            update={
                "id": id,
                "name": id,
                "rating_sum": 25 if rated else 0,
                "jobs_done": 5 if rated else 0,
                "on_time_jobs": 5 if rated else 0,
            }
        )

    base = listing(world, "l20")
    w = World(
        owners=[twin("rated", True), twin("unrated", False)],
        listings=[
            base.model_copy(update={"id": "lA", "owner_id": "rated"}),
            base.model_copy(update={"id": "lB", "owner_id": "unrated"}),
        ],
        slots=[
            Slot(id="sA", listing_id="lA", start=plus(now, 24), end=plus(now, 24 * 6), hours_usable=90),
            Slot(id="sB", listing_id="lB", start=plus(now, 24), end=plus(now, 24 * 6), hours_usable=90),
        ],
        districts=world.districts,
    )
    m = find_matches(brackets, w, now)
    assert len(m) == 2
    assert m[0].owner_id == "rated", "a clean record did not lift the ranking"


# 11 - the same loop on the real seed, in both booking modes
@pytest.mark.parametrize("which", ["window", "batch"])
def test_clean_booking_never_hurts(world, now, saw, brackets, which):
    req = saw if which == "window" else brackets
    before = find_matches(req, world, now)
    assert len(before) >= 2
    target = before[1].owner_id
    was_at = next(i for i, m in enumerate(before) if m.owner_id == target)

    rated = world.model_copy(
        update={
            "owners": [
                apply_outcome(o, Outcome(on_time=True, quality=5)) if o.id == target else o for o in world.owners
            ]
        }
    )
    after = find_matches(req, rated, now)
    now_at = next(i for i, m in enumerate(after) if m.owner_id == target)
    assert trust_of(owner(world, target)) <= trust_of(owner(rated, target))
    assert 0 <= now_at <= was_at


# 12 - copy that gets rendered must be grammatical at the boundaries
def test_track_record_copy(world):
    o1 = owner(world, "o1")
    assert track_record(o1.model_copy(update={"jobs_done": 1, "on_time_jobs": 1})).startswith("1 booking · ")
    assert track_record(o1.model_copy(update={"jobs_done": 2, "on_time_jobs": 1})).startswith("2 bookings · 50% ")
    assert track_record(o1.model_copy(update={"jobs_done": 0, "on_time_jobs": 0})) == "New on Cappy"


# 13 - the headline number
def test_headline(world, now):
    near = idle_nearby(world, "Kreuzberg", 5, now, 24)
    wide = idle_nearby(world, "Kreuzberg", 90, now, 24)
    assert near.hours > 0
    assert wide.hours >= near.hours
    assert wide.listings >= near.listings
    assert near.free_now_count <= near.listings
    assert near.owners <= near.listings
    assert near.hours <= near.listings * 24 + 1e-6
    assert isinstance(near.value, int)
    assert idle_nearby(world, "Kreuzberg", 5, plus(now, 24 * 365), 24).hours == 0


# 14 - every listing must be bookable at its own minimum
def test_every_listing_bookable(world):
    for l in world.listings:
        if not l.active:
            continue
        mine = [s for s in world.slots if s.listing_id == l.id]
        assert mine, f"{l.id} ({l.title}) has no idle windows at all"
        need = l.min_hours if l.mode == "window" else l.setup_hours + 1
        longest = max(s.hours_usable for s in mine)
        assert longest >= need, f"{l.id} needs {need}h but its longest window is {longest}h"


# 15 - Europe
def test_europe(world, now):
    for d in world.districts.values():
        assert d.city
        assert len(d.country) == 2 and d.country.isupper()
    lst = cities(world, now)
    assert len(lst) >= 5
    for c in lst:
        assert c.listings > 0
        assert c.idle.hours > 0, f"{c.city} has listings but no capacity this week"
    hours = [c.idle.hours for c in lst]
    assert hours == sorted(hours, reverse=True)
    europe = idle_europe(world, now)
    assert abs(europe.hours - sum(hours)) < 1e-6
    assert europe.hours > idle_nearby(world, "Kreuzberg", 5, now, 24).hours


# 16 - turning a real GPS fix into a market
def test_nearest_district(world):
    def at(name: str):
        d = world.districts[name]
        return nearest_district(world, d.lat, d.lng)

    assert at("Kreuzberg").district.name == "Kreuzberg"
    assert at("Kreuzberg").km < 0.001
    assert at("Navigli").district.metro == "Milan"
    assert at("Marvila").district.metro == "Lisbon"
    assert nearest_district(world, 48.8566, 2.3522).district.metro == "Paris"
    hamburg = nearest_district(world, 53.5511, 9.9937)
    assert hamburg.km > 200
    assert nearest_district(world, 0, 0) is not None


# 17 - reviews tell the same story as the record they were written from
def test_reviews_match_the_record(world):
    vocab = set(REVIEW_TAGS)
    for o in world.owners:
        mine = [r for r in world.reviews if r.owner_id == o.id]
        if o.jobs_done == 0:
            assert not mine, f"{o.id} has no jobs but has reviews"
            continue
        s = summarise(mine)
        avg = o.rating_sum / o.jobs_done
        assert s.average is not None and abs(s.average - avg) <= 1, f"{o.id} reviews disagree with its rating"
        for lid in {r.listing_id for r in mine}:
            texts = [r.text for r in mine if r.listing_id == lid]
            assert len(set(texts)) == len(texts), f"{lid} repeats a review"
        for r in mine:
            assert 1 <= r.rating <= 5
            assert set(r.tags) <= vocab, f"unknown tag on {r.id}"
    empty = summarise([])
    assert (empty.count, empty.average, empty.on_time_share, empty.top_tags) == (0, None, None, [])
