"""The Stripe provider against stripe-mock: request shapes Stripe accepts.

docker run --rm -p 12111:12111 stripe/stripe-mock
CAPPY_TEST_STRIPE_MOCK=http://localhost:12111 uv run pytest -m stripe_mock
"""

from __future__ import annotations

import os

import pytest
from payments.provider import StripeProvider

pytestmark = pytest.mark.stripe_mock


@pytest.fixture()
def stripe_provider():
    base = os.environ.get("CAPPY_TEST_STRIPE_MOCK")
    if not base:
        pytest.skip("CAPPY_TEST_STRIPE_MOCK not set")
    return StripeProvider("sk_test_123", "whsec_x", base)


async def test_the_whole_money_path_is_accepted_by_stripe(stripe_provider):
    p = stripe_provider
    intent = await p.create_intent(booking_id="bk_1", amount=4600, currency="eur", metadata={"ownerId": "o1"})
    assert intent.id.startswith("pi_") and intent.client_secret
    assert await p.client_secret(intent.id)
    # The expanded payment method's card fingerprint (S-17); stripe-mock's
    # fixture may carry none, so only the request's shape is checked.
    await p.card_fingerprint(intent.id, "buyer")
    # stripe-mock answers with static fixtures, which leave latest_charge empty;
    # real Stripe always sets it on a captured intent.
    charge = await p.capture(intent.id, "bk_1") or "ch_from_real_stripe"
    await p.cancel(intent.id, "bk_2")
    assert (await p.refund(intent.id, "bk_1")).startswith("re_")
    account = await p.create_account("o1")
    assert account.startswith("acct_")
    assert (await p.onboarding_link(account, "https://x/done", "https://x/retry")).startswith("http")
    await p.account_status(account)
    transfer = await p.transfer(booking_id="bk_1", amount=4000, currency="eur", account_id=account, charge_id=charge)
    assert transfer.startswith("tr_")


async def test_identity_sessions_are_accepted_by_stripe(stripe_provider):
    session_id, _secret = await stripe_provider.verification_session("renter-1")
    # The request shape is what this checks; stripe-mock's fixture has no
    # client secret, which real Stripe always returns for a new session.
    assert session_id.startswith("vs_")
