"""The catalog API: profiles, listings, photos, search, saved, candidates, ratings."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cappy_common.events import BOOKING_RATED, LISTING_CHANGED, PROFILE_CREATED, Event, reset_memory_broker
from cappy_common.fixtures import build_world
from cappy_common.ids import new_id
from cappy_common.testing import TestIssuer
from cappy_common.timeutil import HOUR_MS, iso_from_ms, now_iso, now_ms
from catalog.main import build_app
from catalog.media import DirectoryStore
from catalog.repository import CatalogRepository
from catalog.settings import Settings

INTERNAL = {"X-Internal-Token": "i" * 40}


@pytest.fixture()
def issuer():
    return TestIssuer()


@pytest.fixture()
def broker():
    return reset_memory_broker()


@pytest.fixture()
def app(issuer, broker, tmp_path):
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite://",
        internal_token="i" * 40,
        media_dir=str(tmp_path / "media"),
    )
    return build_app(settings, media_store=DirectoryStore(str(tmp_path / "media")), verifier=issuer.verifier())


def _run(app, coro_fn):
    """Run a coroutine against the app's database, on the client's loop."""
    return app.state._portal.call(coro_fn)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        app.state._portal = c.portal

        async def seed():
            async with app.state.db.transaction() as s:
                await CatalogRepository(s).load_seed(build_world())

        c.portal.call(seed)
        yield c


def flush(app):
    return app.state._portal.call(app.state.relay.flush)


def _hours_from_now(h: float) -> str:
    return iso_from_ms(now_ms() + int(h * HOUR_MS))


def _window_listing(**extra):
    return {
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


def _slot(start_h=2, end_h=20, usable=18):
    return {"start": _hours_from_now(start_h), "end": _hours_from_now(end_h), "hoursUsable": usable}


def _profile(client, issuer, sub="user-a", name="Ada Lovelace"):
    r = client.put("/me", json={"name": name, "kind": "person", "district": "Kreuzberg"}, headers=issuer.headers(sub))
    assert r.status_code == 200, r.text
    return r.json()


def _jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (3000, 2000), (200, 80, 40))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (52.0, 30.0, 0.0), 3: "E", 4: (13.0, 25.0, 0.0)}  # GPSInfo
    exif[0x010F] = "PhoneMaker"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


# --- identity and profiles -----------------------------------------------------------


def test_nobody_is_anybody_without_a_token(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"X-Cappy-User": "o1"}).status_code == 401
    assert client.get("/saved").status_code == 401


def test_profile_is_created_once_and_a_record_cannot_be_declared(client, issuer, app, broker):
    me = client.get("/me", headers=issuer.headers("user-a")).json()
    assert me == {"id": "user-a", "homeDistrict": "Kreuzberg"}  # no owner yet

    owner = _profile(client, issuer)
    assert owner["id"] == "user-a" and owner["initials"] == "AL"
    assert (owner["ratingSum"], owner["jobsDone"], owner["verified"]) == (0, 0, False)

    again = client.put(
        "/me",
        json={"name": "Ada L", "kind": "business", "district": "Neukölln", "ratingSum": 500, "jobsDone": 100},
        headers=issuer.headers("user-a"),
    ).json()
    assert again["kind"] == "business" and again["district"] == "Neukölln"
    assert (again["ratingSum"], again["jobsDone"]) == (0, 0)

    flush(app)
    assert [e.data["ownerId"] for e in broker.of_type(PROFILE_CREATED)] == ["user-a"]


def test_profile_needs_a_known_district(client, issuer):
    r = client.put("/me", json={"name": "Ada", "kind": "person", "district": "Atlantis"}, headers=issuer.headers("u"))
    assert r.status_code == 422


# --- listings ---------------------------------------------------------------------------


def test_listing_needs_a_profile(client, issuer):
    r = client.post("/listings", json={"listing": _window_listing(), "slots": []}, headers=issuer.headers("nobody"))
    assert r.status_code == 403


def test_server_mints_ids_and_ignores_the_client_s(client, issuer, app, broker):
    _profile(client, issuer)
    body = {"listing": _window_listing(id="l1", ownerId="o1"), "slots": [{**_slot(), "id": "s1", "listingId": "l1"}]}
    r = client.post("/listings", json=body, headers=issuer.headers("user-a"))
    assert r.status_code == 201, r.text
    created = r.json()
    lid = created["listing"]["id"]
    assert lid.startswith("ls_") and lid != "l1"
    assert created["listing"]["ownerId"] == "user-a"  # never the body's o1
    assert created["slots"][0]["id"].startswith("sl_") and created["slots"][0]["listingId"] == lid
    flush(app)
    assert broker.of_type(LISTING_CHANGED)[-1].data == {"listingId": lid, "change": "created"}


@pytest.mark.parametrize(
    "override, message",
    [
        ({"title": "x" * 121}, "title"),
        ({"instructions": "x" * 2001}, "instructions"),
        ({"rules": ["r"] * 13}, "rules"),
        ({"category": "fabrication"}, "booked by batch"),
        ({"district": "Atlantis"}, "district"),
        ({"ratePerHour": 0}, "ratePerHour"),
        ({"photos": ["https://evil.example/pixel.gif"]}, "uploaded"),
    ],
)
def test_listing_validation(client, issuer, override, message):
    _profile(client, issuer)
    r = client.post("/listings", json={"listing": _window_listing(**override)}, headers=issuer.headers("user-a"))
    assert r.status_code == 422 and message in r.json()["error"]["message"], r.text


def test_slots_are_validated(client, issuer):
    _profile(client, issuer)
    bad = [
        {"start": _hours_from_now(5), "end": _hours_from_now(2), "hoursUsable": 1},  # ends before it starts
        {"start": _hours_from_now(1), "end": _hours_from_now(3), "hoursUsable": 5},  # more usable than wall
        {"start": _hours_from_now(-9), "end": _hours_from_now(-1), "hoursUsable": 1},  # in the past
    ]
    for slot in bad:
        r = client.post(
            "/listings", json={"listing": _window_listing(), "slots": [slot]}, headers=issuer.headers("user-a")
        )
        assert r.status_code == 422, (slot, r.text)


def test_only_the_owner_manages_a_listing(client, issuer):
    _profile(client, issuer)
    lid = client.post(
        "/listings", json={"listing": _window_listing(), "slots": [_slot()]}, headers=issuer.headers("user-a")
    ).json()["listing"]["id"]
    intruder = issuer.headers("user-b")
    for method, path in [
        ("post", f"/listings/{lid}/pause"),
        ("delete", f"/listings/{lid}"),
        ("put", f"/listings/{lid}"),
        ("post", f"/listings/{lid}/slots"),
    ]:
        kwargs = (
            {"json": {"listing": _window_listing()} if method == "put" else []} if method in ("put", "post") else {}
        )
        r = getattr(client, method)(path, headers=intruder, **kwargs)
        assert r.status_code == 404, (method, path, r.text)

    owner = issuer.headers("user-a")
    assert client.post(f"/listings/{lid}/pause", headers=owner).json()["active"] is False
    # Paused: the owner still sees it; nobody else does.
    assert client.get(f"/listings/{lid}", headers=owner).status_code == 200
    assert client.get(f"/listings/{lid}").status_code == 404
    assert client.post(f"/listings/{lid}/resume", headers=owner).json()["active"] is True
    assert client.delete(f"/listings/{lid}", headers=owner).status_code == 204
    assert client.get(f"/listings/{lid}", headers=owner).status_code == 404


def test_listing_detail_and_reviews_page(client):
    detail = client.get("/listings/l9").json()
    assert detail["listing"]["id"] == "l9" and detail["owner"]["id"] == detail["listing"]["ownerId"]
    assert detail["district"]["name"] == detail["listing"]["district"]
    assert all(s["listingId"] == "l9" for s in detail["slots"])
    summary = detail["reviews"]
    assert summary["count"] >= 1 and 1 <= summary["average"] <= 5

    first = client.get("/listings/l9/reviews", params={"limit": 1}).json()
    assert len(first["items"]) == 1
    if summary["count"] > 1:
        second = client.get("/listings/l9/reviews", params={"limit": 1, "cursor": first["nextCursor"]}).json()
        assert second["items"][0]["id"] != first["items"][0]["id"]


def test_my_listings_are_paginated(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    ids = {
        client.post("/listings", json={"listing": _window_listing(title=f"Drill {i}")}, headers=h).json()["listing"][
            "id"
        ]
        for i in range(5)
    }
    seen, cursor = set(), None
    while True:
        page = client.get("/me/listings", params={"limit": 2, "cursor": cursor}, headers=h).json()
        seen |= {v["listing"]["id"] for v in page["items"]}
        cursor = page.get("nextCursor")
        if not cursor:
            break
    assert seen == ids


# --- photos ---------------------------------------------------------------------------------


def test_uploads_are_reencoded_without_metadata(client, issuer, tmp_path):
    _profile(client, issuer)
    raw = _jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif().get(0x8825)  # the original does carry GPS
    r = client.post("/uploads", files={"file": ("p.jpg", raw, "image/jpeg")}, headers=issuer.headers("user-a"))
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["url"].startswith("/media/") and up["url"].endswith(".webp")
    assert max(up["width"], up["height"]) == 2000  # bounded
    stored = client.get(up["url"]).content
    out = Image.open(io.BytesIO(stored))
    assert out.format == "WEBP" and not out.getexif() and "exif" not in out.info

    # The owner can use it; nobody else can put it on their listing.
    listing = _window_listing(photos=[up["url"]])
    assert client.post("/listings", json={"listing": listing}, headers=issuer.headers("user-a")).status_code == 201
    _profile(client, issuer, sub="user-b", name="Bob Builder")
    r = client.post("/listings", json={"listing": listing}, headers=issuer.headers("user-b"))
    assert r.status_code == 422 and "owner uploaded" in r.text


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"<html><script>alert(1)</script></html>",
        b"\xff\xd8\xff\xe0" + b"not really a jpeg" * 10,
    ],
)
def test_non_images_are_refused(client, issuer, payload):
    _profile(client, issuer)
    r = client.post("/uploads", files={"file": ("x.jpg", payload, "image/jpeg")}, headers=issuer.headers("user-a"))
    assert r.status_code == 422


def test_decompression_bombs_are_refused_before_decoding(client, issuer, app):
    _profile(client, issuer)
    app.state.settings.media_max_pixels = 1_000_000
    buf = io.BytesIO()
    Image.new("L", (4000, 4000)).save(buf, format="PNG")  # compresses to almost nothing
    r = client.post(
        "/uploads", files={"file": ("b.png", buf.getvalue(), "image/png")}, headers=issuer.headers("user-a")
    )
    assert r.status_code == 422


def test_uploads_need_a_session(client):
    assert client.post("/uploads", files={"file": ("p.jpg", b"x", "image/jpeg")}).status_code == 401


# --- search, cities, saved ----------------------------------------------------------------------


def test_search_is_paginated_and_scoped(client):
    page = client.get("/search", params={"q": "saw", "limit": 2}).json()
    assert page["items"] and all(
        "saw" in (v["listing"]["title"] + v["listing"]["blurb"]).lower() for v in page["items"]
    )
    berlin = client.get("/search", params={"q": "saw", "metro": "Berlin"}).json()["items"]
    assert berlin and all(v["listing"]["district"] for v in berlin)
    assert client.get("/search", params={"q": "zzzz-no-such-thing"}).json() == {"items": []}
    assert client.get("/search", params={"q": "a"}).status_code == 422  # too short to be useful
    # LIKE wildcards in the query are literals, not patterns.
    assert client.get("/search", params={"q": "%%"}).json() == {"items": []}


def test_cities_are_an_aggregate(client):
    cities = client.get("/cities").json()
    assert cities[0]["city"] == "Berlin" and cities[0]["listings"] > 10
    assert {c["city"] for c in cities} >= {"Berlin", "Paris", "Milan", "Lisbon"}


def test_saved_is_per_person_and_idempotent(client, issuer):
    a, b = issuer.headers("user-a"), issuer.headers("user-b")
    assert client.put("/saved/l9", headers=a).status_code == 204
    assert client.put("/saved/l9", headers=a).status_code == 204
    assert client.put("/saved/l12", headers=a).status_code == 204
    mine = client.get("/saved", headers=a).json()["items"]
    assert [v["listing"]["id"] for v in mine] == ["l12", "l9"] and all(v["saved"] for v in mine)
    assert client.get("/saved", headers=b).json() == {"items": []}
    assert client.put("/saved/nope", headers=a).status_code == 404
    assert client.delete("/saved/l9", headers=a).status_code == 204
    assert [v["listing"]["id"] for v in client.get("/saved", headers=a).json()["items"]] == ["l12"]


# --- internal: candidates -----------------------------------------------------------------------


def test_internal_routes_need_the_service_token(client):
    body = {"origin": "Kreuzberg", "maxKm": 10, "start": now_iso(), "until": _hours_from_now(48)}
    assert client.post("/internal/candidates", json=body).status_code == 403
    assert client.post("/internal/candidates", json=body, headers=INTERNAL).status_code == 200


def test_candidates_are_bounded_and_self_contained(client):
    body = {"origin": "Kreuzberg", "maxKm": 5, "start": now_iso(), "until": _hours_from_now(72), "category": "workshop"}
    w = client.post("/internal/candidates", json=body, headers=INTERNAL).json()
    assert w["listings"], "expected nearby workshop capacity"
    assert all(l["category"] == "workshop" and l["active"] for l in w["listings"])
    owner_ids = {o["id"] for o in w["owners"]}
    assert {l["ownerId"] for l in w["listings"]} <= owner_ids
    assert {s["listingId"] for s in w["slots"]} <= {l["id"] for l in w["listings"]}
    assert "Kreuzberg" in w["districts"] and {l["district"] for l in w["listings"]} <= set(w["districts"])
    # Nothing from another city leaks into a 5 km search from Kreuzberg.
    assert all(w["districts"][l["district"]]["metro"] == "Berlin" for l in w["listings"])

    capped = client.post(
        "/internal/candidates", json={**body, "category": None, "maxKm": 2000, "cap": 3}, headers=INTERNAL
    ).json()
    assert len(capped["listings"]) == 3


def test_candidates_exclude_the_caller_s_own_and_windows_outside_the_range(client):
    far_future = {
        "origin": "Kreuzberg",
        "maxKm": 50,
        "start": _hours_from_now(24 * 400),
        "until": _hours_from_now(24 * 401),
    }
    assert client.post("/internal/candidates", json=far_future, headers=INTERNAL).json()["listings"] == []
    body = {"origin": "Kreuzberg", "maxKm": 50, "start": now_iso(), "until": _hours_from_now(72), "excludeOwner": "o1"}
    w = client.post("/internal/candidates", json=body, headers=INTERNAL).json()
    assert w["listings"] and all(l["ownerId"] != "o1" for l in w["listings"])


# --- the rating loop ------------------------------------------------------------------------------


def test_a_rating_applies_exactly_once_and_becomes_a_review(client, app):
    before = client.get("/owners/o1").json()
    booking_id = new_id("bk")
    event = Event(
        id=new_id("ev"),
        type=BOOKING_RATED,
        source="booking",
        occurred_at=now_iso(),
        data={
            "bookingId": booking_id,
            "ownerId": "o1",
            "listingId": "l9",
            "requesterId": "o17",
            "outcome": {"onTime": True, "quality": 5, "note": "Spot on", "tags": ["Clear handover"]},
            "at": now_iso(),
        },
    )
    handled = [app.state._portal.call(app.state.dispatcher.handle, event) for _ in range(3)]
    assert handled == [True, False, False]  # redeliveries do nothing

    after = client.get("/owners/o1").json()
    assert after["ratingSum"] == before["ratingSum"] + 5 and after["jobsDone"] == before["jobsDone"] + 1
    reviews = client.get("/listings/l9/reviews", params={"limit": 100}).json()["items"]
    mine = [r for r in reviews if r["id"] == f"rv_{booking_id}"]
    assert len(mine) == 1 and mine[0]["text"] == "Spot on" and mine[0]["authorId"] == "o17"
