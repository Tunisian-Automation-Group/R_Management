"""Sustained concurrent use of the running stack (`make load`).

Anonymous browsers search, open listings and ask for offers; signed-in buyers
race to book the same windows. Passing means: no 5xx, no transport errors,
exactly one booking per contested window, and latency percentiles printed
for each call. A laptop is not AWS; this finds errors under concurrency
(pools, locks, timeouts), not capacity numbers.
"""

from __future__ import annotations

import asyncio
import random
import statistics
import sys
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import httpx

API = "http://localhost:8000/api"
ENV = dict(
    line.strip().split("=", 1)
    for line in (Path(__file__).parents[1] / ".local" / "local.env").read_text().splitlines()
    if "=" in line
)
USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 50
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 60
QUERIES = ["saw", "drill", "printer", "van", "laser", "kitchen", "studio", "storage", "lathe", "cnc"]

timings: dict[str, list[float]] = defaultdict(list)
failures: list[str] = []


async def call(c: httpx.AsyncClient, name: str, method: str, path: str, **kw) -> httpx.Response | None:
    t = time.perf_counter()
    try:
        r = await c.request(method, path, **kw)
    except httpx.HTTPError as e:
        failures.append(f"{name}: {type(e).__name__}")
        return None
    timings[name].append((time.perf_counter() - t) * 1000)
    if r.status_code >= 500:
        failures.append(f"{name}: {r.status_code} {r.text[:120]}")
    return r


async def browser(c: httpx.AsyncClient, listing_ids: list[str], until: float) -> None:
    while time.time() < until:
        await call(c, "categories", "GET", "/categories")
        await call(c, "search", "GET", "/search", params={"q": random.choice(QUERIES)})
        lid = random.choice(listing_ids)
        await call(c, "listing", "GET", f"/listings/{lid}")
        await call(c, "offers", "GET", f"/listings/{lid}/offers", params={"hours": 2})
        await call(c, "spotlight", "GET", "/browse/spotlight", params={"district": "Kreuzberg", "maxKm": 20})


def token(email: str, password: str) -> str:
    idp = boto3.client("cognito-idp", region_name="eu-central-1", endpoint_url="http://localhost:9229",
                       aws_access_key_id="x", aws_secret_access_key="x")
    try:
        idp.sign_up(ClientId=ENV["AUTH_CLIENT_IDS"], Username=email, Password=password,
                    UserAttributes=[{"Name": "email", "Value": email}])
        idp.admin_confirm_sign_up(UserPoolId=ENV["USER_POOL_ID"], Username=email)
    except idp.exceptions.UsernameExistsException:
        pass
    auth = idp.initiate_auth(ClientId=ENV["AUTH_CLIENT_IDS"], AuthFlow="USER_PASSWORD_AUTH",
                             AuthParameters={"USERNAME": email, "PASSWORD": password})
    return auth["AuthenticationResult"]["AccessToken"]


async def contested_bookings(c: httpx.AsyncClient, buyers: list[str], listing_id: str) -> int:
    offers = (await c.get(f"/listings/{listing_id}/offers", params={"hours": 2})).json()
    if not offers:
        return -1
    now = datetime.now(UTC)
    body = {
        "requirement": {"mode": "window", "category": "workshop", "hours": 2, "earliest": now.isoformat(),
                        "latest": (now + timedelta(days=28)).isoformat(), "district": "Kreuzberg", "maxDistanceKm": 50},
        "listingId": listing_id,
        **offers[0],
    }
    rs = await asyncio.gather(*(
        call(c, "book", "POST", "/bookings", json=body,
             headers={"Authorization": f"Bearer {b}", "Idempotency-Key": uuid.uuid4().hex})
        for b in buyers
    ))
    return sum(1 for r in rs if r is not None and r.status_code == 201)


async def main() -> None:
    limits = httpx.Limits(max_connections=USERS * 2)
    async with httpx.AsyncClient(base_url=API, timeout=30, limits=limits) as c:
        listings = [v["listing"]["id"] for q in ("saw", "drill", "printer") for v in
                    (await c.get("/search", params={"q": q, "limit": 50})).json()["items"]]
        workshop = [v["listing"]["id"] for v in (await c.get("/search", params={"q": "saw", "limit": 50})).json()["items"]
                    if v["listing"]["mode"] == "window"]
        print(f"{USERS} browsers for {SECONDS:.0f}s over {len(listings)} listings")
        run = uuid.uuid4().hex[:6]
        buyers = [token(f"load-{run}-{i}@example.com", "Load-test-123!") for i in range(10)]
        for b in buyers:
            await c.put("/me", json={"name": "Load Tester", "kind": "person", "district": "Kreuzberg"},
                        headers={"Authorization": f"Bearer {b}"})
        until = time.time() + SECONDS
        browsing = [asyncio.create_task(browser(c, listings, until)) for _ in range(USERS)]
        contested = []
        for lid in workshop[:5]:
            contested.append(await contested_bookings(c, buyers, lid))
        await asyncio.gather(*browsing)

    print(f"{'call':12} {'n':>6} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8}")
    for name, ts in sorted(timings.items()):
        ts.sort()
        q = lambda p: ts[min(len(ts) - 1, int(len(ts) * p))]  # noqa: E731
        print(f"{name:12} {len(ts):6d} {statistics.median(ts):8.1f} {q(0.95):8.1f} {q(0.99):8.1f}")
    print("contested windows, bookings won each:", contested)
    total = sum(len(t) for t in timings.values())
    print(f"{total} requests, {len(failures)} failures")
    for f in sorted(set(failures))[:20]:
        print("  ", f)
    ok = not failures and all(n in (1, -1) for n in contested)
    print("load passed" if ok else "load FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
