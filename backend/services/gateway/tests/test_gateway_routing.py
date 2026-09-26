from __future__ import annotations

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from cappy_common.flags import bucket
from gateway.main import build_app
from gateway.routing import BOOKING, CATALOG, MATCHING, NOTIFICATIONS, PAYMENTS, resolve
from gateway.settings import Settings


@pytest.mark.parametrize(
    ("path", "upstream"),
    [
        ("/me", CATALOG),
        ("/me/listings", CATALOG),
        ("/me/blocks", BOOKING),
        ("/me/blocks/someone", BOOKING),
        ("/bookings/bk_1/messages", BOOKING),
        ("/districts", CATALOG),
        ("/cities", CATALOG),
        ("/owners/o1", CATALOG),
        ("/listings", CATALOG),
        ("/listings/l9", CATALOG),
        ("/listings/l9/slots", CATALOG),
        ("/listings/l9/reviews", CATALOG),
        ("/search", CATALOG),
        ("/saved/l9", CATALOG),
        ("/uploads", CATALOG),
        ("/listings/l9/offers", MATCHING),
        ("/matches", MATCHING),
        ("/quote", MATCHING),
        ("/categories", MATCHING),
        ("/browse/spotlight", MATCHING),
        ("/bookings", BOOKING),
        ("/bookings/bk_1/accept", BOOKING),
        ("/payments/config", PAYMENTS),
        ("/payments/webhooks/stripe", PAYMENTS),
        ("/notifications/devices", NOTIFICATIONS),
        ("/notifications/devices/tok-1", NOTIFICATIONS),
        ("/notifications", NOTIFICATIONS),
        ("/notifications/read", NOTIFICATIONS),
        ("/notifications/settings", NOTIFICATIONS),
        ("/me/sign-out-everywhere", CATALOG),
        ("/notifications/anything-else", None),
        # Never reachable from outside, however the path is dressed up.
        ("/internal/candidates", None),
        ("/listings/internal/candidates", None),
        ("/bookings/../internal/busy", None),
        ("/match-for-offer", None),
        ("/admin/reset", None),
        ("/admin/reports", CATALOG),
        ("/admin/reports/rp_1/decide", CATALOG),
        ("/admin/owners/o1/suspend", CATALOG),
        ("/admin/bookings/bk_1/resolve", BOOKING),
        ("/admin/bookings", None),
        ("/reports", CATALOG),
        ("/world", None),
        ("/nothing-here", None),
    ],
)
def test_resolve(path, upstream):
    assert resolve(path) == upstream


def _upstreams(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.host, request.method, request.url.path, dict(request.headers)))
        if request.url.host == "matching":
            raise httpx.ConnectError("down")
        if request.url.path.startswith("/media/"):
            return httpx.Response(200, content=b"WEBP", headers={"content-type": "image/webp", "x-secret": "no"})
        return httpx.Response(201, json={"ok": True}, headers={"set-cookie": "leak=1"})

    return httpx.MockTransport(handler)


def _settings(**over) -> Settings:
    return Settings(
        app_env="test",
        catalog_url="http://catalog",
        matching_url="http://matching",
        booking_url="http://booking",
        payments_url="http://payments",
        **over,
    )


@pytest.fixture()
def gateway():
    calls: list = []
    with TestClient(build_app(_settings(), transport=_upstreams(calls))) as c:
        yield c, calls


def test_forwards_the_token_and_request_id_and_nothing_else(gateway):
    c, calls = gateway
    r = c.post(
        "/api/bookings",
        json={"listingId": "l9"},
        headers={"Authorization": "Bearer t", "Idempotency-Key": "k1", "X-Cappy-User": "o1", "Cookie": "a=b"},
    )
    assert r.status_code == 201 and "set-cookie" not in r.headers
    host, method, path, headers = calls[-1]
    assert (host, method, path) == ("booking", "POST", "/bookings")
    assert headers["authorization"] == "Bearer t" and headers["idempotency-key"] == "k1"
    assert headers["x-request-id"] == r.headers["x-request-id"]
    assert "x-cappy-user" not in headers and "cookie" not in headers


