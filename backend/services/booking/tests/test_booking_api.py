from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from booking.clients import AccountsClient, CatalogClient, MatchingClient, Offer
from booking.main import build_app
from booking.settings import Settings
from booking.workers import accept_due, reconcile_world, seed_inbox
from cappy_common.errors import NotFound
from cappy_common.events import BOOKING_RATED, BOOKING_REQUESTED, BOOKING_STATUS_CHANGED, CATALOG_CHANGED
from cappy_common.models import Match, Quote
from cappy_common.timeutil import HOUR_MS, iso_from_ms, now_ms

NOW = iso_from_ms(now_ms())
LATER = iso_from_ms(now_ms() + 5 * 24 * HOUR_MS)
START = iso_from_ms(now_ms() + 2 * HOUR_MS)
END = iso_from_ms(now_ms() + 4 * HOUR_MS)

# l9 is the demo user's own saw; l8 is a neighbour's drill.
OWNERS = {"l9": "o1", "l8": "o5"}


class FakeMatching(MatchingClient):
    """Prices every window at a flat rate; knows two listings."""

    async def match_for_offer(self, requirement, listing_id, slot_id, start, end):
        if listing_id not in OWNERS:
            raise NotFound(f"listing {listing_id} not found")
        return Match(
            listing_id=listing_id,
            owner_id=OWNERS[listing_id],
            slot_id=slot_id,
            start=start,
            end=end,
            score=1,
            confidence=1,
            reasons=["2 hours of idle time", "0.0 km away", "New on Cappy"],
            quote=Quote(hours=2, base=500, extra=0, extra_label="No extras", total=500, platform_fee=75, owner_net=425),
            distance_km=0,
        )

    async def first_offer(self, listing_id, hours, from_, until):
        return Offer(slot_id="w1", start=START, end=END)


def _req():
    return {
        "mode": "window",
        "category": "workshop",
        "hours": 2,
        "earliest": NOW,
        "latest": LATER,
        "district": "Kreuzberg",
        "maxDistanceKm": 10,
    }


def _create(client, listing_id="l8", user=None):
    headers = {"X-Cappy-User": user} if user else {}
    return client.post(
        "/bookings",
        json={"requirement": _req(), "listingId": listing_id, "slotId": "w9", "start": START, "end": END},
        headers=headers,
    )


class FakeAccounts(AccountsClient):
    """o1 has signed up; nobody else has."""

    def __init__(self, registered=("o1",)):
        self.registered = set(registered)

    async def has_account(self, owner_id):
        return owner_id in self.registered


def _settings(**over):
    # Everything explicit, so the local .env (which turns the demo user off for
    # the real stack) cannot change what these tests mean.
    base = dict(
        database_url="sqlite+aiosqlite://",
        event_bus_url="memory://",
        demo_user_id="o1",
        demo_auto_accept_seconds=0.01,
        demo_seed_inbox=False,
        run_background_workers=False,
        cors_origins="",
    )
    return Settings(**{**base, **over})


@pytest.fixture()
def app():
    return build_app(_settings(), matching=FakeMatching(), accounts=FakeAccounts())


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def test_request_stores_server_quote_and_publishes(client, app):
    r = _create(client)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "requested" and b["id"].startswith("bk_")
    assert b["match"]["quote"]["total"] == 500 and b["match"]["ownerId"] == "o5"
    assert "requesterId" not in b and "outcome" not in b and "declineReason" not in b
    assert app.state.bus.published[-1][0] == BOOKING_REQUESTED


def test_cannot_book_own_listing_or_unknown(client):
    assert _create(client, listing_id="l9").status_code == 422
    assert _create(client, listing_id="l99").status_code == 404


def test_visibility_and_inbox_shape(client):
    bid = _create(client).json()["id"]
    mine = client.get("/bookings").json()
    assert [b["id"] for b in mine] == [bid]
    assert "requesterId" not in mine[0]

    theirs = client.get("/bookings", headers={"X-Cappy-User": "o5"}).json()
    assert theirs[0]["requesterId"] == "o1", "the owner's inbox must say who asked"

    assert client.get("/bookings", headers={"X-Cappy-User": "o3"}).json() == []
    assert client.get(f"/bookings/{bid}", headers={"X-Cappy-User": "o3"}).status_code == 404


