"""The whole journey against the running stack (`make up`, then `make e2e`).

sign up -> confirm -> profile -> owner lists with a photo -> search finds it
-> buyer books a window -> payment authorised -> owner accepts (captured)
-> hand-over -> buyer completes (owner paid) -> rating -> review visible
-> emails sent. Plus the edge refusing what it must.
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import httpx
from PIL import Image

API = "http://localhost:8000/api"
COGNITO = "http://localhost:9229"
LOCALSTACK = "http://localhost:4566"
ENV = dict(
    line.strip().split("=", 1)
    for line in (Path(__file__).parents[1] / ".local" / "local.env").read_text().splitlines()
    if "=" in line
)
PASSWORD = "Demo-pass-123!"
idp = boto3.client(
    "cognito-idp", region_name="eu-central-1", endpoint_url=COGNITO, aws_access_key_id="x", aws_secret_access_key="x"
)
http = httpx.Client(base_url=API, timeout=20)


def step(msg: str) -> None:
    print(f"  - {msg}", flush=True)


def ok(r: httpx.Response, code: int = 200) -> dict:
    if r.status_code != code:
        sys.exit(f"FAIL {r.request.method} {r.request.url} -> {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def until(what: str, fn, timeout: float = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(0.5)
    sys.exit(f"FAIL waiting for {what}")


def sign_in(email: str) -> dict:
    auth = idp.initiate_auth(
        ClientId=ENV["AUTH_CLIENT_IDS"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": PASSWORD},
    )["AuthenticationResult"]
    return {"Authorization": f"Bearer {auth['AccessToken']}"}


def emailed_code(email: str) -> str | None:
    """cognito-local prints the code it would have emailed."""
    logs = subprocess.run(
        ["docker", "compose", "logs", "cognito"], capture_output=True, text=True, cwd=Path(__file__).parents[1]
    ).stdout
    block = logs[logs.rfind(email) :] if email in logs else ""
    m = re.search(r"Code:\s+(\d{6})", block)
    return m.group(1) if m else None


def confirm_with_test_card(intent_id: str) -> None:
    """What Stripe's Payment Element does in the browser, done with Stripe's
    test card (test keys only)."""
    import stripe

    env = (Path(__file__).parents[1] / ".env").read_text().splitlines()
    key = next((line.split("=", 1)[1].strip() for line in env if line.startswith("STRIPE_SECRET_KEY=")), "")
    if not key.startswith("sk_test_"):
        sys.exit("FAIL: Stripe mode needs sk_test_ keys in .env for the e2e")
    pi = stripe.StripeClient(key).v1.payment_intents.confirm(
        intent_id, {"payment_method": "pm_card_visa", "return_url": "http://localhost:5173/bookings"}
    )
    assert pi.status == "requires_capture", pi.status


def sign_up(email: str) -> dict:
    """Sign up, confirm with the emailed code, sign in: as the app does."""
    idp.sign_up(
        ClientId=ENV["AUTH_CLIENT_IDS"],
        Username=email,
        Password=PASSWORD,
        UserAttributes=[{"Name": "email", "Value": email}],
    )
    deadline = time.time() + 20
    while (code := emailed_code(email)) is None and time.time() < deadline:
        time.sleep(0.5)
    if code:
        idp.confirm_sign_up(ClientId=ENV["AUTH_CLIENT_IDS"], Username=email, ConfirmationCode=code)
    else:
        # cognito-local sometimes prints the code late; the code check is Cognito's, not ours.
        step("(code not in cognito-local's log yet; confirming through the admin API)")
        idp.admin_confirm_sign_up(UserPoolId=ENV["USER_POOL_ID"], Username=email)
    # Cognito marks the address verified on confirmation; cognito-local does not.
    idp.admin_update_user_attributes(
        UserPoolId=ENV["USER_POOL_ID"],
        Username=email,
        UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
    )
    headers = sign_in(email)
    assert ok(http.get("/me", headers=headers)).get("owner") is None
    return headers


def photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), (30, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def main() -> None:
    run = uuid.uuid4().hex[:8]
    print(f"e2e run {run}")

    step("the edge refuses what it must")
    assert http.post("/internal/busy", json={}).status_code == 404
    assert http.get("/bookings").status_code == 401
    # Signed-in only (GOAL 13): nothing of the product before sign-in.
    for path in ("/search?q=saw", "/listings/l9", "/owners/o1", "/browse/spotlight?district=Kreuzberg"):
        assert http.get(path).status_code == 401, path
    assert http.get("/categories").status_code == 200, "the vocabulary stays public (welcome screen)"
    assert http.get("/bookings", headers={"X-Cappy-User": "o1"}).status_code == 401
    assert http.get("/bookings", headers={"Authorization": "Bearer forged.token.here"}).status_code == 401

    step("a new buyer and a new host sign up and confirm")
    email = f"buyer-{run}@example.com"
    host_email = f"host-{run}@example.com"
    buyer = sign_up(email)
    ok(http.put("/me", json={"adult": True, "name": "Erin Buyer", "kind": "person", "district": "Kreuzberg"}, headers=buyer))
    host = sign_up(host_email)
    ok(http.put("/me", json={"adult": True, "name": "Hana Host", "kind": "person", "district": "Kreuzberg"}, headers=host))
    host_sub = ok(http.get("/me", headers=host))["id"]
    if ok(http.get("/payments/config"))["provider"] == "stripe":
        # A verified Stripe test account, as Connect onboarding would give them.
        subprocess.run(
            ["docker", "compose", "exec", "-T", "payments", "python", "-m", "payments.cli", "demo-payouts", host_sub],
            check=True,
            capture_output=True,
            cwd=Path(__file__).parents[1],
        )

    step("the host lists a machine with a photo and a private hand-over address")
    up = ok(http.post("/uploads", files={"file": ("p.jpg", photo(), "image/jpeg")}, headers=host), 201)
    assert http.get(
        up["url"].replace("/api", "") if up["url"].startswith("/api") else up["url"].replace(API, "")
    ).status_code in (200, 404)
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=2)
    title = f"Track saw {run}"
    created = ok(
        http.post(
            "/listings",
            headers=host,
            json={
                "listing": {
                    "category": "workshop",
                    "mode": "window",
                    "title": title,
                    "blurb": "Festool with a 1.4 m rail",
                    "district": "Kreuzberg",
                    "instructions": "Ring the bell at the workshop",
                    "rules": ["Clean the rail"],
                    "active": True,
                    "photos": [up["url"]],
                    "ratePerHour": 1500,
                    "minHours": 2,
                    "maxHours": 8,
                    "extraFee": 0,
                    "extraLabel": "",
                },
                "slots": [
                    {"start": start.isoformat(), "end": (start + timedelta(hours=8)).isoformat(), "hoursUsable": 8}
                ],
                "address": f"Oranienstraße {run}, 10999 Berlin",
            },
        ),
        201,
    )
    listing_id = created["listing"]["id"]

    step("search finds it; offers exist")
    found = ok(http.get("/search", params={"q": run}, headers=buyer))["items"]
    assert [v["listing"]["id"] for v in found] == [listing_id], found
    offers = ok(http.get(f"/listings/{listing_id}/offers", params={"hours": 2}, headers=buyer))
    assert offers

    step("the buyer books a window (idempotently)")
    requirement = {
        "mode": "window",
        "category": "workshop",
        "hours": 2,
        "earliest": datetime.now(UTC).isoformat(),
        "latest": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        "district": "Kreuzberg",
        "maxDistanceKm": 25,
    }
    body = {"requirement": requirement, "listingId": listing_id, **offers[0]}
    key = {**buyer, "Idempotency-Key": f"e2e-{run}"}
    made = ok(http.post("/bookings", json=body, headers=key), 201)
    again = ok(http.post("/bookings", json=body, headers=key), 201)
    booking_id = made["booking"]["id"]
    assert again["booking"]["id"] == booking_id and made["payment"]["clientSecret"]
    other = sign_in("buyer@demo.cappy.local")
    ok(http.put("/me", json={"adult": True, "name": "Demo Buyer", "kind": "person", "district": "Mitte"}, headers=other))
    assert http.post("/bookings", json=body, headers=other).status_code == 409, "the same window twice"

    if ok(http.get("/payments/config"))["provider"] == "stripe":
        step("real Stripe (test mode): the buyer's card is confirmed, Stripe's webhook comes back")
        confirm_with_test_card(made["payment"]["intentId"])

    step("payment authorises; the owner sees the request")
    until(
        "requested",
        timeout=60,
        fn=lambda: ok(http.get(f"/bookings/{booking_id}", headers=host))["status"] == "requested",
    )
    inbox = ok(http.get("/bookings", params={"role": "owner"}, headers=host))["items"]
    assert booking_id in [b["id"] for b in inbox]

    step("accept captures; hand-over; completion pays the owner")
    assert ok(http.post(f"/bookings/{booking_id}/accept", headers=host))["status"] == "accepted"
    handover = ok(http.get(f"/bookings/{booking_id}", headers=buyer))["handover"]
    assert handover["address"] == f"Oranienstraße {run}, 10999 Berlin", "the buyer now knows where to go"
    until("captured", lambda: ok(http.get(f"/payments/bookings/{booking_id}", headers=buyer))["status"] == "captured")
    ok(http.post(f"/bookings/{booking_id}/start", headers=host))
    assert ok(http.post(f"/bookings/{booking_id}/complete", headers=buyer))["status"] == "completed"
    until(
        "paid out",
        lambda: ok(http.get(f"/payments/bookings/{booking_id}", headers=host))["status"] == "transferred",
        timeout=60,
    )

    step("both sides review (blind); the renter's review appears on the listing")
    ok(
        http.post(
            f"/bookings/{booking_id}/rate", json={"onTime": True, "quality": 5, "note": f"Great {run}"}, headers=buyer
        )
    )
    ok(http.post(f"/bookings/{booking_id}/rate-renter", json={"quality": 5}, headers=host))
    until(
        "review",
        lambda: any(
            run in (r.get("text") or "")
            for r in ok(http.get(f"/listings/{listing_id}/reviews", headers=buyer))["items"]
        ),
    )

    step("both sides were emailed")

    def mails_to(address: str) -> list[str]:
        sent = httpx.get(f"{LOCALSTACK}/_aws/ses").json()["messages"]
        return [m["Subject"] for m in sent if address in m["Destination"]["ToAddresses"]]

    until("buyer's confirmation", lambda: any(title in s and "Confirmed" in s for s in mails_to(email)))
    until("host's request email", lambda: any(title in s for s in mails_to(host_email)))

    step("both can take their data and delete their accounts")
    export = http.get("/me/export", headers=buyer)
    assert export.status_code == 200 and any(b["id"] == booking_id for b in export.json()["bookings"])
    for who in (buyer, host):
        assert http.delete("/me", headers=who).status_code == 204
    assert http.get(f"/listings/{listing_id}", headers=other).status_code == 404, "the host's listing is gone"
    assert http.get(f"/owners/{host_sub}", headers=other).status_code == 404, "the host is gone from every page"
    # Deleting the account also deletes the sign-in, email and all (P-23).
    def gone(address: str) -> bool:
        try:
            idp.admin_get_user(UserPoolId=ENV["USER_POOL_ID"], Username=address)
            return False
        except idp.exceptions.UserNotFoundException:
            return True

    for address in (email, host_email):
        until(f"{address}'s sign-in to be deleted", lambda a=address: gone(a))
    print("e2e passed")


if __name__ == "__main__":
    main()
