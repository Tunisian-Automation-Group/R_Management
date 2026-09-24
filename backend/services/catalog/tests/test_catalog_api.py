from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cappy_common.events import BOOKING_RATED, CATALOG_CHANGED
from cappy_common.timeutil import HOUR_MS, iso_from_ms, now_ms
from catalog.main import build_app
from catalog.settings import Settings

# The demo world, as the frontend's seed.ts ships it (see scripts/export-seed.mjs).
OWNERS, LISTINGS, SLOTS, REVIEWS = 70, 78, 250, 275


@pytest.fixture()
def app():
    return build_app(
        Settings(
            database_url="sqlite+aiosqlite://",
            event_bus_url="memory://",
            seed_on_start=True,
            cors_origins="",
        )
    )


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def _listing(owner="o1", id="own_test1", **extra):
    return {
        "id": id,
        "ownerId": owner,
        "category": "workshop",
        "mode": "window",
        "title": "Cordless drill",
        "blurb": "Makita, two batteries",
        "district": "Kreuzberg",
        "instructions": "Ring the bell",
        "rules": ["Bring it back charged"],
        "active": True,
        "ratePerHour": 200,
        "minHours": 2,
        "maxHours": 8,
        "extraFee": 0,
        "extraLabel": "",
        **extra,
    }


def _batch_listing(owner="o1", id="own_van1"):
    """A van: no materials, no tolerance. The optional questions stay absent."""
    return {
        "id": id,
        "ownerId": owner,
        "category": "freight",
        "mode": "batch",
        "title": "Half a Sprinter to Leipzig",
        "blurb": "Thursday run, four pallet spaces free",
        "district": "Kreuzberg",
        "instructions": "Dock 3",
        "rules": ["Wrapped pallets only"],
        "active": True,
        "machine": "Mercedes Sprinter",
        "maxDims": {"x": 1200, "y": 800, "z": 1800},
        "unitsPerHour": 2,
        "setupHours": 0.5,
        "ratePerHour": 4500,
        "setupFee": 2000,
    }


def _slots(listing_id="own_test1", n=2):
    base = now_ms() + HOUR_MS
    return [
        {
            "id": f"{listing_id}_w{d}",
            "listingId": listing_id,
            "start": iso_from_ms(base + d * 24 * HOUR_MS),
            "end": iso_from_ms(base + d * 24 * HOUR_MS + 8 * HOUR_MS),
            "hoursUsable": 8,
        }
        for d in range(n)
    ]


def test_world_is_seeded_in_frontend_shape(client):
    w = client.get("/world").json()
    assert (len(w["owners"]), len(w["listings"]), len(w["slots"]), len(w["reviews"])) == (
        OWNERS,
        LISTINGS,
        SLOTS,
        REVIEWS,
    )
    assert "Kreuzberg" in w["districts"] and w["districts"]["Potsdam"]["metro"] == "Berlin"
    saw = next(l for l in w["listings"] if l["id"] == "l9")
    assert saw["ownerId"] == "o1" and saw["ratePerHour"] == 400 and saw["mode"] == "window"
    assert saw["category"] == "workshop" and saw["photos"][0].startswith("https://")
    mill = next(l for l in w["listings"] if l["id"] == "l20")
    assert "maxDims" in mill and "unitsPerHour" in mill and mill["toleranceMm"] == 0.05
    assert w["slots"][0]["start"].endswith("Z")
    rv = next(r for r in w["reviews"] if r["listingId"] == "l8")
    assert rv["id"].startswith("rv_l8_") and rv["ownerId"] == "o5" and rv["at"].endswith("Z")
    assert set(rv) >= {"author", "initials", "rating", "onTime", "text", "tags"}


def test_optional_fields_are_omitted_not_null(client):
    """The app runs `listing.toleranceMm === undefined` on what it loads: a null
    there would read as a tolerance of zero."""
    w = client.get("/world").json()
    van = next(l for l in w["listings"] if l["mode"] == "batch" and "toleranceMm" not in l)
    assert "materials" not in van or isinstance(van["materials"], list)
    assert "authorId" not in w["reviews"][0]
    for l in w["listings"]:
        assert None not in l.values(), l["id"]


