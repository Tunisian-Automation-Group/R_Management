from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from notifications.mail import Directory, LogMailer
from notifications.main import build_app
from notifications.settings import Settings

from cappy_common.events import BOOKING_STATUS_CHANGED, PAYOUT_SENT, Event
from cappy_common.ids import new_id
from cappy_common.timeutil import now_iso


class People(Directory):
    book = {"buyer": "buyer@example.com", "host": "host@example.com"}

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def email_of(self, sub: str) -> str | None:
        return self.book.get(sub)

    async def delete_person(self, sub: str) -> None:
        self.deleted.append(sub)


@pytest.fixture()
def app():
    mailer = LogMailer()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    return build_app(settings, directory=People(), mailer=mailer)


def _event(type_, **data) -> Event:
    return Event(id=new_id("ev"), type=type_, source="booking", occurred_at=now_iso(), data=data)


def _change(to, by="buyer", frm=None, **extra):
    data = {"bookingId": "bk_1", "requesterId": "buyer", "ownerId": "host", "title": "Table saw"}
    return _event(BOOKING_STATUS_CHANGED, **{**data, "to": to, "by": by, "from": frm, **extra})


def _sent(app, *events):
    with TestClient(app) as c:
        for e in events:
            c.portal.call(app.state.dispatcher.handle, e)
    return [(m.to, m.subject) for m in app.state.mailer.sent]


def test_each_party_hears_what_concerns_them(app):
    sent = _sent(
        app,
        _change("awaiting_payment"),
        _change("requested", by="payments", frm="awaiting_payment"),
        _change("accepted", by="host", frm="requested"),
        _change("completed", by="system", frm="active"),
        _event(PAYOUT_SENT, bookingId="bk_1", ownerId="host", requesterId="buyer", amount=4000, currency="eur"),
    )
    assert sent == [
        ("host@example.com", "New request: Table saw"),
        ("buyer@example.com", "Confirmed: Table saw"),
        ("buyer@example.com", "How was Table saw?"),
        ("host@example.com", "You have been paid €40.00"),
    ]


def test_a_cancellation_goes_to_the_other_side(app):
    assert _sent(app, _change("cancelled", by="host")) == [("buyer@example.com", "Cancelled: Table saw")]


def test_an_unpaid_request_lapsing_is_silent(app):
    assert _sent(app, _change("expired", by="system", frm="awaiting_payment")) == []


def test_each_email_is_sent_once(app):
    e = _change("accepted", by="host")
    assert len(_sent(app, e, e)) == 1


def test_nobody_to_tell(app):
    e = _change("accepted", by="host", requesterId="deleted-user")
    assert _sent(app, e) == []


def test_devices_get_pushes_and_gone_ones_are_forgotten():
    from notifications.push import LogPusher

    from cappy_common.events import PROFILE_DELETED
    from cappy_common.testing import TestIssuer

    issuer, pusher, mailer = TestIssuer(), LogPusher(), LogMailer()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=People(), mailer=mailer, pusher=pusher, verifier=issuer.verifier())
    with TestClient(app) as c:
        assert c.post("/notifications/devices", json={"platform": "ios", "token": "tok-alive-1"}).status_code == 401
        for token in ("tok-alive-1", "tok-was-gone"):
            r = c.post(
                "/notifications/devices", json={"platform": "ios", "token": token}, headers=issuer.headers("host")
            )
            assert r.status_code == 204

        # The second endpoint reports itself gone on the first push.
        async def mark_gone():
            from notifications.tables import DeviceRow
            from sqlalchemy import update

            async with app.state.db.transaction() as s:
                await s.execute(update(DeviceRow).where(DeviceRow.token == "tok-was-gone").values(endpoint="x:gone"))

        c.portal.call(mark_gone)
        c.portal.call(app.state.dispatcher.handle, _change("requested", by="payments"))
        assert [t for _, t in pusher.sent] == ["New request: Table saw", "New request: Table saw"]
        assert [m.subject for m in mailer.sent] == ["New request: Table saw"], "email still goes"
        c.portal.call(app.state.dispatcher.handle, _change("accepted", by="host"))  # to the buyer, who has no devices
        pusher.sent.clear()
        c.portal.call(app.state.dispatcher.handle, _change("requested", by="payments"))
        assert len(pusher.sent) == 1, "the gone device was forgotten"
        # Deleting the account removes the rest.
        c.portal.call(app.state.dispatcher.handle, _event(PROFILE_DELETED, ownerId="host"))
        pusher.sent.clear()
        c.portal.call(app.state.dispatcher.handle, _change("requested", by="payments"))
        assert pusher.sent == []


