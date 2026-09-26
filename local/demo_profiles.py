"""Give the demo buyer and staff accounts a profile (`make seed-demo`).

The seed owns the host's profile; the others would stop at "Tell people who
you are" on first sign-in, and staff could not reach the admin console.
Additive: a profile someone already filled in is left alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import boto3
import httpx

sys.path.insert(0, str(Path(__file__).parent))
from bootstrap import DEMO, DEMO_PASSWORD  # noqa: E402

API = "http://localhost:8000/api"
ENV = dict(
    line.strip().split("=", 1)
    for line in (Path(__file__).parents[1] / ".local" / "local.env").read_text().splitlines()
    if "=" in line
)
NAMES = {"buyer": "Demo Buyer", "staff": "Cappy Staff"}

idp = boto3.client(
    "cognito-idp",
    region_name="eu-central-1",
    endpoint_url="http://localhost:9229",
    aws_access_key_id="x",
    aws_secret_access_key="x",
)
for role, name in NAMES.items():
    email = DEMO[role][0]
    auth = idp.initiate_auth(
        ClientId=ENV["AUTH_CLIENT_IDS"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": DEMO_PASSWORD},
    )
    h = {"Authorization": f"Bearer {auth['AuthenticationResult']['AccessToken']}"}
    if httpx.get(f"{API}/me", headers=h).raise_for_status().json().get("owner"):
        continue
    r = httpx.put(f"{API}/me", headers=h, json={"adult": True, "name": name, "kind": "person", "district": "Kreuzberg"})
    r.raise_for_status()
    print(f"demo {role}: profile created")


# A second host (GD-5), made through the API as a new owner would be: an
# instant-book listing on a weekly schedule, a van run, and a studio above
# the market's review threshold, which waits in the staff console. Skipped
# once they own anything. (No CHF listing: the seed has no Swiss places yet.)
WEEKDAYS = {"weekly": [{"day": d, "start": "09:00", "end": "18:00"} for d in range(1, 6)], "timeZone": "Europe/Berlin"}
WEEKENDS = {"weekly": [{"day": d, "start": "10:00", "end": "16:00"} for d in (6, 7)], "timeZone": "Europe/Berlin"}
HOST2_LISTINGS = [
    {
        "category": "workshop",
        "mode": "window",
        "title": "Bandsaw and bench, book instantly",
        "blurb": "A Record Power bandsaw on a solid bench, dust extraction on.",
        "district": "Neukölln",
        "instructions": "Side door in the courtyard, code sent after booking.",
        "rules": ["Sweep up before you go"],
        "active": True,
        "ratePerHour": 1500,
        "minHours": 1,
        "maxHours": 8,
        "extraFee": 0,
        "extraLabel": "",
        "instantBook": True,
        "availability": WEEKDAYS,
    },
    {
        "category": "freight",
        "mode": "batch",
        "title": "Van run, Neukölln to Leipzig on Saturdays",
        "blurb": "Two pallet spaces free on a run I make every Saturday.",
        "district": "Neukölln",
        "machine": "Ford Transit L3H2",
        "maxDims": {"x": 1200, "y": 800, "z": 1600},
        "unitsPerHour": 0.5,
        "setupHours": 1,
        "ratePerHour": 2500,
        "setupFee": 2000,
        "instructions": "Palletised and wrapped. Pickup at the yard gate.",
        "rules": ["No hazardous goods"],
        "active": True,
        "availability": WEEKENDS,
    },
    {
        "category": "creator",
        "mode": "window",
        "title": "Photo studio with daylight wall (waits for review)",
        "blurb": "Six-metre cyclorama and north light. New owner, so staff check it first.",
        "district": "Neukölln",
        "instructions": "Ring Studio 3.",
        "rules": ["No confetti"],
        "active": True,
        "ratePerHour": 16000,
        "minHours": 2,
        "maxHours": 10,
        "extraFee": 0,
        "extraLabel": "",
        "availability": WEEKDAYS,
    },
]


def signed_in(role: str) -> dict:
    auth = idp.initiate_auth(
        ClientId=ENV["AUTH_CLIENT_IDS"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": DEMO[role][0], "PASSWORD": DEMO_PASSWORD},
    )
    return {"Authorization": f"Bearer {auth['AuthenticationResult']['AccessToken']}"}


h = signed_in("host2")
if not httpx.get(f"{API}/me", headers=h).raise_for_status().json().get("owner"):
    me = {"adult": True, "name": "Demo Host Two", "kind": "person", "district": "Neukölln", "country": "DE"}
    httpx.put(f"{API}/me", headers=h, json=me).raise_for_status()
if not httpx.get(f"{API}/me/listings", headers=h).raise_for_status().json()["items"]:
    for listing in HOST2_LISTINGS:
        r = httpx.post(
            f"{API}/listings", headers=h, json={"listing": listing, "address": "Weserstraße 1, 12047 Berlin"}
        )
        r.raise_for_status()
        held = " (held for review)" if r.json().get("held") else ""
        print(f"demo host2: {listing['title']}{held}, {len(r.json()['slots'])} windows")
