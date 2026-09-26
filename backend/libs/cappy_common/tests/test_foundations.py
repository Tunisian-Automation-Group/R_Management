"""The shared foundations every service stands on."""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import Column, String, Table, insert, select

from cappy_common.app import ApiRouter, create_app
from cappy_common.auth import Principal, TokenVerifier, require_admin, require_internal, require_principal
from cappy_common.db import Database, new_metadata
from cappy_common.errors import Unauthorized
from cappy_common.events import (
    BOOKING_RATED,
    BOOKING_STATUS_CHANGED,
    Dispatcher,
    MemoryBroker,
    Outbox,
    OutboxRelay,
    event_tables,
)
from cappy_common.ids import ULID_RE, new_id
from cappy_common.pagination import clamp_limit, decode_cursor, encode_cursor
from cappy_common.settings import CommonSettings, UnsafeSettings
from cappy_common.testing import TestIssuer

# --- settings -------------------------------------------------------------------

SAFE_PROD = dict(
    app_env="prod",
    internal_token="cappy:" + "x" * 40,
    internal_callers="booking=" + "0" * 64,
    event_bus_url="sns://arn:aws:sns:eu-central-1:123:cappy-events",
    auth_issuer="https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_abc",
    auth_client_ids="client-1",
)


@pytest.mark.parametrize(
    "override, reason",
    [({"internal_token": "x" * 46}, "own token"), ({"internal_callers": ""}, "INTERNAL_CALLERS")],
)
def test_prod_needs_per_caller_internal_tokens(override, reason):
    with pytest.raises(UnsafeSettings, match=reason):
        CommonSettings(**{**SAFE_PROD, **override})


def test_prod_boots_with_safe_settings():
    assert CommonSettings(**SAFE_PROD).deployed


@pytest.mark.parametrize(
    "override, reason",
    [
        ({"internal_token": "short"}, "INTERNAL_TOKEN"),
        ({"event_bus_url": "memory://"}, "EVENT_BUS_URL"),
        ({"aws_endpoint_url": "http://localstack:4566"}, "emulator"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"auth_issuer": "http://cognito:9229/local"}, "AUTH_ISSUER"),
        ({"auth_client_ids": ""}, "AUTH_CLIENT_IDS"),
    ],
)
def test_prod_refuses_unsafe_settings(override, reason):
    with pytest.raises(UnsafeSettings, match=reason):
        CommonSettings(**{**SAFE_PROD, **override})


def test_local_is_forgiving():
    s = CommonSettings(app_env="local")
    assert not s.deployed and s.unsafe_reasons()  # unsafe, but allowed locally


# --- tokens ---------------------------------------------------------------------


@pytest.fixture()
def issuer():
    return TestIssuer()


async def test_verifies_a_good_token(issuer):
    p = await issuer.verifier().verify(issuer.token("user-1"))
    assert p == Principal(sub="user-1", username="user-1", client_id=issuer.client_id)


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},  # expired
        {"iss": "https://evil.example/pool"},  # someone else's pool
        {"client_id": "another-app"},  # another app client
        {"token_use": "id"},  # an id token is not an access token
    ],
)
async def test_rejects_bad_claims(issuer, claims):
    with pytest.raises(Unauthorized):
        await issuer.verifier().verify(issuer.token("user-1", **claims))


async def test_rejects_a_token_signed_by_another_key(issuer):
    forger = TestIssuer(issuer=issuer.issuer, client_id=issuer.client_id, kid=issuer.kid)
    with pytest.raises(Unauthorized):
        await issuer.verifier().verify(forger.token("user-1"))


async def test_rejects_alg_none(issuer):
    unsigned = jwt.encode(
        {"sub": "u", "iss": issuer.issuer, "exp": int(time.time()) + 60, "iat": int(time.time())},
        key=None,
        algorithm="none",
    )
    with pytest.raises(Unauthorized):
        await issuer.verifier().verify(unsigned)


async def test_unknown_key_refresh_is_rate_limited(issuer):
    import httpx

    fetches = {"n": 0}

    def jwks_endpoint(request: httpx.Request) -> httpx.Response:
        fetches["n"] += 1
        return httpx.Response(200, json=issuer.jwks)

    v = TokenVerifier(
        issuer=issuer.issuer,
        jwks_url="https://idp.test/jwks.json",
        client_ids=[],
        http=httpx.AsyncClient(transport=httpx.MockTransport(jwks_endpoint)),
    )
    # The real key is fetched once and then served from cache.
    await v.verify(issuer.token("u"))
    await v.verify(issuer.token("u"))
    assert fetches["n"] == 1
    # Tokens naming a key we do not have cannot hammer the identity provider:
    # within the refresh window they are refused without another fetch.
    stranger = TestIssuer(issuer=issuer.issuer, kid="rotated")
    for _ in range(5):
        with pytest.raises(Unauthorized):
            await v.verify(stranger.token("u"))
    assert fetches["n"] == 1