def test_a_chat_message_is_pushed_and_emailed_at_most_every_15_minutes():
    from notifications.push import LogPusher

    from cappy_common.events import BOOKING_MESSAGE
    from cappy_common.testing import TestIssuer

    issuer, pusher, mailer = TestIssuer(), LogPusher(), LogMailer()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=People(), mailer=mailer, pusher=pusher, verifier=issuer.verifier())
    with TestClient(app) as c:
        c.post(
            "/notifications/devices",
            json={"platform": "android", "token": "tok-host-9"},
            headers=issuer.headers("host"),
        )
        for _ in range(3):
            ev = _event(BOOKING_MESSAGE, bookingId="bk_1", senderId="buyer", recipientId="host", title="Table saw")
            c.portal.call(app.state.dispatcher.handle, ev)
        other = _event(BOOKING_MESSAGE, bookingId="bk_2", senderId="buyer", recipientId="host", title="Van")
        c.portal.call(app.state.dispatcher.handle, other)
    assert [t for _, t in pusher.sent] == ["New message: Table saw"] * 3 + ["New message: Van"]
    # FL-3: one email per conversation per 15 minutes; another conversation is another email.
    assert [m.subject for m in mailer.sent] == ["New message: Table saw", "New message: Van"]


def test_reports_are_acknowledged_and_decisions_explained(app):
    from cappy_common.events import MODERATION_DECISION, REPORT_RECEIVED

    sent = _sent(
        app,
        _event(REPORT_RECEIVED, reportId="rp_1", reporterId=None, reporterEmail="n@example.com", targetType="listing"),
        _event(
            MODERATION_DECISION,
            reportId="rp_1",
            action="take_down",
            targetType="listing",
            targetId="l9",
            affectedId="host",
            reporterId=None,
            reporterEmail="n@example.com",
            statement="Stolen photos (terms 4).",
        ),
    )
    assert sent == [
        ("n@example.com", "We received your report"),
        ("host@example.com", "We removed your listing"),
        ("n@example.com", "Your report: our decision"),
    ]


def test_a_german_speaker_is_written_to_in_german():
    class Germans(People):
        async def person_of(self, sub):
            return self.book.get(sub), "de-DE"

    mailer = LogMailer()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=Germans(), mailer=mailer)
    with TestClient(app) as c:
        c.portal.call(app.state.dispatcher.handle, _change("requested", by="payments"))
        c.portal.call(
            app.state.dispatcher.handle,
            _event(PAYOUT_SENT, bookingId="bk_1", ownerId="host", requesterId="buyer", amount=123456, currency="eur"),
        )
    assert [m.subject for m in mailer.sent] == ["Neue Anfrage: Table saw", "Du hast 1.234,56 € erhalten"]


def test_an_instant_booking_tells_both_sides(app):
    sent = _sent(app, _change("accepted", by="payments", frm="awaiting_payment"))
    assert sent == [("buyer@example.com", "Confirmed: Table saw"), ("host@example.com", "New booking: Table saw")]


