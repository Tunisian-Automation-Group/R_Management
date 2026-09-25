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
    r = httpx.put(f"{API}/me", headers=h, json={"name": name, "kind": "person", "district": "Kreuzberg"})
    r.raise_for_status()
    print(f"demo {role}: profile created")
