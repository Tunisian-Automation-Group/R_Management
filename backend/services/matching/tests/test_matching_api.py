"""The matching API, against fake upstreams: no database, no network."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from cappy_common.errors import NotFound, Unavailable
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

    async def listing_context(self, listing_id, *, after, origin=None, staff=False) -> World:  # noqa: ANN001
        self.calls.append("staff-context" if staff else "context")
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


class FakeRevocations:
    """Catalog's answer to "when did this person's sessions end?"."""

    def __init__(self) -> None:
        self.ended: dict[str, float] = {}
        self.down = False

    async def not_before(self, sub: str) -> float | None:
        if self.down:
            raise Unavailable("catalog is unreachable")
        return self.ended.get(sub)


@pytest.fixture()
def revocations():
    return FakeRevocations()


@pytest.fixture()
def issuer():
    return TestIssuer()


@pytest.fixture()
def fakes():
    return FakeCatalog(), FakeBookings()


@pytest.fixture()
def client(fakes, issuer, revocations):
    catalog, bookings = fakes
    app = build_app(
        Settings(app_env="test", internal_token="i" * 40),
        catalog=catalog,
        bookings=bookings,
        verifier=issuer.verifier(),
        revocations=revocations,
    )
    with TestClient(app, headers=issuer.headers("viewer-1")) as c:
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


def test_an_extension_finds_its_own_slot(client):
    # S-12: booking asks for the time after a booking, with no slot id.
    offer = client.get("/listings/l9/offers", params={"hours": 2}).json()[0]
    body = {"requirement": _saw_requirement(), "listingId": "l9", **offer, "slotId": "", "extension": True}
    r = client.post("/internal/match-for-offer", json=body, headers=INTERNAL)
    assert r.status_code == 200, r.text
    assert r.json()["match"]["slotId"] == offer["slotId"]
    closed = {**body, "start": iso_from_ms(ms_from_iso(offer["start"]) + 400 * DAY_MS)}
    closed["end"] = iso_from_ms(ms_from_iso(closed["start"]) + 2 * 3_600_000)
    assert (
        client.post("/internal/match-for-offer", json=closed, headers=INTERNAL).json()["error"]["code"]
        == "not_extendable"
    )
    no_slot = {**body, "extension": False}
    assert client.post("/internal/match-for-offer", json=no_slot, headers=INTERNAL).status_code == 404


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
    for path in ("/groups", "/categories", "/review-tags", "/ranking"):
        assert client.get(path).headers["cache-control"] == "public, max-age=300"


def test_the_ranking_page_is_the_ranker(client):
    """H-2 (P2B Art. 5): the published signals and weights are exactly the ones
    the ranker multiplies. Changing W changes this answer, or this test fails."""
    from matching.domain.match import SIGNALS, W

    body = client.get("/ranking", headers={"Authorization": ""}).json()
    assert (
        {s["key"]: s["weight"] for s in body["signals"]} == W == {"price": 0.3, "trust": 0.3, "soon": 0.2, "near": 0.2}
    )
    assert set(SIGNALS) == set(W) and all(s["description"] for s in body["signals"])
    assert body["signals"][0]["weight"] >= body["signals"][-1]["weight"] and body["textSearch"] == "newest first"


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


def test_every_category_is_tagged_for_dac7(client):
    tags = {c["id"]: c["dac7"] for c in client.get("/categories").json()}
    assert set(tags.values()) <= {"personal_service", "immovable_property", "transport", "out_of_scope"}
    assert tags["warehousing"] == "immovable_property" and tags["events"] == "out_of_scope"


def test_offers_can_be_spread_over_days(client):
    # V6-23: a long window's starts used up the limit on the first days.
    few = client.get("/listings/l9/offers", params={"hours": 2, "limit": 500, "perDay": 2}).json()
    days = {o["start"][:10] for o in few}
    assert all(sum(o["start"][:10] == d for o in few) <= 2 for d in days)
    assert len(days) > 1


def test_staff_see_a_held_listings_offers_and_quote(client, fakes, issuer):
    # V6-2: only staff, and the context is asked for with held listings in.
    catalog, _ = fakes
    staff = {"Authorization": f"Bearer {issuer.token('staff-1', **{'cognito:groups': ['admin']})}"}
    assert client.get("/admin/listings/l9/offers", params={"hours": 2}).status_code == 403
    r = client.get("/admin/listings/l9/offers", params={"hours": 2}, headers=staff)
    assert r.status_code == 200 and r.json() and catalog.calls[-1] == "staff-context"
    q = client.post("/admin/quote", json={"listingId": "l9", "requirement": _saw_requirement()}, headers=staff)
    assert q.status_code == 200 and q.json()["quote"]["total"] > 0


def test_a_session_ended_elsewhere_is_refused_here_too(client, revocations):
    """Sign out everywhere ends the old access token in matching at once, not
    after its 15 minutes (P-24): matching asks catalog when sessions ended."""
    body = {"requirement": _saw_requirement()}
    assert client.post("/matches", json=body).status_code == 200
    revocations.ended["viewer-1"] = time.time() + 60  # after this token was issued
    r = client.post("/matches", json=body)
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"


def test_catalog_down_is_an_outage_not_a_sign_out(client, revocations):
    # A 401 would make the app sign the person out over a blip.
    revocations.down = True
    assert client.post("/matches", json={"requirement": _saw_requirement()}).status_code == 503