# --- ids and cursors ----------------------------------------------------------------


def test_ids_are_sortable_and_unique():
    ids = [new_id("bk") for _ in range(2000)]
    assert len(set(ids)) == len(ids)
    assert all(ULID_RE.match(i.split("_", 1)[1]) for i in ids)
    early, late = new_id("bk"), (time.sleep(0.002), new_id("bk"))[1]
    assert early < late


def test_cursor_round_trip_and_tamper():
    c = encode_cursor({"at": "2026-09-25T10:00:00.000Z", "id": "bk_1"})
    assert decode_cursor(c) == {"at": "2026-09-25T10:00:00.000Z", "id": "bk_1"}
    assert decode_cursor(None) is None
    with pytest.raises(Exception, match="cursor"):
        decode_cursor("!!!not-base64")
    for tampered in ({"x": 1}, {"at": "nope", "id": "bk_1"}, {"at": "2026-09-25T10:00:00Z", "id": 7}, [1]):
        with pytest.raises(Exception, match="cursor"):
            decode_cursor(encode_cursor(tampered))
    assert clamp_limit(None) == 20 and clamp_limit(10_000) == 100 and clamp_limit(0) == 1


# --- the app shell ----------------------------------------------------------------


def _app(issuer: TestIssuer, **settings):
    s = CommonSettings(app_env="test", internal_token="t" * 40, max_body_bytes=100, **settings)
    app = create_app(s, title="t", body_limits={"/upload": 10_000})
    app.state.verifier = issuer.verifier()
    router = ApiRouter()

    @router.get("/me")
    async def me(p: Principal = Depends(require_principal)) -> dict:
        return {"sub": p.sub}

    @router.post("/echo")
    async def echo(body: dict) -> dict:
        return body

    @router.post("/upload")
    async def upload(body: dict) -> dict:
        return {"n": len(str(body))}

    @router.get("/admin/thing", dependencies=[Depends(require_admin)])
    async def admin() -> dict:
        return {"ok": True}

    @router.get("/internal/thing", dependencies=[Depends(require_internal)])
    async def internal() -> dict:
        return {"ok": True}

    @router.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("secret internals")

    app.include_router(router)
    return app


