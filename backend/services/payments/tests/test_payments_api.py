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
from payments.tables import ConnectAccountRow, IdentityRow, PaymentRow

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
    assert client.get("/payments/config").json() == {"provider": "fake", "identityProvider": "fake"}
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
    later = issuer.headers("leaver", iat=int(time.time()) + 1)  # a sign-in after the deletion
    assert client.get("/payments/connect/status", headers=later).json()["connected"] is False


def test_deletion_erases_the_id_check_at_the_provider_and_the_card_fingerprint(client, app, issuer):
    from cappy_common.events import PROFILE_DELETED

    h = issuer.headers("renter-1")
    assert client.post("/payments/identity/session", json={"consent": True}, headers=h).json()["status"] == "verified"
    _intent(client, requesterId="renter-1")

    async def fingerprint():
        async with app.state.db.transaction() as s:
            (await s.get(PaymentRow, "bk_1")).card_fingerprint = "fp_1"

    call(app, fingerprint)
    ev = Event(
        id=new_id("ev"), type=PROFILE_DELETED, source="catalog", occurred_at=now_iso(), data={"ownerId": "renter-1"}
    )
    assert call(app, app.state.dispatcher.handle, ev)
    assert app.state.identity.redacted == ["vs_fake_renter-1"]  # D-6

    async def left():
        async with app.state.db.transaction() as s:
            return (await s.get(PaymentRow, "bk_1")).card_fingerprint, await s.get(IdentityRow, "renter-1")

    assert call(app, left) == (None, None)