def test_full_lifecycle_and_rating(client, app):
    bid = _create(client).json()["id"]
    o5 = {"X-Cappy-User": "o5"}

    assert client.post(f"/bookings/{bid}/start").status_code == 409
    assert client.post(f"/bookings/{bid}/accept").status_code == 403
    assert client.post(f"/bookings/{bid}/accept", headers=o5).json()["status"] == "accepted"
    assert client.post(f"/bookings/{bid}/start").json()["status"] == "active"
    assert client.post(f"/bookings/{bid}/complete").json()["status"] == "completed"

    assert client.post(f"/bookings/{bid}/rate", json={"onTime": True, "quality": 5}, headers=o5).status_code == 403
    outcome = {"onTime": True, "quality": 5, "note": "spotless", "tags": ["Ready on time", "Clear handover"]}
    r = client.post(f"/bookings/{bid}/rate", json=outcome)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == outcome
    assert client.post(f"/bookings/{bid}/rate", json={"onTime": True, "quality": 5}).status_code == 409

    topic, payload = app.state.bus.published[-1]
    assert topic == BOOKING_RATED
    assert payload["ownerId"] == "o5" and payload["listingId"] == "l8" and payload["requesterId"] == "o1"
    assert payload["outcome"] == outcome
    assert payload["at"] == END, "a review is dated at the end of the booked window"
    assert BOOKING_STATUS_CHANGED in [t for t, _ in app.state.bus.published]


