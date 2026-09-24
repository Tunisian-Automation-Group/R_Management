from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cappy_common.fixtures import build_world
from cappy_common.timeutil import HOUR_MS, iso_from_ms, ms_from_iso, now_iso
from matching.main import build_app
from matching.settings import Settings
from matching.world import StaticWorldProvider


@pytest.fixture(scope="module")
def client():
    app = build_app(
        Settings(event_bus_url="memory://", cors_origins=""),
        world_provider=StaticWorldProvider(build_world()),
    )
    with TestClient(app) as c:
        yield c


NOW = now_iso()
LATER = iso_from_ms(ms_from_iso(NOW) + 7 * 24 * HOUR_MS)
# Two hours of a drill, from Kreuzberg. l8 is a hammer drill in Wedding at €2.50/h.
SAW = {
    "mode": "window",
    "category": "workshop",
    "hours": 2,
    "earliest": NOW,
    "latest": LATER,
    "district": "Kreuzberg",
    "maxDistanceKm": 10,
}


def test_health(client):
    assert client.get("/healthz").json()["ok"] is True


def test_vocabulary(client):
    groups = client.get("/groups").json()
    assert [g["id"] for g in groups] == ["make", "move", "equip"]
    assert all({"label", "blurb"} <= set(g) for g in groups)

    everything = client.get("/categories").json()
    assert len(everything) == 9
    assert {c["id"] for c in everything} == {
        "fabrication",
        "additive",
        "finishing",
        "print",
        "freight",
        "warehousing",
        "workshop",
        "events",
        "creator",
    }
    equip = client.get("/categories", params={"group": "equip"}).json()
    assert [c["id"] for c in equip] == ["workshop", "events", "creator"]
    assert all(c["group"] == "equip" and c["mode"] == "window" for c in equip)
    assert "markets" not in equip[0]
    workshop = next(c for c in equip if c["id"] == "workshop")
    assert workshop["quickHours"] == [2, 4, 8] and "unitNoun" not in workshop
    assert client.get("/categories", params={"group": "everyday"}).status_code == 422

    assert client.get("/review-tags").json() == [
        "As described",
        "Ready on time",
        "Clear handover",
        "Quick replies",
        "Great quality",
        "Fair price",
    ]


def test_matches_are_camel_case_and_sorted(client):
    r = client.post("/matches", json={"requirement": SAW, "now": NOW, "sort": "price"})
    assert r.status_code == 200, r.text
    matches = r.json()
    assert matches
    assert "listingId" in matches[0] and "quote" in matches[0] and "platformFee" in matches[0]["quote"]
    totals = [m["quote"]["total"] for m in matches]
    assert totals == sorted(totals)


def test_offers_and_match_for_offer(client):
    offers = client.get("/listings/l8/offers", params={"hours": 2, "from": NOW, "until": LATER}).json()
    assert offers
    o = offers[0]
    r = client.post(
        "/match-for-offer",
        json={"requirement": SAW, "listingId": "l8", "slotId": o["slotId"], "start": o["start"], "end": o["end"]},
    )
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["listingId"] == "l8" and m["ownerId"] == "o5"
    assert m["quote"]["total"] == 2 * 250
    assert 0 < m["distanceKm"] < 10, "Kreuzberg to Wedding is a few km"
    assert any("of idle time" in reason for reason in m["reasons"])


def test_match_for_offer_rejects_bad_window(client):
    offers = client.get("/listings/l8/offers", params={"hours": 2, "from": NOW, "until": LATER}).json()
    o = offers[0]
    outside = iso_from_ms(ms_from_iso(o["start"]) + 400 * HOUR_MS)
    r = client.post(
        "/match-for-offer",
        json={"requirement": SAW, "listingId": "l8", "slotId": o["slotId"], "start": o["start"], "end": outside},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid"


def test_match_for_offer_unknown_listing(client):
    r = client.post(
        "/match-for-offer",
        json={"requirement": SAW, "listingId": "nope", "slotId": "x", "start": NOW, "end": LATER},
    )
    assert r.status_code == 404


def test_quote_and_feasibility(client):
    r = client.post("/quote", json={"requirement": SAW, "listingId": "l8"}).json()
    assert r["quote"]["total"] == 500 and r["feasibility"]["feasible"] is True
    pa = client.post("/feasibility", json={"requirement": SAW, "listingId": "l12"}).json()
    assert pa["feasible"] is False and "different category" in pa["blockers"]


def test_reviews_summary(client):
    r = client.get("/listings/l8/reviews/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    s = body["summary"]
    assert s["count"] == len(body["reviews"]) > 0
    assert 1 <= s["average"] <= 5 and 0 <= s["onTimeShare"] <= 1
    assert s["topTags"] and all({"tag", "n"} == set(t) for t in s["topTags"])
    ats = [x["at"] for x in body["reviews"]]
    assert ats == sorted(ats, reverse=True)
    assert client.get("/listings/nope/reviews/summary").status_code == 404


def test_browse(client):
    spot = client.get("/browse/spotlight", params={"district": "Kreuzberg", "maxKm": 5, "now": NOW}).json()
    assert isinstance(spot, list)
    idle = client.get("/browse/idle", params={"district": "Kreuzberg", "maxKm": 5, "now": NOW}).json()
    assert idle["hours"] > 0 and isinstance(idle["value"], int)
    cities = client.get("/browse/cities", params={"now": NOW}).json()
    assert len(cities) >= 5 and cities[0]["idle"]["hours"] >= cities[-1]["idle"]["hours"]
    europe = client.get("/browse/europe", params={"now": NOW}).json()
    assert abs(europe["hours"] - sum(c["idle"]["hours"] for c in cities)) < 1e-6


def test_nearest_district(client):
    r = client.get("/districts/nearest", params={"lat": 48.8566, "lng": 2.3522}).json()
    assert r["district"]["metro"] == "Paris"