def test_the_notification_centre_lists_marks_read_exports_and_forgets():
    from notifications.push import LogPusher

    from cappy_common.events import PROFILE_DELETED
    from cappy_common.testing import TestIssuer

    issuer, people = TestIssuer(), People()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=people, mailer=LogMailer(), pusher=LogPusher(), verifier=issuer.verifier())
    host, buyer = issuer.headers("host"), issuer.headers("buyer")
    with TestClient(app) as c:
        assert c.get("/notifications").status_code == 401
        e = _change("requested", by="payments")
        for ev in (e, e, _event(PAYOUT_SENT, bookingId="bk_1", ownerId="host", amount=4000, currency="eur")):
            c.portal.call(app.state.dispatcher.handle, ev)
        box = c.get("/notifications", headers=host).json()
        assert box["unread"] == 2, "a redelivered event shows once"
        assert [(i["kind"], i["link"], i["read"]) for i in box["items"]] == [
            ("paid", "/earn", False),
            ("requested", "/bookings/bk_1", False),
        ], "newest first, links inside the app"
        assert (
            box["items"][1]["title"] == "New request: Table saw"
            and "Answer by the booked start" in box["items"][1]["body"]
        )
        assert c.get("/notifications", headers=buyer).json() == {"items": [], "unread": 0}, "only their own"

        page = c.get("/notifications", params={"limit": 1}, headers=host).json()
        rest = c.get("/notifications", params={"limit": 1, "cursor": page["next"]}, headers=host).json()
        assert [i["kind"] for i in page["items"] + rest["items"]] == ["paid", "requested"] and "next" not in rest

        first = box["items"][0]["id"]
        assert c.post("/notifications/read", json={"ids": [first]}, headers=buyer).status_code == 204
        assert c.get("/notifications", headers=host).json()["unread"] == 2, "nobody marks another's"
        c.post("/notifications/read", json={"ids": [first]}, headers=host)
        assert c.get("/notifications", headers=host).json()["unread"] == 1
        c.post("/notifications/read", json={}, headers=host)
        assert c.get("/notifications", headers=host).json()["unread"] == 0

        assert c.get("/internal/people/host/export").status_code == 403
        export = c.get("/internal/people/host/export", headers={"X-Internal-Token": "i" * 40}).json()
        assert len(export["items"]) == 2 and export["settings"]["categories"]["marketing"]["email"] is False
        c.portal.call(app.state.dispatcher.handle, _event(PROFILE_DELETED, ownerId="host"))
        # The old token is revoked with the account (P-24) once the clock has
        # moved past its issue time, so look through the export, not the token.
        gone = c.get("/internal/people/host/export", headers={"X-Internal-Token": "i" * 40}).json()
        assert gone["items"] == [], "deleted with the account"


def test_the_bell_speaks_the_readers_language_and_names_the_real_deadline():
    """Stored once, rendered when read (V3-13): switching the app to German
    turns every item German, and a request says when it lapses."""
    from notifications.push import LogPusher

    from cappy_common.testing import TestIssuer

    issuer = TestIssuer()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=People(), mailer=LogMailer(), pusher=LogPusher(), verifier=issuer.verifier())
    host = issuer.headers("host")
    with TestClient(app) as c:
        # Lapses at 14:00 Berlin (12:00 UTC in summer time).
        c.portal.call(
            app.state.dispatcher.handle, _change("requested", by="payments", expiresAt="2026-09-26T12:00:00Z")
        )
        c.portal.call(
            app.state.dispatcher.handle,
            _event(PAYOUT_SENT, bookingId="bk_1", ownerId="host", amount=123456, currency="eur"),
        )
        assert app.state.mailer.sent[0].text.startswith("Someone wants to book Table saw. Answer by Sat 26 Sep, 14:00")
        en = c.get("/notifications", headers={**host, "Accept-Language": "en-GB,en;q=0.9"}).json()["items"]
        de = c.get("/notifications", headers={**host, "Accept-Language": "de-DE,de;q=0.9"}).json()["items"]
    assert [i["title"] for i in en] == ["You have been paid €1,234.56", "New request: Table saw"]
    assert [i["title"] for i in de] == ["Du hast 1.234,56 € erhalten", "Neue Anfrage: Table saw"]
    assert "bis Sa., 26.09., 14:00 Uhr" in de[1]["body"]


