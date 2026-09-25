"""Operator commands. ``python -m payments.cli --help``.

``demo-payouts`` gives a demo owner a Stripe *test-mode* connected account
that is already verified, so a local or staging stack running real Stripe can
take bookings and pay out without anyone filling in onboarding by hand. It
refuses to run with live keys or in prod (ADR 0010).
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import UTC, datetime

import stripe

from cappy_common.db import Database
from cappy_common.events import PAYOUTS_READY, Outbox

from .provider import FAKE_ACCOUNT_PREFIX
from .settings import Settings
from .tables import OUTBOX, ConnectAccountRow

# Stripe's documented test values: they verify instantly and move no money.
_TEST_ACCOUNT = {
    "type": "custom",
    "country": "DE",
    "business_type": "individual",
    "capabilities": {"transfers": {"requested": True}},
    "business_profile": {"mcc": "7394", "url": "https://cappy.example", "product_description": "Renting idle capacity"},
    "individual": {
        "first_name": "Demo",
        "last_name": "Owner",
        "phone": "+49 30 901820",
        "dob": {"day": 1, "month": 1, "year": 1901},
        "address": {"line1": "address_full_match", "city": "Berlin", "postal_code": "10115", "country": "DE"},
    },
    "external_account": {
        "object": "bank_account",
        "country": "DE",
        "currency": "eur",
        "account_number": "DE89370400440532013000",
    },
}


async def demo_payouts(owner_ids: list[str]) -> None:
    s = Settings()
    key = s.stripe_secret_key.get_secret_value()
    if s.app_env not in ("local", "staging", "test") or not key.startswith("sk_test_"):
        raise SystemExit("demo-payouts runs only with Stripe test keys, outside prod")
    client = stripe.StripeClient(key)
    db = Database(s.database_url)
    outbox = Outbox(OUTBOX, s.service_name)
    try:
        for owner in owner_ids:
            async with db.transaction() as session:
                row = await session.get(ConnectAccountRow, owner)
                if row is not None and row.payouts_enabled and not row.account_id.startswith(FAKE_ACCOUNT_PREFIX):
                    print(f"{owner}: already payable")
                    continue
                email = f"{owner[:40]}@demo.cappy.local"
                acct = client.v1.accounts.create(
                    {
                        **_TEST_ACCOUNT,
                        "email": email,
                        "individual": {**_TEST_ACCOUNT["individual"], "email": email},
                        "tos_acceptance": {"date": int(time.time()), "ip": "8.8.8.8"},
                        "metadata": {"ownerId": owner, "demo": "true"},
                    },
                    {"idempotency_key": f"demo-account-{owner}"},
                )
                now = datetime.now(UTC)
                if row is None:
                    row = ConnectAccountRow(owner_id=owner, account_id=acct.id, updated_at=now)
                    session.add(row)
                row.account_id, row.payouts_enabled, row.details_submitted, row.updated_at = acct.id, True, True, now
                await session.flush()
                await outbox.add(session, PAYOUTS_READY, {"ownerId": owner, "ready": True, "asOf": now.isoformat()})
                print(f"{owner}: linked a verified test account")
    finally:
        await db.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="payments")
    sub = parser.add_subparsers(dest="cmd", required=True)
    demo = sub.add_parser("demo-payouts", help="verified Stripe test accounts for demo owners (test keys only)")
    demo.add_argument("owners", nargs="+", help="owner ids (Cognito subs)")
    args = parser.parse_args(argv)
    if args.cmd == "demo-payouts":
        asyncio.run(demo_payouts(args.owners))


if __name__ == "__main__":
    main()
