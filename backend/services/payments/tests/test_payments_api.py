"""Payments: intents, onboarding, the webhook, and money following the booking."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from payments.handlers import NotReady
from payments.main import build_app
from payments.provider import AccountStatus, FakeProvider, Intent, StripeProvider
from payments.settings import Settings
from payments.tables import ConnectAccountRow, PaymentRow

from cappy_common.events import (
    BOOKING_STATUS_CHANGED,
    PAYMENT_AUTHORISED,
    PAYMENT_CAPTURED,
    PAYMENT_REFUNDED,
    PAYOUT_SENT,
    PAYOUTS_READY,
    Event,
    reset_memory_broker,
)
from cappy_common.ids import new_id
from cappy_common.testing import TestIssuer
from cappy_common.timeutil import now_iso

INTERNAL = {"X-Internal-Token": "i" * 40}
WEBHOOK_SECRET = "whsec_test"


def _settings(**over) -> Settings:
    return Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40, **over)


@pytest.fixture()
def issuer():
    return TestIssuer()


@pytest.fixture()
def broker():
    return reset_memory_broker()


@pytest.fixture()
def provider():
    return FakeProvider()


@pytest.fixture()
def app(issuer, broker, provider):
    return build_app(_settings(), provider=provider, verifier=issuer.verifier())


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        app.state._portal = c.portal
        yield c


def call(app, fn, *args, **kwargs):
    return app.state._portal.call(lambda: fn(*args, **kwargs))


def _intent(client, booking_id="bk_1", owner="host", **over):
    body = {
        "bookingId": booking_id,
        "requesterId": "buyer",
        "ownerId": owner,
        "amount": 4600,
        "ownerNet": 4000,
        "currency": "eur",
        **over,
    }
    return client.post("/internal/intents", json=body, headers=INTERNAL)


def _status(app, booking_id: str, to: str) -> bool:
    ev = Event(
        id=new_id("ev"),
        type=BOOKING_STATUS_CHANGED,
        source="booking",
        occurred_at=now_iso(),
        data={"bookingId": booking_id, "from": None, "to": to, "by": "x"},
    )
    return call(app, app.state.dispatcher.handle, ev)


async def _payment(app, booking_id: str) -> PaymentRow:
    async with app.state.db.session() as s:
        return await s.get(PaymentRow, booking_id)


def test_intents_are_internal_and_idempotent(client, app, broker):
    assert client.post("/internal/intents", json={}).status_code == 403
    a, b = _intent(client).json(), _intent(client).json()
    assert a["intentId"] == b["intentId"] and a["clientSecret"]
    call(app, app.state.relay.flush)
    # The fake has no card step: authorised at once, announced once.
    assert [e.data["bookingId"] for e in broker.of_type(PAYMENT_AUTHORISED)] == ["bk_1"]
    assert broker.of_type(PAYMENT_AUTHORISED)[0].data["cardFingerprint"] == "fp_fake_buyer"


def test_the_owner_share_cannot_exceed_the_price(client):
    assert _intent(client, ownerNet=5000).status_code == 422


def test_money_follows_the_booking(client, app, provider, broker):
    _intent(client)
    assert _status(app, "bk_1", "accepted")
    assert call(app, _payment, app, "bk_1").status == "captured"
    owed = lambda: client.get("/internal/people/host/open", headers=INTERNAL).json()  # noqa: E731
    assert owed() == {"pendingPayouts": 1}, "the host cannot delete their account before being paid"
    assert _status(app, "bk_1", "completed")
    assert owed() == {"pendingPayouts": 0}
    p = call(app, _payment, app, "bk_1")
    assert p.status == "transferred" and p.transfer_id
    assert [op for op, _ in provider.calls] == ["intent", "capture", "transfer"]
    call(app, app.state.relay.flush)
    assert broker.of_type(PAYMENT_CAPTURED) and broker.of_type(PAYOUT_SENT)[0].data["amount"] == 4000


def test_declines_release_the_hold_and_late_cancels_refund(client, app, provider, broker):
    _intent(client, "bk_d")
    _status(app, "bk_d", "declined")
    assert call(app, _payment, app, "bk_d").status == "cancelled"
    _intent(client, "bk_c")
    _status(app, "bk_c", "accepted")
    _status(app, "bk_c", "cancelled")
    assert call(app, _payment, app, "bk_c").status == "refunded"
    call(app, app.state.relay.flush)
    assert [e.data["bookingId"] for e in broker.of_type(PAYMENT_REFUNDED)] == ["bk_c"]
    # Nothing more happens to a settled payment.
    _status(app, "bk_c", "cancelled")
    assert [op for op, k in provider.calls if k == "bk_c"] == ["intent", "capture", "refund"]


def test_a_failed_stripe_call_leaves_the_event_to_be_retried(client, app, provider):
    _intent(client)
    provider.failing.add("capture")
    ev = Event(
        id=new_id("ev"),
        type=BOOKING_STATUS_CHANGED,
        source="booking",
        occurred_at=now_iso(),
        data={"bookingId": "bk_1", "to": "accepted"},
    )
    with pytest.raises(RuntimeError):
        call(app, app.state.dispatcher.handle, ev)
    assert call(app, _payment, app, "bk_1").status == "authorised"
    provider.failing.clear()
    assert call(app, app.state.dispatcher.handle, ev) is True
    assert call(app, _payment, app, "bk_1").status == "captured"


def test_a_payout_before_capture_waits(client, app):
    _intent(client)
    with pytest.raises(NotReady):
        _status(app, "bk_1", "completed")


def test_payment_is_visible_to_its_two_parties_only(client, issuer):
    _intent(client)
    assert client.get("/payments/bookings/bk_1", headers=issuer.headers("buyer")).json()["status"] == "authorised"
    assert client.get("/payments/bookings/bk_1", headers=issuer.headers("host")).status_code == 200
    assert client.get("/payments/bookings/bk_1", headers=issuer.headers("stranger")).status_code == 404
    assert client.get("/payments/bookings/bk_1").status_code == 401


def test_payout_readiness_is_announced_once_per_change(client, app, broker):
    _intent(client, "bk_a", owner="new-host")
    _intent(client, "bk_b", owner="new-host")
    call(app, app.state.relay.flush)
    [e] = broker.of_type(PAYOUTS_READY)
    assert (e.data["ownerId"], e.data["ready"]) == ("new-host", True) and e.data["asOf"]


def test_config_and_onboarding(client, issuer):
    assert client.get("/payments/config").json() == {"provider": "fake"}
    h = issuer.headers("new-owner")
    assert client.get("/payments/connect/status", headers=h).json()["connected"] is False
    assert client.post("/payments/connect/onboarding", headers=h).json()["url"].endswith("/earn?payments=done")
    assert client.get("/payments/connect/status", headers=h).json()["payoutsEnabled"] is True


# --- the real provider's webhook, with a genuine signature ------------------------------------


class _StripeShaped(StripeProvider):
    """The real webhook verification with the network calls stubbed."""

    def __init__(self) -> None:
        super().__init__("sk_test_x", WEBHOOK_SECRET)

    async def create_intent(self, *, booking_id, amount, currency, metadata) -> Intent:  # noqa: ANN001
        return Intent(id=f"pi_{booking_id}", client_secret="pi_secret")

    status = AccountStatus(False, False)

    async def card_fingerprint(self, intent_id: str, requester_id: str) -> str | None:
        return "fp_stripe_card"

    async def account_status(self, account_id: str) -> AccountStatus:
        return self.status


def _signed(payload: dict, secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"stripe-signature": f"t={t},v1={sig}", "content-type": "application/json"}


def _event(kind: str, obj: dict) -> dict:
    return {"id": new_id("evt"), "object": "event", "type": kind, "data": {"object": obj}}


@pytest.fixture()
def stripe_app(issuer, broker):
    app = build_app(_settings(payments_provider="stripe"), provider=_StripeShaped(), verifier=issuer.verifier())
    with TestClient(app) as c:
        app.state._portal = c.portal
        yield app, c


def test_unpayable_owners_are_refused(stripe_app):
    _, c = stripe_app
    r = _intent(c, owner="not-onboarded")
    assert r.status_code == 409


def test_webhook_authorises_once_and_rejects_forgeries(stripe_app, broker):
    app, c = stripe_app

    async def onboard():
        from datetime import UTC, datetime

        async with app.state.db.transaction() as s:
            s.add(
                ConnectAccountRow(
                    owner_id="host", account_id="acct_1", payouts_enabled=True, updated_at=datetime.now(UTC)
                )
            )

    call(app, onboard)
    assert _intent(c).status_code == 200
    assert call(app, _payment, app, "bk_1").status == "created"

    event = _event("payment_intent.amount_capturable_updated", {"id": "pi_bk_1", "object": "payment_intent"})
    body, headers = _signed(event)
    forged_body, forged_headers = _signed(event, secret="whsec_wrong")
    assert c.post("/payments/webhooks/stripe", content=forged_body, headers=forged_headers).status_code == 422
    assert (
        c.post("/payments/webhooks/stripe", content=body, headers={"content-type": "application/json"}).status_code
        == 422
    )

    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).json() == {"received": True}
    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).json()["duplicate"] is True
    assert call(app, _payment, app, "bk_1").status == "authorised"
    call(app, app.state.relay.flush)
    assert len(broker.of_type(PAYMENT_AUTHORISED)) == 1
    # Booking links cards shared with suspended accounts (S-17).
    assert broker.of_type(PAYMENT_AUTHORISED)[0].data["cardFingerprint"] == "fp_stripe_card"
    assert call(app, _payment, app, "bk_1").card_fingerprint == "fp_stripe_card"


def test_webhook_keeps_accounts_current(stripe_app, issuer, broker):
    app, c = stripe_app

    async def connect():
        from datetime import UTC, datetime

        async with app.state.db.transaction() as s:
            s.add(ConnectAccountRow(owner_id="host", account_id="acct_9", updated_at=datetime.now(UTC)))

    call(app, connect)
    # The webhook asks Stripe for the current state rather than trusting the payload.
    app.state.provider.status = AccountStatus(True, True)
    body, headers = _signed(
        _event("account.updated", {"id": "acct_9", "payouts_enabled": True, "details_submitted": True})
    )
    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).status_code == 200
    assert c.get("/payments/connect/status", headers=issuer.headers("host")).json()["payoutsEnabled"] is True
    call(app, app.state.relay.flush)
    assert [(e.data["ownerId"], e.data["ready"]) for e in broker.of_type(PAYOUTS_READY)] == [("host", True)]


def test_deployed_payments_require_stripe():
    with pytest.raises(RuntimeError, match="PAYMENTS_PROVIDER"):
        Settings(app_env="prod", internal_token="i" * 40, auth_issuer="https://x", auth_client_ids="c")


def test_a_declined_capture_tells_booking_and_takes_nothing(client, app, provider, broker):
    from cappy_common.events import PAYMENT_FAILED

    _intent(client)
    provider.failing.add("capture_declined")
    assert _status(app, "bk_1", "accepted")
    assert call(app, _payment, app, "bk_1").status == "failed"
    call(app, app.state.relay.flush)
    [failed] = broker.of_type(PAYMENT_FAILED)
    assert failed.data["bookingId"] == "bk_1" and failed.data["stage"] == "capture"
    # The booking then becomes payment_failed; nothing further happens here.
    _status(app, "bk_1", "payment_failed")
    assert [op for op, _ in provider.calls] == ["intent"]


def test_accounts_the_fake_provider_made_do_not_count_with_stripe(stripe_app):
    app, c = stripe_app

    async def leftover():
        from datetime import UTC, datetime

        async with app.state.db.transaction() as s:
            s.add(
                ConnectAccountRow(
                    owner_id="host", account_id="acct_fake_host", payouts_enabled=True, updated_at=datetime.now(UTC)
                )
            )

    call(app, leftover)
    assert _intent(c).status_code == 409


def test_a_deleted_profile_loses_its_payout_link(client, app, issuer):
    from cappy_common.events import PROFILE_DELETED

    client.post("/payments/connect/onboarding", headers=issuer.headers("leaver"))
    assert client.get("/payments/connect/status", headers=issuer.headers("leaver")).json()["connected"]
    ev = Event(
        id=new_id("ev"), type=PROFILE_DELETED, source="catalog", occurred_at=now_iso(), data={"ownerId": "leaver"}
    )
    assert call(app, app.state.dispatcher.handle, ev)
    assert client.get("/payments/connect/status", headers=issuer.headers("leaver")).json()["connected"] is False


def test_a_chargeback_holds_the_payout(stripe_app, broker):
    from datetime import UTC, datetime

    app, c = stripe_app

    async def captured():
        async with app.state.db.transaction() as s:
            s.add(
                ConnectAccountRow(
                    owner_id="host", account_id="acct_1", payouts_enabled=True, updated_at=datetime.now(UTC)
                )
            )
            now = datetime.now(UTC)
            s.add(
                PaymentRow(
                    booking_id="bk_cb",
                    intent_id="pi_cb",
                    requester_id="buyer",
                    owner_id="host",
                    amount=4600,
                    owner_net=4000,
                    currency="eur",
                    status="captured",
                    charge_id="ch_cb",
                    created_at=now,
                    updated_at=now,
                )
            )

    call(app, captured)
    body, headers = _signed(_event("charge.dispute.created", {"id": "dp_1", "object": "dispute", "charge": "ch_cb"}))
    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).status_code == 200
    assert call(app, _payment, app, "bk_cb").chargeback_at is not None
    assert _status(app, "bk_cb", "completed")
    assert call(app, _payment, app, "bk_cb").status == "captured", "not paid out"


def test_a_lost_webhook_is_made_good_by_reconciliation(stripe_app, broker):
    from datetime import UTC, datetime, timedelta

    from payments.jobs import reconcile_once

    app, c = stripe_app

    async def stuck():
        async with app.state.db.transaction() as s:
            old = datetime.now(UTC) - timedelta(minutes=15)
            for bid, intent in (("bk_lost", "pi_lost"), ("bk_gone", "pi_gone"), ("bk_new", "pi_new")):
                created = old if bid != "bk_new" else datetime.now(UTC)
                s.add(
                    PaymentRow(
                        booking_id=bid,
                        intent_id=intent,
                        requester_id="b",
                        owner_id="h",
                        amount=100,
                        owner_net=80,
                        currency="eur",
                        status="created",
                        created_at=created,
                        updated_at=created,
                    )
                )

    call(app, stuck)
    statuses = {"pi_lost": "requires_capture", "pi_gone": "canceled", "pi_new": "requires_capture"}

    async def status(intent_id):
        return statuses[intent_id]

    app.state.provider.intent_status = status
    assert call(app, reconcile_once, app) == 2
    assert call(app, _payment, app, "bk_lost").status == "authorised"
    assert call(app, _payment, app, "bk_gone").status == "cancelled"
    assert call(app, _payment, app, "bk_new").status == "created", "too young to be suspicious"
    call(app, app.state.relay.flush)
    assert [e.data["bookingId"] for e in broker.of_type(PAYMENT_AUTHORISED)] == ["bk_lost"]


def test_the_payouts_kill_switch_holds_payouts_on_the_queue(issuer, broker):
    provider = FakeProvider()
    app = build_app(_settings(payouts_on=False), provider=provider, verifier=issuer.verifier())
    with TestClient(app) as c:
        app.state._portal = c.portal
        _intent(c)
        _status(app, "bk_1", "accepted")
        with pytest.raises(NotReady):
            _status(app, "bk_1", "completed")
        assert "transfer" not in [op for op, _ in provider.calls]


def test_identity_is_verified_once_and_announced(client, app, issuer, broker):
    from cappy_common.events import IDENTITY_VERIFIED

    h = issuer.headers("renter-1")
    assert client.get("/payments/identity", headers=h).json() == {"status": "none"}
    assert (
        client.post("/payments/identity/session", headers=h).json()["status"] == "verified"
    )  # the fake verifies at once
    assert client.post("/payments/identity/session", headers=h).json() == {"status": "verified"}
    call(app, app.state.relay.flush)
    assert [e.data["personId"] for e in broker.of_type(IDENTITY_VERIFIED)] == ["renter-1"]


def test_stripe_identity_outcome_comes_by_webhook(stripe_app, issuer, broker):
    from cappy_common.events import IDENTITY_VERIFIED

    app, c = stripe_app

    async def session_for(person_id):
        return "vs_123", "vs_123_secret"

    app.state.provider.verification_session = session_for
    h = issuer.headers("renter-2")
    started = c.post("/payments/identity/session", headers=h).json()
    assert started == {"status": "pending", "clientSecret": "vs_123_secret"}
    body, headers = _signed(
        _event("identity.verification_session.verified", {"id": "vs_123", "metadata": {"personId": "renter-2"}})
    )
    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).status_code == 200
    assert c.get("/payments/identity", headers=h).json()["status"] == "verified"
    call(app, app.state.relay.flush)
    assert len(broker.of_type(IDENTITY_VERIFIED)) == 1


def test_a_late_cancellation_refunds_part_and_pays_the_owner_their_share(client, app, provider, broker):
    _intent(client)
    _status(app, "bk_1", "accepted")
    ev = Event(
        id=new_id("ev"),
        type=BOOKING_STATUS_CHANGED,
        source="booking",
        occurred_at=now_iso(),
        data={"bookingId": "bk_1", "to": "cancelled", "refundAmount": 2300},
    )
    assert call(app, app.state.dispatcher.handle, ev)
    assert [op for op, _ in provider.calls] == ["intent", "capture", "refund", "transfer"]
    call(app, app.state.relay.flush)
    assert broker.of_type(PAYMENT_REFUNDED)[0].data["amount"] == 2300
    assert broker.of_type(PAYOUT_SENT)[0].data["amount"] == 2000, "the owner's 4000/4600 of the 2300 kept"


def test_a_payout_issues_one_numbered_fee_invoice(client, app, issuer):
    _intent(client)
    _status(app, "bk_1", "accepted")
    _status(app, "bk_1", "completed")
    _status(app, "bk_1", "completed")  # redelivered: still one invoice
    [inv] = client.get("/payments/invoices", headers=issuer.headers("host")).json()
    assert inv["number"].endswith("-0000001") and inv["gross"] == 600 and inv["net"] + inv["vat"] == 600
    assert inv["vatRateBps"] == 1900 and inv["net"] == 504
    page = client.get(f"/payments/invoices/{inv['number']}", headers=issuer.headers("host"))
    assert page.status_code == 200 and "Rechnung" in page.text and "6,00 €" in page.text
    assert client.get(f"/payments/invoices/{inv['number']}", headers=issuer.headers("buyer")).status_code == 404


def test_a_late_cancellation_payout_waits_while_payouts_are_off(issuer, broker):
    provider = FakeProvider()
    app = build_app(_settings(payouts_on=False), provider=provider, verifier=issuer.verifier())
    with TestClient(app) as c:
        app.state._portal = c.portal
        _intent(c)
        _status(app, "bk_1", "accepted")
        ev = Event(
            id=new_id("ev"),
            type=BOOKING_STATUS_CHANGED,
            source="booking",
            occurred_at=now_iso(),
            data={"bookingId": "bk_1", "to": "cancelled", "refundAmount": 0},
        )
        with pytest.raises(NotReady):
            call(app, app.state.dispatcher.handle, ev)
        assert "transfer" not in [op for op, _ in provider.calls]