def test_a_webhook_signature_reaches_only_its_own_route(gateway):
    c, calls = gateway
    sig = {"Stripe-Signature": "t=1,v1=abc"}
    c.post("/api/payments/webhooks/stripe", content=b"{}", headers=sig)
    assert calls[-1][2] == "/payments/webhooks/stripe" and calls[-1][3]["stripe-signature"] == "t=1,v1=abc"
    c.post("/api/payments/connect/onboarding", json={}, headers=sig)
    assert "stripe-signature" not in calls[-1][3], "nowhere else"


def test_the_apps_language_reaches_the_bell(gateway):
    # V3-13: the bell renders in the language the app sends.
    c, calls = gateway
    c.get("/api/notifications", headers={"Authorization": "Bearer t", "Accept-Language": "de"})
    host, _, path, headers = calls[-1]
    assert path == "/notifications" and headers["accept-language"] == "de"


def test_unknown_paths_never_reach_a_service(gateway):
    c, calls = gateway
    for path in ("/api/internal/busy", "/api/whatever", "/api/admin/reset"):
        r = c.post(path, json={})
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert calls == []


def test_an_unreachable_service_is_a_clean_502(gateway):
    c, _ = gateway
    r = c.post("/api/matches", json={})
    assert r.status_code == 502 and "down" not in r.text


def test_photos_pass_through_without_internal_headers(gateway):
    c, _ = gateway
    r = c.get("/media/abc.webp")
    assert r.headers["content-type"] == "image/webp" and "x-secret" not in r.headers


def test_body_limit(gateway):
    c, calls = gateway
    assert (
        c.post("/api/bookings", content=b"x" * 300_000, headers={"content-type": "application/json"}).status_code == 413
    )
    assert calls == []


def test_serves_the_web_app_from_the_same_origin(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Cappy</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "sw.js").write_text("// service worker", encoding="utf-8")
    with TestClient(build_app(_settings(static_dir=str(tmp_path)), transport=_upstreams([]))) as c:
        home = c.get("/")
        assert "Cappy" in home.text and home.headers["cache-control"] == "no-store"
        assert "immutable" in c.get("/assets/index-abc123.js").headers["cache-control"]
        assert c.get("/sw.js").headers["cache-control"] == "no-store"
        assert "Cappy" in c.get("/listing/l9").text, "client-side routes fall back to the app"
        assert "Cappy" in c.get("/../../etc/passwd").text
        assert c.get("/api/whatever").status_code == 404


def test_the_native_apps_may_call_the_api_cross_origin():
    settings = _settings(cors_origins="capacitor://localhost,https://localhost")
    with TestClient(build_app(settings, transport=_upstreams([]))) as c:
        pre = {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,idempotency-key",
        }
        ok = c.options("/api/bookings", headers={"Origin": "capacitor://localhost", **pre})
        assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "capacitor://localhost"
        evil = c.options("/api/bookings", headers={"Origin": "https://evil.example", **pre})
        assert "access-control-allow-origin" not in evil.headers
        versioned = {**pre, "Access-Control-Request-Headers": "authorization,x-app-version"}
        assert c.options("/api/bookings", headers={"Origin": "capacitor://localhost", **versioned}).status_code == 200
        shed = c.post("/api/matches", json={}, headers={"Origin": "capacitor://localhost"})
        exposed = {h.strip() for h in shed.headers["access-control-expose-headers"].lower().split(",")}
        assert {"x-request-id", "retry-after"} <= exposed and shed.headers["x-request-id"]


def test_app_config_for_the_store_apps(gateway):
    c, calls = gateway
    r = c.get("/api/app-config")
    body = r.json()
    markets = body.pop("markets")
    assert body == {"minVersion": "1.0.0", "latestVersion": "1.0.0", "flags": {}, "rollouts": {}}
    assert markets["DE"]["status"] == "live" and markets["US"]["units"] == "imperial"
    assert "legalEntity" not in markets["US"] and "taxRegime" not in markets["US"], "public part only"
    assert "max-age" in r.headers["cache-control"]
    assert calls == []