def test_identity_comes_only_from_a_verified_token(issuer):
    with TestClient(_app(issuer)) as c:
        assert c.get("/me").status_code == 401
        assert c.get("/me", headers={"X-Cappy-User": "o1"}).status_code == 401
        assert c.get("/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
        assert c.get("/me", headers=issuer.headers("user-9")).json() == {"sub": "user-9"}


class _Mfa:
    def __init__(self, on: set[str]) -> None:
        self.on, self.asked = on, 0

    async def enabled(self, username: str) -> bool:
        self.asked += 1
        return username in self.on


def test_staff_powers_need_mfa_where_required(issuer):
    staff = {"cognito:groups": ["admin"]}
    app = _app(issuer, admin_mfa_required=True)
    app.state.staff_mfa = _Mfa(on={"mod-with-mfa"})
    with TestClient(app) as c:
        assert c.get("/admin/thing", headers=issuer.headers("user-1")).status_code == 403  # not staff
        r = c.get("/admin/thing", headers=issuer.headers("mod-no-mfa", **staff))
        assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"
        assert c.get("/admin/thing", headers=issuer.headers("mod-with-mfa", **staff)).json() == {"ok": True}
    # Locally (cognito-local has no MFA) staff need only the group.
    with TestClient(_app(issuer)) as c:
        assert c.get("/admin/thing", headers=issuer.headers("mod-no-mfa", **staff)).status_code == 200


def test_deployed_services_refuse_to_run_staff_without_mfa():
    with pytest.raises(UnsafeSettings, match="ADMIN_MFA_REQUIRED"):
        CommonSettings(**{**SAFE_PROD, "admin_mfa_required": False})
    assert CommonSettings(**SAFE_PROD).staff_mfa_required


def test_internal_routes_need_the_service_token(issuer):
    with TestClient(_app(issuer)) as c:
        assert c.get("/internal/thing").status_code == 403
        assert c.get("/internal/thing", headers={"X-Internal-Token": "wrong"}).status_code == 403
        assert c.get("/internal/thing", headers={"X-Internal-Token": "t" * 40}).json() == {"ok": True}


def test_internal_routes_take_only_listed_callers(issuer):
    import hashlib

    booking, matching = "booking:" + "b" * 40, "matching:" + "m" * 40
    listed = f"booking={hashlib.sha256(booking.encode()).hexdigest()}"
    with TestClient(_app(issuer, internal_callers=listed)) as c:
        assert c.get("/internal/thing", headers={"X-Internal-Token": booking}).json() == {"ok": True}
        # A real token of a service that may not call this one, the old shared
        # token, and a listed name with the wrong secret: all refused.
        for token in (matching, "t" * 40, "booking:" + "x" * 40, ""):
            assert c.get("/internal/thing", headers={"X-Internal-Token": token}).status_code == 403


def test_body_limits(issuer):
    with TestClient(_app(issuer)) as c:
        assert c.post("/echo", json={"a": "x" * 500}).status_code == 413
        assert c.post("/echo", json={"a": "x"}).status_code == 200
        assert c.post("/upload", json={"a": "x" * 500}).status_code == 200  # route override


def test_errors_never_leak_internals_and_carry_a_request_id(issuer):
    with TestClient(_app(issuer), raise_server_exceptions=False) as c:
        r = c.get("/boom", headers={"X-Request-Id": "req-12345678"})
        assert r.status_code == 500
        assert "secret" not in r.text and "req-12345678" in r.text
        assert r.headers["x-request-id"] == "req-12345678"
        assert r.headers["x-content-type-options"] == "nosniff"


def test_readiness_reports_failing_dependencies(issuer):
    app = _app(issuer)

    async def database():
        raise ConnectionError("down")

    with TestClient(app) as c:
        assert c.get("/readyz").status_code == 200
        app.state.readiness.append(database)
        r = c.get("/readyz")
        assert r.status_code == 503 and r.json()["failing"] == ["database: ConnectionError"]


def test_docs_are_hidden_when_deployed():
    app = create_app(CommonSettings(**SAFE_PROD), title="t")
    with TestClient(app) as c:
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


# --- outbox and consumers ----------------------------------------------------------


@pytest.fixture()
async def stores():
    meta = new_metadata()
    things = Table("things", meta, Column("id", String(40), primary_key=True))
    outbox, processed = event_tables(meta)
    db = Database("sqlite+aiosqlite://")
    await db.create_all(meta)
    yield db, things, outbox, processed
    await db.dispose()


async def test_outbox_publishes_only_committed_events(stores):
    db, things, outbox_t, _ = stores
    outbox, broker = Outbox(outbox_t, "test"), MemoryBroker()
    relay = OutboxRelay(db, outbox_t, broker)

    async with db.transaction() as s:
        await s.execute(insert(things).values(id="kept"))
        await outbox.add(s, BOOKING_STATUS_CHANGED, {"id": "kept"})

    with pytest.raises(RuntimeError):
        async with db.transaction() as s:
            await s.execute(insert(things).values(id="rolled-back"))
            await outbox.add(s, BOOKING_STATUS_CHANGED, {"id": "rolled-back"})
            raise RuntimeError("the change failed")

    assert await relay.flush() == 1
    assert [e.data for e in broker.published] == [{"id": "kept"}]
    assert await relay.flush() == 0  # sent rows are not resent


async def test_relay_keeps_events_when_publishing_fails(stores):
    db, _, outbox_t, _ = stores

    class Down(MemoryBroker):
        async def publish(self, events):
            raise ConnectionError("sns unreachable")

    async with db.transaction() as s:
        await Outbox(outbox_t, "test").add(s, BOOKING_RATED, {"n": 1})
    with pytest.raises(ConnectionError):
        await OutboxRelay(db, outbox_t, Down()).flush()
    healthy = MemoryBroker()
    assert await OutboxRelay(db, outbox_t, healthy).flush() == 1
    assert healthy.published[0].data == {"n": 1}


async def test_a_row_that_keeps_failing_stops_blocking_the_rest(stores):
    from sqlalchemy import update

    from cappy_common.events import MAX_ATTEMPTS

    db, _, outbox_t, _ = stores
    out = Outbox(outbox_t, "test")
    async with db.transaction() as s:
        poison = await out.add(s, BOOKING_RATED, {"n": "poison"})
    async with db.transaction() as s:
        await s.execute(update(outbox_t).where(outbox_t.c.id == poison.id).values(attempts=MAX_ATTEMPTS))
        await out.add(s, BOOKING_RATED, {"n": "next"})
    broker = MemoryBroker()
    assert await OutboxRelay(db, outbox_t, broker).flush() == 1
    assert [e.data["n"] for e in broker.published] == ["next"]


async def test_consumer_is_idempotent_and_never_acks_failures(stores):
    db, things, outbox_t, processed = stores
    seen = []

    async def on_rated(session, event):
        seen.append(event.id)
        await session.execute(insert(things).values(id=event.data["id"]))
        if event.data.get("fail"):
            raise ValueError("handler failed")

    dispatcher = Dispatcher(db, processed, {BOOKING_RATED: on_rated})
    async with db.transaction() as s:
        good = await Outbox(outbox_t, "test").add(s, BOOKING_RATED, {"id": "a"})
        bad = await Outbox(outbox_t, "test").add(s, BOOKING_RATED, {"id": "b", "fail": True})

    assert await dispatcher.handle(good) is True
    assert await dispatcher.handle(good) is False  # redelivery: nothing happens twice
    with pytest.raises(ValueError):
        await dispatcher.handle(bad)
    async with db.session() as s:
        ids = set((await s.execute(select(things.c.id))).scalars())
        done = set((await s.execute(select(processed.c.event_id))).scalars())
    # The failed handler's write and its processed marker both rolled back, so a
    # redelivery will try again rather than being skipped.
    assert ids == {"a"} and done == {good.id}
    assert seen == [good.id, bad.id]


async def test_prune_keeps_what_may_still_be_needed():
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, insert, select

    from cappy_common.db import Database, new_metadata
    from cappy_common.events import event_tables, prune

    md = new_metadata()
    outbox, processed = event_tables(md)
    db = Database("sqlite+aiosqlite://")
    await db.create_all(md)
    now = datetime.now(UTC)
    async with db.transaction() as s:
        for i, (sent, age) in enumerate([(True, 8), (True, 1), (False, 30)]):
            at = now - timedelta(days=age)
            await s.execute(
                insert(outbox).values(
                    id=f"o{i}", type="t", body={}, created_at=at, sent_at=at if sent else None, attempts=0
                )
            )
        for i, age in enumerate([22, 20]):
            await s.execute(
                insert(processed).values(event_id=f"p{i}", type="t", processed_at=now - timedelta(days=age))
            )
    assert await prune(db, outbox, processed, batch=1) == 2
    async with db.session() as s:
        assert sorted((await s.execute(select(outbox.c.id))).scalars()) == ["o1", "o2"], "unsent is never pruned"
        assert (await s.execute(select(func.count()).select_from(processed))).scalar() == 1
    await db.dispose()


def test_failed_messages_back_off_to_hours_not_minutes():
    from cappy_common.events import retry_delay

    first, later = retry_delay(1), [retry_delay(n) for n in range(1, 13)]
    assert 15 <= first <= 30
    assert max(later) <= 900
    assert sum(later) > 3600, "twelve tries span over an hour, even jittered low"


async def test_a_task_started_during_an_identity_outage_uses_the_deploy_time_keys():
    import httpx

    from cappy_common.auth import TokenVerifier
    from cappy_common.testing import TEST_CLIENT, TEST_ISSUER, TestIssuer

    issuer = TestIssuer()

    def down(request):
        raise httpx.ConnectError("cognito unreachable")

    v = TokenVerifier(
        issuer=TEST_ISSUER,
        jwks_url="https://cognito.example/jwks.json",
        client_ids=[TEST_CLIENT],
        fallback_jwks=issuer.jwks,
        http=httpx.AsyncClient(transport=httpx.MockTransport(down)),
    )
    assert (await v.verify(issuer.token("someone"))).sub == "someone"


async def test_an_event_carries_the_trace_of_the_request_that_caused_it(stores):
    from opentelemetry.sdk.trace import TracerProvider

    from cappy_common.events import Event

    db, _, outbox_t, _ = stores
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("POST /bookings") as span:
        async with db.transaction() as s:
            event = await Outbox(outbox_t, "test").add(s, BOOKING_RATED, {"n": 1})
    trace_id = format(span.get_span_context().trace_id, "032x")
    assert event.trace and trace_id in event.trace["traceparent"]
    assert Event.from_json(event.to_json()).trace == event.trace

    async with db.transaction() as s:
        untraced = await Outbox(outbox_t, "test").add(s, BOOKING_RATED, {"n": 2})
    assert untraced.trace is None and "trace" not in untraced.to_json()


def test_staff_is_whatever_claim_the_settings_name():
    """F-3: Cognito groups today; another provider's claim is two settings."""
    from cappy_common.auth import Principal, is_staff
    from cappy_common.settings import CommonSettings

    cognito = Principal(sub="s", claims={"cognito:groups": ["admin"]})
    assert is_staff(cognito, CommonSettings()) and not is_staff(Principal(sub="s", claims={}), CommonSettings())
    other = CommonSettings(staff_claim="scope", staff_value="cappy:staff")
    assert is_staff(Principal(sub="s", claims={"scope": "openid cappy:staff"}), other)
    assert not is_staff(cognito, other)