def test_payouts_only_where_owners_can_be_paid(client, issuer):
    h = issuer.headers("abroad")
    r = client.post("/payments/connect/onboarding", json={"country": "JP"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "country_unsupported"
    # Where Cappy is open (markets.json): Canada is planned, Switzerland live.
    r = client.post("/payments/connect/onboarding", json={"country": "CA"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "country_unsupported"
    assert client.post("/payments/connect/onboarding", json={"country": "CH"}, headers=h).status_code == 200


def test_another_identity_provider_reports_through_its_own_webhook(client, app, issuer):
    """F-1: a provider with its own webhook, in neutral words."""
    from payments.identity import IdentityResult, IdentitySession

    identity = app.state.identity
    identity.verifies_immediately = False

    async def start(person_id):
        return IdentitySession("idv_1", url="https://verify.example/idv_1")

    identity.start_session = start
    identity.parse_webhook = lambda payload, headers: IdentityResult("idv_1", "renter-3", json.loads(payload)["s"])
    h = issuer.headers("renter-3")
    started = client.post("/payments/identity/session", json={"consent": True}, headers=h).json()
    assert started["url"] == "https://verify.example/idv_1" and started["status"] == "pending"
    assert client.post("/payments/webhooks/identity", content=b'{"s": "needs_input"}').status_code == 200
    assert client.get("/payments/identity", headers=h).json()["status"] == "requires_input"
    assert client.post("/payments/webhooks/identity", content=b'{"s": "verified"}').status_code == 200
    assert client.post("/payments/webhooks/identity", content=b'{"s": "verified"}').json()["duplicate"] is True
    assert client.get("/payments/identity", headers=h).json()["status"] == "verified"


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
    # Nothing starts without the person's consent to the ID check (P-18).
    for body in (None, {"consent": False}):
        r = client.post("/payments/identity/session", json=body, headers=h)
        assert r.status_code == 422 and r.json()["error"]["code"] == "consent_required"
    yes = {"consent": True}
    assert (
        client.post("/payments/identity/session", json=yes, headers=h).json()["status"] == "verified"
    )  # the fake verifies at once
    assert client.post("/payments/identity/session", headers=h).json() == {"status": "verified"}

    async def consent():
        async with app.state.db.session() as s:
            row = await s.get(IdentityRow, "renter-1")
            return row.consent_at is not None, row.consent_version

    assert call(app, consent) == (True, "identity-2026-09")
    mine = client.get("/internal/people/renter-1/export", headers=INTERNAL).json()["identity"]
    assert mine["consentVersion"] == "identity-2026-09" and mine["consentAt"], "and it is in their export"
    call(app, app.state.relay.flush)
    assert [e.data["personId"] for e in broker.of_type(IDENTITY_VERIFIED)] == ["renter-1"]


def test_stripe_identity_outcome_comes_by_webhook(stripe_app, issuer, broker):
    from cappy_common.events import IDENTITY_VERIFIED

    app, c = stripe_app

    from payments.identity import IdentitySession

    async def session_for(person_id):
        return IdentitySession("vs_123", client_secret="vs_123_secret")

    app.state.identity.start_session = session_for
    h = issuer.headers("renter-2")
    started = c.post("/payments/identity/session", json={"consent": True}, headers=h).json()
    assert started["status"] == "pending" and started["clientSecret"] == "vs_123_secret"
    # An event about some other session carrying the person's id does nothing (P-28).
    body, headers = _signed(
        _event("identity.verification_session.verified", {"id": "vs_other", "metadata": {"personId": "renter-2"}})
    )
    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).status_code == 200
    assert c.get("/payments/identity", headers=h).json()["status"] == "pending"
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


def test_a_renter_no_show_refunds_nothing_and_is_an_ordinary_payout(client, app, provider, broker):
    # S-11: cancelled with refundAmount 0 — nothing back, the owner paid in full.
    _intent(client)
    _status(app, "bk_1", "accepted")
    ev = Event(
        id=new_id("ev"),
        type=BOOKING_STATUS_CHANGED,
        source="booking",
        occurred_at=now_iso(),
        data={"bookingId": "bk_1", "to": "cancelled", "refundAmount": 0},
    )
    assert call(app, app.state.dispatcher.handle, ev)
    assert [op for op, _ in provider.calls] == ["intent", "capture", "transfer"], "no refund call"
    body = client.get("/internal/bookings/bk_1/payment", headers=INTERNAL).json()
    assert (body["status"], body["refunded"], body["paidOut"]) == ("transferred", 0, 4000)


def test_a_dispute_settled_with_a_partial_refund_refunds_part_and_pays_the_rest(client, app, provider, broker):
    # H-6/S-21: booking completes the dispute with refundAmount set.
    _intent(client)
    _status(app, "bk_1", "accepted")
    ev = Event(
        id=new_id("ev"),
        type=BOOKING_STATUS_CHANGED,
        source="booking",
        occurred_at=now_iso(),
        data={"bookingId": "bk_1", "from": "disputed", "to": "completed", "refundAmount": 2300},
    )
    assert call(app, app.state.dispatcher.handle, ev)
    assert [op for op, _ in provider.calls] == ["intent", "capture", "refund", "transfer"]
    call(app, app.state.relay.flush)
    assert broker.of_type(PAYMENT_REFUNDED)[0].data["amount"] == 2300
    assert broker.of_type(PAYOUT_SENT)[0].data["amount"] == 2000
    state = client.get("/internal/bookings/bk_1/payment", headers=INTERNAL)
    body = state.json()
    assert (body["captured"], body["refunded"], body["paidOut"]) == (4600, 2300, 2000), "amounts, not flags"
    assert body["status"] == "partially_refunded"
    assert client.get("/internal/bookings/bk_1/payment").status_code == 403
    assert client.get("/internal/bookings/nope/payment", headers=INTERNAL).status_code == 404


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
    # A person has no business address: the payout provider's verified one (V4-7).
    assert "10115 Berlin<br>DE (test)" in page.text
    assert client.get(f"/payments/invoices/{inv['number']}", headers=issuer.headers("buyer")).status_code == 404


def test_the_fee_invoice_has_the_ustg_fields(client, app, issuer):
    """§ 14 (4) UStG: issuer and recipient with addresses, a tax number or VAT
    ID, the service and its date; dates are German days, not UTC."""
    _intent(client)
    _status(app, "bk_1", "accepted")
    about = {
        "title": "Band saw",
        "windowStart": "2026-09-25T22:30:00Z",  # 00:30 on the 26th in Berlin
        "windowEnd": "2026-09-26T01:00:00Z",
        "ownerName": "Nadia",
        "ownerBusiness": {
            "legalName": "Brandt Werkstatt GmbH",
            "address": "Ohlauer Str. 5, 10999 Berlin",
            "vatId": "DE123456789",
        },
    }
    ev = Event(
        id=new_id("ev"),
        type=BOOKING_STATUS_CHANGED,
        source="booking",
        occurred_at=now_iso(),
        data={"bookingId": "bk_1", "from": "active", "to": "completed", "by": "x", **about},
    )
    assert call(app, app.state.dispatcher.handle, ev)
    [inv] = client.get("/payments/invoices", headers=issuer.headers("host")).json()
    assert inv["description"] == "Service fee · Band saw · 26.09.2026" and inv["title"] == "Band saw"
    page = client.get(f"/payments/invoices/{inv['number']}", headers=issuer.headers("host")).text
    for field in (
        app.state.settings.legal_company,
        "Musterstraße 1",
        "Steuernummer",
        "Brandt Werkstatt GmbH",
        "Ohlauer Str. 5",
        "DE123456789",
        "Leistungsdatum: 26.09.2026",
        "Band saw",
    ):
        assert field in page, field
    assert "siehe Impressum" not in page


def test_the_issuer_zone_and_tax_are_settings():
    """Another market is settings, not code (GOAL 16): zone, rate and label."""
    import asyncio

    from payments.invoices import Issuer, issue

    from cappy_common.db import Database

    async def run():
        db = Database("sqlite+aiosqlite://")
        from payments.tables import Base

        async with db.engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with db.transaction() as s:
            ca = Issuer(time_zone="America/Toronto", tax_rate_bps=1300, tax_label="HST")
            # 02:00 UTC on 1 Jan 2027 is still 2026 in Toronto.
            import payments.invoices as inv

            real = inv.datetime

            class Frozen(real):
                @classmethod
                def now(cls, tz=None):
                    return real(2027, 1, 1, 2, 0, tzinfo=tz)

            inv.datetime = Frozen
            try:
                row = await issue(s, booking_id="bk_ca", owner_id="o", fee_gross=1130, currency="cad", issuer=ca)
            finally:
                inv.datetime = real
        await db.dispose()
        return row

    row = asyncio.run(run())
    assert row.number.startswith("CAP-2026-") and row.vat_rate_bps == 1300 and row.net == 1000


def test_production_needs_the_invoice_issuer():
    from payments.settings import Settings

    from cappy_common.settings import UnsafeSettings

    with pytest.raises(UnsafeSettings) as e:
        Settings(app_env="prod")
    assert "LEGAL_COMPANY" in str(e.value) and "LEGAL_VAT_ID" in str(e.value)


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


def test_invoices_are_deleted_once_their_retention_ends(client, app):
    """D-9: kept from the end of the year of issue for the issuer's period."""
    from datetime import UTC, datetime

    from payments.jobs import purge_invoices_once
    from payments.tables import InvoiceRow

    async def seed():
        async with app.state.db.transaction() as s:
            for number, year in (("CAP-2026-1", 2026), ("CAP-2027-1", 2027)):
                s.add(
                    InvoiceRow(
                        number=number,
                        booking_id=f"bk_{year}",
                        owner_id="o",
                        net=100,
                        vat_rate_bps=1900,
                        vat=19,
                        gross=119,
                        currency="eur",
                        issued_at=datetime(year, 12, 31, 12, tzinfo=UTC),
                    )
                )

    async def numbers():
        from sqlalchemy import select

        async with app.state.db.transaction() as s:
            return sorted((await s.execute(select(InvoiceRow.number))).scalars())

    call(app, seed)
    assert call(app, purge_invoices_once, app, datetime(2036, 12, 31, tzinfo=UTC)) == 0  # still within 10 years
    assert call(app, purge_invoices_once, app, datetime(2037, 1, 1, tzinfo=UTC)) == 1
    assert call(app, numbers) == ["CAP-2027-1"]


def test_the_fee_invoice_reads_in_the_owners_language(client, app, issuer):
    # V6-21: an English or French owner gets their invoice in their words,
    # named by the listing, the booking id only as the reference.
    _intent(client)
    _status(app, "bk_1", "accepted")
    _status(app, "bk_1", "completed")
    [inv] = client.get("/payments/invoices", headers=issuer.headers("host")).json()
    url = f"/payments/invoices/{inv['number']}"
    en = client.get(url, headers={**issuer.headers("host"), "Accept-Language": "en-US"}).text
    assert "Invoice" in en and "Rechnung" not in en and "€6.00" in en and "Booking reference: bk_1" in en
    assert "Tax number (Steuernummer)" in en, "a German issuer's fields stay"
    fr = client.get(url, headers={**issuer.headers("host"), "Accept-Language": "fr-CA"}).text
    assert "Facture" in fr and "6,00 €" in fr and "Référence de réservation" in fr


def test_the_fee_invoice_follows_the_readers_typography(client, app, issuer):
    # V7-10: French spacing, the tax in the reader's words, the reader's date
    # order, and the issuer's VAT ID and tax number both.
    _intent(client)
    _status(app, "bk_1", "accepted")
    _status(app, "bk_1", "completed")
    [inv] = client.get("/payments/invoices", headers=issuer.headers("host")).json()
    url = f"/payments/invoices/{inv['number']}"
    page = lambda lang: client.get(url, headers={**issuer.headers("host"), "Accept-Language": lang}).text  # noqa: E731
    fr, us, gb, de = page("fr-FR"), page("en-US"), page("en-GB"), page("de-DE")
    assert "Date de facture : " in fr and "TVA 19 %" in fr and "USt" not in fr.split("<table>")[1]
    assert "VAT 19%" in us and "USt" not in us.split("<table>")[1]
    from datetime import datetime
    from zoneinfo import ZoneInfo

    local = datetime.fromisoformat(inv["issuedAt"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Berlin"))
    y, m, d = local.year, local.month, local.day
    assert f"{m}/{d}/{y}" in us and f"{d:02d}/{m:02d}/{y}" in gb and f"{d:02d}.{m:02d}.{y}" in de
    assert "USt 19 %" in de
    for text in (fr, us, de):
        assert "USt-IdNr." in text and "Steuernummer" in text, "both of the issuer's lines"


# --- the chargeback lifecycle (R2-3) ------------------------------------------------------


class _Chargebacks(_StripeShaped):
    """Stripe-shaped, with the money calls recorded instead of sent."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []
        self.reversal_fails = False

    async def transfer(self, *, booking_id, amount, currency, account_id, charge_id) -> str:  # noqa: ANN001
        self.calls.append(("transfer", booking_id, amount))
        return f"tr_{booking_id}"

    async def reverse_transfer(self, transfer_id: str, amount: int, booking_id: str) -> str:
        if self.reversal_fails:
            raise RuntimeError("insufficient funds in the connected account")
        self.calls.append(("reverse", transfer_id, amount))
        return f"trr_{booking_id}"

    async def submit_dispute_evidence(self, dispute_id: str, text: str) -> None:
        self.calls.append(("evidence", dispute_id, text))

    async def account_address(self, account_id: str) -> str | None:
        return None


@pytest.fixture()
def chargebacks(issuer, broker):
    provider = _Chargebacks()
    app = build_app(_settings(payments_provider="stripe"), provider=provider, verifier=issuer.verifier())
    with TestClient(app) as c:
        app.state._portal = c.portal
        yield app, c, provider


def _paid(app, booking_id: str, charge: str, **row):
    from datetime import UTC, datetime

    async def go():
        async with app.state.db.transaction() as s:
            now = datetime.now(UTC)
            if await s.get(ConnectAccountRow, "host") is None:
                s.add(ConnectAccountRow(owner_id="host", account_id="acct_1", payouts_enabled=True, updated_at=now))
            s.add(
                PaymentRow(
                    booking_id=booking_id,
                    intent_id=f"pi_{booking_id}",
                    requester_id="buyer",
                    owner_id="host",
                    amount=4600,
                    owner_net=4000,
                    currency="EUR",
                    status=row.pop("status", "captured"),
                    charge_id=charge,
                    created_at=now,
                    updated_at=now,
                    **row,
                )
            )

    call(app, go)


def _dispute(c, kind: str, charge: str, status: str, due: int | None = None) -> None:
    obj = {"id": f"dp_{charge}", "object": "dispute", "charge": charge, "status": status}
    if due:
        obj["evidence_details"] = {"due_by": due}
    body, headers = _signed(_event(kind, obj))
    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).status_code == 200


def test_a_won_chargeback_pays_out_what_it_held(chargebacks, issuer):
    app, c, provider = chargebacks
    _paid(app, "bk_w", "ch_w")
    _dispute(c, "charge.dispute.created", "ch_w", "needs_response", due=int(time.time()) + 7 * 86400)
    assert _status(app, "bk_w", "completed")
    held = call(app, _payment, app, "bk_w")
    assert held.status == "captured" and held.held_payout and held.dispute_due_at is not None
    # Staff see it, with its deadline, and answer it; the answer is audited.
    staff = {"Authorization": f"Bearer {issuer.token('staff-1', **{'cognito:groups': ['admin']})}"}
    [cb] = c.get("/admin/payments/chargebacks", headers=staff).json()
    assert cb["bookingId"] == "bk_w" and cb["status"] == "needs_response" and cb["evidenceDueAt"]
    assert c.get("/admin/payments/chargebacks", headers=issuer.headers("buyer")).status_code == 403
    r = c.post(
        "/admin/payments/bk_w/dispute-evidence",
        json={"text": "Handed over on time, photos at both ends.", "links": ["https://cappy.app/b/bk_w"]},
        headers=staff,
    )
    assert r.status_code == 204 and provider.calls[-1][0] == "evidence"
    call(app, app.state.relay.flush)
    # Won: the owner is paid what they would have been, once.
    _dispute(c, "charge.dispute.closed", "ch_w", "won")
    p = call(app, _payment, app, "bk_w")
    assert p.status == "transferred" and p.chargeback_at is None and p.held_payout is None
    assert [x for x in provider.calls if x[0] == "transfer"] == [("transfer", "bk_w", 4000)]
    _dispute(c, "charge.dispute.closed", "ch_w", "won")
    assert len([x for x in provider.calls if x[0] == "transfer"]) == 1
    assert c.post("/admin/payments/bk_w/dispute-evidence", json={"text": "x" * 30}, headers=staff).status_code == 409


def test_a_lost_chargeback_takes_the_payout_back_or_records_the_debt(chargebacks):
    app, c, provider = chargebacks
    _paid(app, "bk_l", "ch_l", status="transferred", transfer_id="tr_bk_l", paid_out_amount=4000)
    _dispute(c, "charge.dispute.created", "ch_l", "needs_response")
    _dispute(c, "charge.dispute.closed", "ch_l", "lost")
    p = call(app, _payment, app, "bk_l")
    assert p.status == "charged_back" and p.recovered_amount == 4000 and p.owner_owes == 0
    assert ("reverse", "tr_bk_l", 4000) in provider.calls
    # When the owner's balance cannot cover it, the debt is recorded, not lost.
    provider.reversal_fails = True
    _paid(app, "bk_o", "ch_o", status="transferred", transfer_id="tr_bk_o", paid_out_amount=4000)
    _dispute(c, "charge.dispute.created", "ch_o", "needs_response")
    _dispute(c, "charge.dispute.closed", "ch_o", "lost")
    p = call(app, _payment, app, "bk_o")
    assert p.status == "charged_back" and p.owner_owes == 4000 and p.recovered_amount == 0