def test_feature_flags_are_on_off_or_a_rollout_the_app_evaluates():
    settings = _settings(feature_flags="chat:100,dark:0,newcheckout:25")
    with TestClient(build_app(settings, transport=_upstreams([]))) as c:
        body = c.get("/api/app-config").json()
    assert body["flags"] == {"chat": True, "dark": False, "newcheckout": False}
    assert body["rollouts"] == {"newcheckout": 25}
    # The vector the app's own implementation is checked against.
    assert bucket("newcheckout", "user-1") == 16


def test_the_apps_report_their_crashes_without_an_account(gateway, caplog):
    c, calls = gateway
    report = {"message": "TypeError: x is undefined", "stack": "at Listing.tsx:12", "route": "/listing/l9"}
    r = c.post("/api/client-errors", json={**report, "appVersion": "1.0.0", "platform": "ios"})
    assert r.status_code == 202 and calls == []
    logged = [rec for rec in caplog.records if rec.getMessage().startswith("client error")]
    assert logged and logged[-1].client["route"] == "/listing/l9"
    assert c.post("/api/client-errors", content=b"x" * 9000).status_code == 413
    assert c.post("/api/client-errors", json={"platform": "windows", "message": "?"}).status_code == 422


def test_a_crash_loop_cannot_flood_the_logs(caplog):
    with TestClient(build_app(_settings(client_errors_per_minute=3), transport=_upstreams([]))) as c:
        logging.getLogger().addHandler(caplog.handler)  # starting the app configured logging afresh
        for _ in range(10):
            assert c.post("/api/client-errors", json={"message": "boom"}).status_code == 202
    assert sum(r.getMessage().startswith("client error") for r in caplog.records) == 3


def test_error_reports_are_scrubbed_and_limited_per_real_client(caplog):
    settings = _settings(client_errors_per_minute=1, trusted_proxy_hops=2)
    with TestClient(build_app(settings, transport=_upstreams([]))) as c:
        logging.getLogger().addHandler(caplog.handler)
        msg = {"message": "failed for ana@example.com, call +49 30 1234567", "stack": "tel 0151-2345678"}
        # A forged left-most hop changes nothing: the proxies' hops decide.
        for forged in ("1.1.1.1", "2.2.2.2"):
            xff = {"X-Forwarded-For": f"{forged}, 203.0.113.9, 10.0.0.2"}
            assert c.post("/api/client-errors", json=msg, headers=xff).status_code == 202
    logged = [r for r in caplog.records if r.getMessage().startswith("client error")]
    assert len(logged) == 1, "the second report came from the same real client"
    assert "example.com" not in str(logged[0].client) and "1234567" not in str(logged[0].client)
    assert "[email]" in logged[0].client["message"] and logged[0].client["stack"] == "tel [number]"


def test_an_unreachable_service_says_when_to_retry(gateway):
    c, _ = gateway
    assert c.post("/api/matches", json={}).headers["retry-after"] == "2"


def test_overload_sheds_browsing_first_and_keeps_room_for_writes():
    from gateway.main import Admission, Shed

    a = Admission(limit=10, browse_share=0.8)
    for _ in range(8):
        a.enter(write=False)
    with pytest.raises(Shed):
        a.enter(write=False)  # browsing is capped at 80%
    a.enter(write=True)
    a.enter(write=True)  # writes may use the rest
    with pytest.raises(Shed):
        a.enter(write=True)
    a.leave()
    a.enter(write=True)


def test_a_shed_request_is_a_fast_503(gateway):
    c, calls = gateway
    c.app.state.admission.in_flight = c.app.state.admission.limit
    r = c.get("/api/listings/l9")
    assert r.status_code == 503 and r.headers["retry-after"] == "2" and r.json()["error"]["code"] == "overloaded"
    assert calls == [], "never reached a service"
    c.app.state.admission.in_flight = 0


def test_a_full_bulkhead_sheds_only_that_service(gateway):
    import asyncio

    c, _ = gateway
    sem: asyncio.Semaphore = c.app.state.bulkheads["matching"]
    sem._value = 0  # every slot to matching taken
    assert c.post("/api/matches", json={}).status_code == 503
    assert c.get("/api/listings/l9").status_code == 201, "catalog is unaffected"
    sem._value = 200
