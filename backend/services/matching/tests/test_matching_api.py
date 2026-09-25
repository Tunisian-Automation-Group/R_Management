"""The matching API, against fake upstreams: no database, no network."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cappy_common.errors import NotFound
from cappy_common.fixtures import build_world
from cappy_common.models import World
from cappy_common.testing import TestIssuer
from cappy_common.timeutil import DAY_MS, HOUR_MS, iso_from_ms, ms_from_iso, now_iso, now_ms
from matching.clients import Bookings, Catalog
from matching.main import build_app
from matching.settings import Settings

INTERNAL = {"X-Internal-Token": "i" * 40}


class FakeCatalog(Catalog):
    """Serves the demo world. The real catalog narrows candidates in SQL; the
    domain rules applied afterwards are what these tests pin down."""

    def __init__(self) -> None:
        self.world = build_world()
        self.calls: list[str] = []

    async def candidates(self, *, origin, max_km, start, until, category, exclude_owner) -> World:  # noqa: ANN001
        self.calls.append("candidates")
        listings = [
            l
            for l in self.world.listings
            if (category is None or l.category == category) and (exclude_owner is None or l.owner_id != exclude_owner)
        ]
        return self.world.model_copy(update={"listings": listings})

    async def listing_context(self, listing_id, *, after, origin=None) -> World:  # noqa: ANN001
        self.calls.append("context")
        listing = next((l for l in self.world.listings if l.id == listing_id), None)
        if listing is None:
            raise NotFound(f"listing {listing_id} not found")
        return World(
            owners=[o for o in self.world.owners if o.id == listing.owner_id],
            listings=[listing],
            slots=[s for s in self.world.slots if s.listing_id == listing_id],
            districts=self.world.districts,
            reviews=[],
        )


class FakeBookings(Bookings):
    def __init__(self) -> None:
        self.taken: dict[str, list[tuple[int, int]]] = {}

    async def busy(self, listing_ids, start, until):  # noqa: ANN001
        return {lid: self.taken[lid] for lid in listing_ids if lid in self.taken}


@pytest.fixture()
def issuer():
    return TestIssuer()


@pytest.fixture()
def fakes():
    return FakeCatalog(), FakeBookings()


@pytest.fixture()
def client(fakes, issuer):
    catalog, bookings = fakes
    app = build_app(
        Settings(app_env="test", internal_token="i" * 40),
        catalog=catalog,
        bookings=bookings,
        verifier=issuer.verifier(),
    )
    with TestClient(app) as c:
        yield c


def _saw_requirement(**extra):
    return {
        "mode": "window",
        "category": "workshop",
        "hours": 2,
        "earliest": now_iso(),
        "latest": iso_from_ms(now_ms() + 7 * DAY_MS),
        "district": "Kreuzberg",
        "maxDistanceKm": 25,
        **extra,
    }


def test_vocabulary(client):
    assert [g["id"] for g in client.get("/groups").json()] == ["make", "move", "equip"]
    assert len(client.get("/categories").json()) == 9
    assert {c["group"] for c in client.get("/categories", params={"group": "move"}).json()} == {"move"}
    assert client.get("/categories", params={"group": "nope"}).status_code == 422
    assert "Ready on time" in client.get("/review-tags").json()


def test_matches_carry_what_a_card_needs_and_are_sorted(client):
    r = client.post("/matches", json={"requirement": _saw_requirement(), "sort": "price"})
    assert r.status_code == 200, r.text
    views = r.json()
    assert views
    totals = [v["match"]["quote"]["total"] for v in views]
    assert totals == sorted(totals)
    for v in views:
        assert v["listing"]["id"] == v["match"]["listingId"] and v["owner"]["id"] == v["match"]["ownerId"]
        assert v["listing"]["category"] == "workshop"


def test_you_never_see_your_own_listings(client, issuer):
    everyone = {
        v["listing"]["ownerId"] for v in client.post("/matches", json={"requirement": _saw_requirement()}).json()
    }
    assert "o1" in everyone
    mine = client.post("/matches", json={"requirement": _saw_requirement()}, headers=issuer.headers("o1")).json()
    assert mine and all(v["listing"]["ownerId"] != "o1" for v in mine)


def test_results_are_capped(client):
    r = client.post("/matches", json={"requirement": _saw_requirement(maxDistanceKm=2000), "limit": 3})
    assert len(r.json()) == 3
    assert client.post("/matches", json={"requirement": _saw_requirement(), "limit": 1000}).status_code == 422


def test_spotlight(client):
    spots = client.get("/browse/spotlight", params={"district": "Kreuzberg", "maxKm": 10}).json()
    assert spots and all(s["distanceKm"] <= 10 for s in spots)


def test_offers_skip_what_is_booked(client, fakes):
    _, bookings = fakes
    before = client.get("/listings/l9/offers", params={"hours": 2}).json()
    assert before
    first = before[0]
    bookings.taken["l9"] = [(ms_from_iso(first["start"]), ms_from_iso(first["end"]))]
    after = client.get("/listings/l9/offers", params={"hours": 2}).json()
    assert all(not (o["start"] < first["end"] and first["start"] < o["end"]) for o in after)


def test_match_for_offer_is_internal(client):
    offer = client.get("/listings/l9/offers", params={"hours": 2}).json()[0]
    body = {"requirement": _saw_requirement(), "listingId": "l9", **offer}
    assert client.post("/internal/match-for-offer", json=body).status_code == 403
    r = client.post("/internal/match-for-offer", json=body, headers=INTERNAL)
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["match"]["quote"]["total"] > 0 and view["match"]["start"] == offer["start"]
    assert view["listing"]["id"] == "l9" and view["owner"]["id"] == view["listing"]["ownerId"]


def test_match_for_offer_refuses_a_taken_window(client, fakes):
    _, bookings = fakes
    offer = client.get("/listings/l9/offers", params={"hours": 2}).json()[0]
    bookings.taken["l9"] = [(ms_from_iso(offer["start"]), ms_from_iso(offer["end"]))]
    body = {"requirement": _saw_requirement(), "listingId": "l9", **offer}
    r = client.post("/internal/match-for-offer", json=body, headers=INTERNAL)
    assert r.status_code == 409


def test_match_for_offer_refuses_bad_windows(client):
    offer = client.get("/listings/l9/offers", params={"hours": 2}).json()[0]
    base = {"requirement": _saw_requirement(), "listingId": "l9", **offer}
    wrong_length = {**base, "end": iso_from_ms(ms_from_iso(offer["start"]) + 5 * 3_600_000)}
    outside = {**base, "start": iso_from_ms(ms_from_iso(offer["start"]) - 365 * DAY_MS), "end": offer["start"]}
    for body, code in [(wrong_length, 422), (outside, 422), ({**base, "listingId": "nope"}, 404)]:
        assert client.post("/internal/match-for-offer", json=body, headers=INTERNAL).status_code == code, body


def test_quote_and_feasibility(client):
    q = client.post("/quote", json={"requirement": _saw_requirement(), "listingId": "l9"}).json()
    assert q["feasibility"]["feasible"] and q["quote"]["total"] == q["quote"]["platformFee"] + q["quote"]["ownerNet"]
    f = client.post("/feasibility", json={"requirement": _saw_requirement(hours=200), "listingId": "l9"}).json()
    assert not f["feasible"] and f["blockers"]


def test_nothing_starts_too_soon_for_the_owner_to_answer(client):
    soon = ms_from_iso(now_iso()) + 2 * HOUR_MS - 60_000
    offers = client.get("/listings/l9/offers", params={"hours": 2}).json()
    assert offers and all(ms_from_iso(o["start"]) >= soon for o in offers)
    early = {"slotId": offers[0]["slotId"], "start": now_iso(), "end": iso_from_ms(now_ms() + 2 * HOUR_MS)}
    body = {"requirement": _saw_requirement(), "listingId": "l9", **early}
    assert client.post("/internal/match-for-offer", json=body, headers=INTERNAL).status_code == 422


def test_shared_vocabulary_is_cacheable_at_the_edge(client):
    for path in ("/groups", "/categories", "/review-tags"):
        assert client.get(path).headers["cache-control"] == "public, max-age=300"


def test_search_keeps_working_when_booking_is_down(client, fakes):
    from cappy_common.errors import Unavailable

    _, bookings = fakes

    async def down(*a, **k):
        raise Unavailable("booking is down")

    bookings.busy = down
    assert client.post("/matches", json={"requirement": _saw_requirement()}).json()
    assert client.get("/listings/l9/offers", params={"hours": 2}).json()
    # Selling a window, though, needs booking to say it is free.
    offer = client.get("/listings/l9/offers", params={"hours": 2}).json()[0]
    body = {"requirement": _saw_requirement(), "listingId": "l9", **offer}
    assert client.post("/internal/match-for-offer", json=body, headers=INTERNAL).status_code == 503