def test_rating_tags_come_from_the_vocabulary(client):
    bid = _create(client).json()["id"]
    o5 = {"X-Cappy-User": "o5"}
    client.post(f"/bookings/{bid}/accept", headers=o5)
    client.post(f"/bookings/{bid}/start")
    client.post(f"/bookings/{bid}/complete")
    r = client.post(f"/bookings/{bid}/rate", json={"onTime": True, "quality": 4, "tags": ["Cheap"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid"
    r = client.post(f"/bookings/{bid}/rate", json={"onTime": True, "quality": 4, "tags": ["Fair price", "Fair price"]})
    assert r.status_code == 200 and r.json()["outcome"]["tags"] == ["Fair price"]


def test_decline_needs_a_reason(client):
    bid = _create(client).json()["id"]
    o5 = {"X-Cappy-User": "o5"}
    assert client.post(f"/bookings/{bid}/decline", json={"reason": "  "}, headers=o5).status_code == 422
    r = client.post(f"/bookings/{bid}/decline", json={"reason": "Away that weekend"}, headers=o5)
    assert r.json()["status"] == "declined" and r.json()["declineReason"] == "Away that weekend"


def test_cancel_by_either_side(client):
    a = _create(client).json()["id"]
    b = _create(client).json()["id"]
    assert client.post(f"/bookings/{a}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/bookings/{b}/cancel", headers={"X-Cappy-User": "o5"}).json()["status"] == "cancelled"
    assert client.post(f"/bookings/{a}/cancel").status_code == 409


def test_demo_hosts_accept_after_a_moment(client, app):
    bid = _create(client).json()["id"]
    time.sleep(0.05)
    assert client.portal.call(accept_due, app) == 1
    assert client.get(f"/bookings/{bid}").json()["status"] == "accepted"
    assert client.portal.call(accept_due, app) == 0


def test_demo_user_is_never_simulated():
    with TestClient(build_app(_settings(), matching=FakeMatching(), accounts=FakeAccounts())) as c:
        # o5 asks for o1's saw: that lands in the real Earn inbox.
        r = _create(c, listing_id="l9", user="o5")
        assert r.status_code == 201
        time.sleep(0.05)
        assert c.portal.call(accept_due, c.app) == 0
        assert c.get("/bookings").json()[0]["status"] == "requested"


def test_seed_inbox_and_reset(client, app):
    assert client.get("/bookings").json() == []
    app.state.settings.demo_seed_inbox = True
    assert client.portal.call(seed_inbox, app) is True
    assert client.portal.call(seed_inbox, app) is False, "never seeds twice"

    inbox = client.get("/bookings").json()
    assert len(inbox) == 1
    b = inbox[0]
    assert b["id"] == "bk_seed_1" and b["requesterId"] == "o17" and b["status"] == "requested"
    assert b["match"]["listingId"] == "l9" and b["match"]["ownerId"] == "o1"
    assert b["requirement"]["category"] == "workshop" and b["requirement"]["hours"] == 2

    _create(client)
    assert len(client.get("/bookings").json()) == 2
    assert client.post("/admin/reset").status_code == 204
    after = client.get("/bookings").json()
    assert [x["id"] for x in after] == ["bk_seed_1"]


# --- the world moved on -------------------------------------------------------


class FakeCatalog(CatalogClient):
    def __init__(self, version="seed-a"):
        self.version = version

    async def world_version(self):
        return self.version


def test_bookings_against_a_vanished_world_are_dropped_at_startup():
    """A catalog reseeded from a newer seed.ts serves a different world; the
    bookings on disk point at listings that no longer exist and go."""
    catalog = FakeCatalog("seed-a")
    with TestClient(build_app(_settings(), matching=FakeMatching(), catalog=catalog, accounts=FakeAccounts())) as c:
        assert c.portal.call(reconcile_world, c.app) is False, "first run: nothing to compare with"
        _create(c)
        assert c.portal.call(reconcile_world, c.app) is False, "same world, bookings stay"
        assert len(c.get("/bookings").json()) == 1
        catalog.version = "seed-b"
        assert c.portal.call(reconcile_world, c.app) is True
        assert c.get("/bookings").json() == []
        assert c.portal.call(reconcile_world, c.app) is False, "remembered the new world"


def test_catalog_reset_event_wipes_and_reseeds(client, app):
    app.state.catalog = FakeCatalog()
    app.state.settings.demo_seed_inbox = True
    _create(client)
    client.portal.call(app.state.bus.publish, CATALOG_CHANGED, {"what": "listing", "id": "l8"})
    assert len(client.get("/bookings").json()) == 1, "an ordinary catalog change is not a reset"
    client.portal.call(app.state.bus.publish, CATALOG_CHANGED, {"what": "reset", "reason": "seed changed"})
    after = client.get("/bookings").json()
    assert [b["id"] for b in after] == ["bk_seed_1"], "wiped, then the inbox request came back"


def test_unversioned_database_keeps_what_still_reads_and_drops_the_rest(client, app):
    """A booking database from before the world was versioned: the one row
    written against a category that no longer exists goes, the good one stays."""
    from booking.tables import BookingRow

    app.state.catalog = FakeCatalog("seed-a")
    good = _create(client).json()["id"]

    async def plant_old_row():
        async with app.state.db.session() as s, s.begin():
            fresh = await s.get(BookingRow, good)
            s.add(
                BookingRow(
                    id="bk_old",
                    requester_id="o17",
                    owner_id="o1",
                    listing_id="l1",
                    status="requested",
                    created_at=NOW,
                    updated_at=NOW,
                    requirement={**fresh.requirement, "category": "laundry"},
                    match=fresh.match,
                    auto_accept_at=None,
                )
            )

    client.portal.call(plant_old_row)
    with pytest.raises(ValidationError):
        client.get("/bookings")  # the old row poisons the whole list
    assert client.portal.call(reconcile_world, app) is True
    assert [b["id"] for b in client.get("/bookings").json()] == [good]
    assert client.portal.call(reconcile_world, app) is False


def test_client_may_choose_the_booking_id(client):
    body = {"requirement": _req(), "listingId": "l8", "slotId": "w9", "start": START, "end": END, "id": "bk_mug4abc123"}
    r = client.post("/bookings", json=body)
    assert r.status_code == 201 and r.json()["id"] == "bk_mug4abc123"
    assert client.post("/bookings", json=body).status_code == 409, "the same id twice is a conflict"
    assert client.post("/bookings", json={**body, "id": "not-ours"}).status_code == 422


def test_a_signed_up_host_is_never_simulated():
    """Once someone has an account, requests to them wait for them."""
    with TestClient(
        build_app(_settings(demo_user_id=""), matching=FakeMatching(), accounts=FakeAccounts(registered={"o5"}))
    ) as c:
        r = _create(c, listing_id="l8", user="u_buyer")
        assert r.status_code == 201
        time.sleep(0.05)
        assert c.portal.call(accept_due, c.app) == 0
        assert c.get("/bookings", headers={"X-Cappy-User": "u_buyer"}).json()[0]["status"] == "requested"


def test_nobody_without_a_session_when_the_demo_user_is_off():
    with TestClient(build_app(_settings(demo_user_id=""), matching=FakeMatching(), accounts=FakeAccounts())) as c:
        assert c.get("/bookings").status_code == 401
        assert c.get("/bookings").json()["error"]["code"] == "unauthorized"
        assert _create(c).status_code == 401
        assert c.get("/bookings", headers={"X-Cappy-User": "u_x"}).status_code == 200
