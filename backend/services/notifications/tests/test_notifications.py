from __future__ import annotations

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

    async def email_of(self, sub: str) -> str | None:
        return self.book.get(sub)


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


def test_a_chat_message_is_pushed_never_emailed():
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
        ev = _event(BOOKING_MESSAGE, bookingId="bk_1", senderId="buyer", recipientId="host", title="Table saw")
        c.portal.call(app.state.dispatcher.handle, ev)
    assert [t for _, t in pusher.sent] == ["New message: Table saw"]
    assert mailer.sent == []


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