def test_lookups(client):
    assert client.get("/owners/o1").json()["name"] == "Nadia Brandt"
    assert client.get("/owners/nobody").status_code == 404
    assert client.get("/listings/l9").json()["title"].startswith("Festool")
    assert len(client.get("/listings", params={"ownerId": "o1"}).json()) >= 1
    assert all(s["listingId"] == "l9" for s in client.get("/listings/l9/slots").json())
    reviews = client.get("/listings/l8/reviews").json()
    assert reviews and all(r["listingId"] == "l8" for r in reviews)
    ats = [r["at"] for r in reviews]
    assert ats == sorted(ats, reverse=True), "reviews come newest first"
    assert client.get("/listings/nope/reviews").status_code == 404
    assert len(client.get("/reviews").json()) == REVIEWS


def test_me(client):
    me = client.get("/me").json()
    assert me["id"] == "o1" and me["homeDistrict"] == "Kreuzberg" and me["owner"]["initials"] == "NB"
    stranger = client.get("/me", headers={"X-Cappy-User": "u_new"}).json()
    assert stranger == {"id": "u_new", "homeDistrict": "Kreuzberg"}


def test_create_pause_resume_remove_listing(client, app):
    r = client.post("/listings", json={"listing": _listing(), "slots": _slots()})
    assert r.status_code == 201, r.text
    assert client.get("/listings/own_test1").json()["active"] is True
    assert len(client.get("/listings/own_test1/slots").json()) == 2

    assert client.post("/listings", json={"listing": _listing(), "slots": []}).status_code == 409

    assert client.post("/listings/own_test1/pause").json()["active"] is False
    assert client.post("/listings/own_test1/resume").json()["active"] is True

    client.put("/saved/own_test1")
    assert client.delete("/listings/own_test1").status_code == 204
    assert client.get("/listings/own_test1").status_code == 404
    assert all(s["listingId"] != "own_test1" for s in client.get("/world").json()["slots"])
    assert "own_test1" not in client.get("/saved").json(), "a removed listing drops out of the shortlist"

    topics = [t for t, _ in app.state.bus.published]
    assert topics.count(CATALOG_CHANGED) == 4


def test_batch_listing_without_optional_questions_round_trips(client):
    r = client.post("/listings", json={"listing": _batch_listing(), "slots": _slots("own_van1", 1)})
    assert r.status_code == 201, r.text
    van = client.get("/listings/own_van1").json()
    assert van["machine"] == "Mercedes Sprinter"
    assert "materials" not in van and "toleranceMm" not in van and "photos" not in van


def test_ownership_is_enforced(client):
    r = client.post("/listings", json={"listing": _listing(owner="o5"), "slots": []})
    assert r.status_code == 403
    r = client.post("/listings", json={"listing": _listing(owner="o5"), "slots": []}, headers={"X-Cappy-User": "o5"})
    assert r.status_code == 201
    assert client.post("/listings/own_test1/pause").status_code == 403
    assert client.delete("/listings/l9", headers={"X-Cappy-User": "o5"}).status_code == 403


def test_listing_validation(client):
    bad_mode = {**_listing(), "category": "fabrication"}
    assert client.post("/listings", json={"listing": bad_mode, "slots": []}).status_code == 422
    old_category = {**_listing(), "category": "laundry"}
    assert client.post("/listings", json={"listing": old_category, "slots": []}).status_code == 422
    bad_district = {**_listing(), "district": "Atlantis"}
    assert client.post("/listings", json={"listing": bad_district, "slots": []}).status_code == 422
    greedy = _slots(n=1)
    greedy[0]["hoursUsable"] = 99
    assert client.post("/listings", json={"listing": _listing(), "slots": greedy}).status_code == 422
    backwards = _slots(n=1)
    backwards[0]["start"], backwards[0]["end"] = backwards[0]["end"], backwards[0]["start"]
    assert client.post("/listings", json={"listing": _listing(), "slots": backwards}).status_code == 422
    data_url = _listing(photos=["data:image/png;base64,AAAA"])
    assert client.post("/listings", json={"listing": data_url, "slots": []}).status_code == 422
    too_many = _listing(photos=[f"https://x.test/{i}.jpg" for i in range(13)])
    assert client.post("/listings", json={"listing": too_many, "slots": []}).status_code == 422
    fine = _listing(photos=["https://x.test/cover.jpg"])
    assert client.post("/listings", json={"listing": fine, "slots": []}).status_code == 201


def test_saved_is_per_user_and_idempotent(client):
    assert client.get("/saved").json() == []
    assert client.put("/saved/l8").json() == ["l8"]
    assert client.put("/saved/l8").json() == ["l8"], "hearting twice is one heart"
    assert client.put("/saved/l9").json() == ["l9", "l8"], "newest first"
    assert client.get("/saved", headers={"X-Cappy-User": "o5"}).json() == []
    assert client.put("/saved/nope").status_code == 404
    assert client.delete("/saved/l8").json() == ["l9"]
    assert client.delete("/saved/l8").json() == ["l9"], "unhearting twice is fine too"