def test_settings_choose_channels_but_contract_emails_always_come():
    from notifications.push import LogPusher

    from cappy_common.events import PROFILE_DELETED
    from cappy_common.testing import TestIssuer

    issuer, pusher = TestIssuer(), LogPusher()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=People(), mailer=LogMailer(), pusher=pusher, verifier=issuer.verifier())
    host, buyer = issuer.headers("host"), issuer.headers("buyer")
    with TestClient(app) as c:
        assert c.get("/notifications/settings").status_code == 401
        prefs = c.get("/notifications/settings", headers=host).json()
        assert prefs["categories"]["bookings"] == {"push": True, "email": True}
        assert prefs["categories"]["marketing"] == {"push": False, "email": False}
        quiet = {"push": False, "email": False}
        body = {"categories": {k: quiet for k in ("bookings", "messages", "payouts", "marketing")}}
        for who in (host, buyer):
            assert c.put("/notifications/settings", json=body, headers=who).json() == body
        assert c.put("/notifications/settings", json={"categories": {}}, headers=host).status_code == 422
        c.post("/notifications/devices", json={"platform": "ios", "token": "tok-host-phone"}, headers=host)
        for ev in (
            _change("requested", by="payments"),  # optional: not emailed, not pushed
            _change("accepted", by="host", frm="requested"),  # the contract: emailed anyway
            _event(PAYOUT_SENT, bookingId="bk_1", ownerId="host", amount=4000, currency="eur"),
        ):
            c.portal.call(app.state.dispatcher.handle, ev)
        assert [(m.to, m.subject) for m in app.state.mailer.sent] == [("buyer@example.com", "Confirmed: Table saw")]
        assert pusher.sent == []
        assert c.get("/notifications", headers=host).json()["unread"] == 2, "the bell still has everything"
        c.portal.call(app.state.dispatcher.handle, _event(PROFILE_DELETED, ownerId="host"))
        assert c.get("/notifications/settings", headers=host).json()["categories"]["bookings"]["email"] is True


def test_signing_out_everywhere_revokes_tokens_and_forgets_devices():
    from notifications.push import LogPusher

    from cappy_common.testing import TestIssuer

    class Signing(People):
        signed_out: list[str] = []

        async def sign_out_everywhere(self, sub: str) -> None:
            self.signed_out.append(sub)

    issuer, people, pusher = TestIssuer(), Signing(), LogPusher()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=people, mailer=LogMailer(), pusher=pusher, verifier=issuer.verifier())
    with TestClient(app) as c:
        c.post(
            "/notifications/devices",
            json={"platform": "ios", "token": "tok-lost-phone"},
            headers=issuer.headers("host"),
        )
        # Catalog takes the request (it can publish); this is the event it sends.
        c.portal.call(app.state.dispatcher.handle, _event("person.signed_out", personId="host"))
        assert people.signed_out == ["host"]
        # Tokens issued before now no longer count here either (P-24).
        r = c.get("/notifications", headers=issuer.headers("host", iat=int(time.time()) - 60))
        assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
        assert c.get("/notifications", headers=issuer.headers("host", iat=int(time.time()) + 1)).status_code == 200
        c.portal.call(app.state.dispatcher.handle, _change("requested", by="payments"))
        assert pusher.sent == [], "the lost phone gets nothing"


def test_the_person_affected_gets_the_whole_statement_of_reasons(app):
    """DSA Art. 17(3): the restriction, the facts, automated or not, the ground
    and what they can do about it."""
    from cappy_common.events import MODERATION_DECISION

    sor = {
        "restriction": "The listing was removed and can no longer be seen or booked.",
        "facts": "The serial number matches a machine reported stolen.",
        "automated": False,
        "ground": "law",
        "clause": "§ 259 StGB",
        "redress": "…",
    }
    _sent(
        app,
        _event(
            MODERATION_DECISION,
            action="take_down",
            targetType="listing",
            targetId="l9",
            affectedId="host",
            statement=sor["facts"],
            statementOfReasons=sor,
        ),
    )
    [mail] = app.state.mailer.sent
    body = mail.text
    assert "The serial number matches" in body and "illegal content under § 259 StGB" in body
    assert "automated means: no" in body and "6 months" in body and "Art. 21" in body


