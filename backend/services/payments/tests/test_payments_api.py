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


def test_the_owner_share_cannot_exceed_the_price(client):
    assert _intent(client, ownerNet=5000).status_code == 422


def test_money_follows_the_booking(client, app, provider, broker):
    _intent(client)
    assert _status(app, "bk_1", "accepted")
    assert call(app, _payment, app, "bk_1").status == "captured"
    assert _status(app, "bk_1", "completed")
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

    async def account_status(self, account_id: str) -> AccountStatus:
        return AccountStatus(False, False)


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


def test_webhook_keeps_accounts_current(stripe_app, issuer):
    app, c = stripe_app

    async def connect():
        from datetime import UTC, datetime

        async with app.state.db.transaction() as s:
            s.add(ConnectAccountRow(owner_id="host", account_id="acct_9", updated_at=datetime.now(UTC)))

    call(app, connect)
    body, headers = _signed(
        _event("account.updated", {"id": "acct_9", "payouts_enabled": True, "details_submitted": True})
    )
    assert c.post("/payments/webhooks/stripe", content=body, headers=headers).status_code == 200
    assert c.get("/payments/connect/status", headers=issuer.headers("host")).json()["payoutsEnabled"] is True


def test_deployed_payments_require_stripe():
    with pytest.raises(RuntimeError, match="PAYMENTS_PROVIDER"):
        Settings(app_env="prod", internal_token="i" * 40, auth_issuer="https://x", auth_client_ids="c")