def test_outcome_endpoint_and_event(client, app):
    before = client.get("/owners/o5").json()
    after = client.post("/owners/o5/outcomes", json={"onTime": True, "quality": 5}).json()
    assert after["jobsDone"] == before["jobsDone"] + 1
    assert after["ratingSum"] == before["ratingSum"] + 5
    assert after["onTimeJobs"] == before["onTimeJobs"] + 1

    n_reviews = len(client.get("/listings/l8/reviews").json())
    rated = {
        "bookingId": "bk_x",
        "ownerId": "o5",
        "listingId": "l8",
        "requesterId": "o1",
        "outcome": {"onTime": False, "quality": 3, "note": "Ran a day late", "tags": ["Fair price"]},
        "at": "2026-09-20T16:00:00.000Z",
    }
    client.portal.call(app.state.bus.publish, BOOKING_RATED, rated)
    again = client.get("/owners/o5").json()
    assert again["jobsDone"] == before["jobsDone"] + 2
    assert again["onTimeJobs"] == before["onTimeJobs"] + 1

    reviews = client.get("/listings/l8/reviews").json()
    assert len(reviews) == n_reviews + 1
    mine = next(r for r in reviews if r["id"] == "rv_bk_x")
    assert mine == {
        "id": "rv_bk_x",
        "listingId": "l8",
        "ownerId": "o5",
        "author": "Nadia Brandt",
        "initials": "NB",
        "authorId": "o1",
        "rating": 3,
        "onTime": False,
        "text": "Ran a day late",
        "tags": ["Fair price"],
        "at": "2026-09-20T16:00:00.000Z",
    }

    # Redelivery (Redis Streams promises at-least-once) must not double-count.
    client.portal.call(app.state.bus.publish, BOOKING_RATED, rated)
    assert client.get("/owners/o5").json()["jobsDone"] == before["jobsDone"] + 2
    assert len(client.get("/listings/l8/reviews").json()) == n_reviews + 1

    # A rating for a listing that has since gone still moves the record.
    gone = {**rated, "bookingId": "bk_y", "listingId": "l_removed"}
    client.portal.call(app.state.bus.publish, BOOKING_RATED, gone)
    assert client.get("/owners/o5").json()["jobsDone"] == before["jobsDone"] + 3


def test_reset_restores_the_seed(client):
    client.post("/listings", json={"listing": _listing(), "slots": _slots()})
    client.post("/listings/l9/pause")
    client.put("/saved/l8")
    assert client.post("/admin/reset").status_code == 204
    w = client.get("/world").json()
    assert len(w["listings"]) == LISTINGS and len(w["reviews"]) == REVIEWS
    assert next(l for l in w["listings"] if l["id"] == "l9")["active"] is True
    assert client.get("/saved").json() == []


def test_world_version_and_reseed_when_the_seed_changes(tmp_path):
    """A database seeded from an older seed.ts is rebuilt on startup, and the
    other services are told, rather than served with categories that no longer
    exist. A database on the current seed is left alone, hearts and all."""
    from cappy_common.fixtures import fingerprint
    from catalog.repository import CatalogRepository
    from catalog.seed import SEED_KEY

    # A file, because an in-memory SQLite dies with the engine on shutdown and
    # the point is what happens to a database that outlives the process.
    db = (tmp_path / "catalog.db").as_posix()
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", event_bus_url="memory://", cors_origins=""))

    with TestClient(app) as c:
        assert c.get("/world/version").json() == {"version": fingerprint()}
        c.put("/saved/l8")
        c.post("/listings", json={"listing": _listing(), "slots": _slots()})

        async def pretend_older_edition():
            async with app.state.db.session() as s, s.begin():
                await CatalogRepository(s).set_meta(SEED_KEY, "0000deadbeef0000")

        c.portal.call(pretend_older_edition)

    # Same database, new process.
    with TestClient(app) as c:
        assert c.get("/world/version").json()["version"] == fingerprint()
        assert len(c.get("/world").json()["listings"]) == LISTINGS, "the old edition's listings are gone"
        assert c.get("/saved").json() == []
        resets = [p for t, p in app.state.bus.published if t == CATALOG_CHANGED and p.get("what") == "reset"]
        assert resets and resets[-1]["reason"] == "seed changed"

    with TestClient(app) as c:
        c.put("/saved/l8")
    with TestClient(app) as c:
        assert c.get("/saved").json() == ["l8"], "a current world is not touched on restart"