def test_times_are_told_in_the_events_zone_berlin_by_default():
    from notifications.texts import render

    at = "2026-09-26T12:00:00Z"
    _, berlin = render("requested", "en", title="Van", link="/", _deadline=at)
    _, toronto = render("requested", "en", title="Van", link="/", _deadline=at, _tz="America/Toronto")
    assert "Sat 26 Sep, 14:00" in berlin and "Sat 26 Sep, 08:00" in toronto


def test_a_deleted_account_loses_its_sign_in_too():
    from cappy_common.events import PROFILE_DELETED

    people = People()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=people, mailer=LogMailer())
    with TestClient(app) as c:
        c.portal.call(app.state.dispatcher.handle, _event(PROFILE_DELETED, ownerId="host"))
    assert people.deleted == ["host"]


def test_a_push_token_moves_only_from_the_same_install():
    from notifications.push import LogPusher

    from cappy_common.testing import TestIssuer

    class Pusher(LogPusher):
        def __init__(self) -> None:
            super().__init__()
            self.deleted: list[str] = []

        async def unregister(self, endpoint: str) -> None:
            self.deleted.append(endpoint)

    issuer, pusher = TestIssuer(), Pusher()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, directory=People(), mailer=LogMailer(), pusher=pusher, verifier=issuer.verifier())
    phone = {"platform": "ios", "token": "tok-shared-phone", "installId": "install-" + "a" * 16}
    with TestClient(app) as c:
        assert c.post("/notifications/devices", json=phone, headers=issuer.headers("host")).status_code == 204
        # Someone who only knows the token cannot take it.
        stolen = {**phone, "installId": "install-" + "b" * 16}
        r = c.post("/notifications/devices", json=stolen, headers=issuer.headers("mallory"))
        assert r.status_code == 409 and r.json()["error"]["code"] == "device_taken"
        r = c.post("/notifications/devices", json={**phone, "installId": None}, headers=issuer.headers("mallory"))
        assert r.status_code == 409 and pusher.deleted == []
        # The same install, another person signing in: the old endpoint goes first.
        assert c.post("/notifications/devices", json=phone, headers=issuer.headers("buyer")).status_code == 204
        assert pusher.deleted == ["local:ios:tok-shared-p"]


def test_a_failed_capture_and_a_dispute_reach_both_sides(app):
    """FL-2: the owner learns a booking fell through, or is disputed."""
    sent = _sent(
        app,
        _change("payment_failed", by="payments", frm="awaiting_payment", bookingId="bk_a"),
        _change("payment_failed", by="payments", frm="accepted", bookingId="bk_b"),
        _change("disputed", by="buyer", frm="active", bookingId="bk_c"),
    )
    assert sent == [
        ("buyer@example.com", "Payment failed: Table saw"),
        ("buyer@example.com", "Payment failed: Table saw"),
        ("host@example.com", "Payment failed: Table saw"),
        ("host@example.com", "A problem was reported: Table saw"),
        ("buyer@example.com", "We received your report: Table saw"),
    ]


def test_french_readers_are_written_to_in_french_and_everything_is_translated():
    from notifications.texts import TEXTS, money, render

    assert TEXTS["fr"].keys() == TEXTS["en"].keys() == TEXTS["de"].keys()
    subject, body = render("requested", "fr-CA", title="Scie", link="x", _deadline="2026-09-26T12:00:00Z")
    assert subject == "Nouvelle demande\u00a0: Scie" and "sam. 26 sept., 14:00" in body
    assert money(123456, "cad", "fr-CA") == "1 234,56 $" and money(123456, "usd", "en-US") == "$1,234.56"
    assert (
        render("paid", "es-ES", amount="x", booking="b", web="w", _cents=(100, "eur"))[0] == "You have been paid €1.00"
    )
