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
MODE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdigit() else "closed"
ARGS = [a for a in sys.argv[1:] if a.isdigit()]
USERS = int(ARGS[0]) if ARGS else 50
SECONDS = float(ARGS[1]) if len(ARGS) > 1 else 60
QUERIES = ["saw", "drill", "printer", "van", "laser", "kitchen", "studio", "storage", "lathe", "cnc"]

timings: dict[str, list[float]] = defaultdict(list)
failures: list[str] = []
shed = 0


class SignedIn:
    """Signed-in only (GOAL 13): every browser carries a token."""

    def __init__(self, c: httpx.AsyncClient, token: str) -> None:
        self._c, self._h = c, {"Authorization": f"Bearer {token}"}

    async def request(self, method: str, path: str, **kw):  # noqa: ANN003, ANN201
        return await self._c.request(method, path, headers={**self._h, **kw.pop("headers", {})}, **kw)


async def call(c: httpx.AsyncClient, name: str, method: str, path: str, **kw) -> httpx.Response | None:
    t = time.perf_counter()
    try:
        r = await c.request(method, path, **kw)
    except httpx.HTTPError as e:
        failures.append(f"{name}: {type(e).__name__}")
        return None
    timings[name].append((time.perf_counter() - t) * 1000)
    if r.status_code == 503 and "overloaded" in r.text:
        global shed
        shed += 1  # load shedding doing its job: fast, and says when to come back
    elif r.status_code >= 500:
        failures.append(f"{name}: {r.status_code} {r.text[:120]}")
    return r


async def browser(c: httpx.AsyncClient, listing_ids: list[str], until: float, token: str) -> None:
    c = SignedIn(c, token)
    while time.time() < until:
        await call(c, "categories", "GET", "/categories")
        await call(c, "search", "GET", "/search", params={"q": random.choice(QUERIES)})
        lid = random.choice(listing_ids)
        await call(c, "listing", "GET", f"/listings/{lid}")
        await call(c, "offers", "GET", f"/listings/{lid}/offers", params={"hours": 2})
        await call(c, "spotlight", "GET", "/browse/spotlight", params={"district": "Kreuzberg", "maxKm": 20})


IDP = boto3.client(
    "cognito-idp",
    region_name="eu-central-1",
    endpoint_url="http://localhost:9229",
    aws_access_key_id="x",
    aws_secret_access_key="x",
)


def token(email: str, password: str) -> str:
    idp = IDP
    try:
        idp.sign_up(
            ClientId=ENV["AUTH_CLIENT_IDS"],
            Username=email,
            Password=password,
            UserAttributes=[{"Name": "email", "Value": email}],
        )
        idp.admin_confirm_sign_up(UserPoolId=ENV["USER_POOL_ID"], Username=email)
    except idp.exceptions.UsernameExistsException:
        pass
    auth = idp.initiate_auth(
        ClientId=ENV["AUTH_CLIENT_IDS"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return auth["AuthenticationResult"]["AccessToken"]


async def contested_bookings(c: httpx.AsyncClient, buyers: list[str], listing_id: str) -> int:
    offers = (await SignedIn(c, buyers[0]).request("GET", f"/listings/{listing_id}/offers", params={"hours": 2})).json()
    if not offers:
        return -1
    now = datetime.now(UTC)
    body = {
        "requirement": {
            "mode": "window",
            "category": "workshop",
            "hours": 2,
            "earliest": now.isoformat(),
            "latest": (now + timedelta(days=28)).isoformat(),
            "district": "Kreuzberg",
            "maxDistanceKm": 50,
        },
        "listingId": listing_id,
        **offers[0],
    }
    rs = await asyncio.gather(
        *(
            call(
                c,
                "book",
                "POST",
                "/bookings",
                json=body,
                headers={"Authorization": f"Bearer {b}", "Idempotency-Key": uuid.uuid4().hex},
            )
            for b in buyers
        )
    )
    won = [(r, b) for r, b in zip(rs, buyers, strict=True) if r is not None and r.status_code == 201]
    # Leave nothing behind: the demo data stays the demo data.
    for r, b in won:
        await c.post(f"/bookings/{r.json()['booking']['id']}/cancel", headers={"Authorization": f"Bearer {b}"})
    return len(won)


async def open_model(
    c: httpx.AsyncClient, listing_ids: list[str], rate: float, seconds: float, buyers: list[str]
) -> None:
    """Requests arrive at `rate` per second whatever the system does (open
    model): a slow system cannot slow its own load down and hide."""
    tasks = []
    workshop = listing_ids

    async def one() -> None:
        c_ = SignedIn(c, random.choice(buyers))
        roll = random.random()
        lid = random.choice(workshop)
        if roll < 0.90:
            await random.choice(
                [
                    lambda: call(c_, "search", "GET", "/search", params={"q": random.choice(QUERIES)}),
                    lambda: call(c_, "listing", "GET", f"/listings/{lid}"),
                    lambda: call(c_, "offers", "GET", f"/listings/{lid}/offers", params={"hours": 2}),
                    lambda: call(
                        c_, "spotlight", "GET", "/browse/spotlight", params={"district": "Kreuzberg", "maxKm": 20}
                    ),
                ]
            )()
        elif roll < 0.98 and buyers:
            await call(c_, "my-bookings", "GET", "/bookings")
        else:
            await call(c_, "categories", "GET", "/categories")

    end = time.time() + seconds
    while time.time() < end:
        tasks.append(asyncio.create_task(one()))
        await asyncio.sleep(random.expovariate(rate))
    await asyncio.gather(*tasks)


async def main() -> None:
    limits = httpx.Limits(max_connections=USERS * 2)
    async with httpx.AsyncClient(base_url=API, timeout=30, limits=limits) as c:
        run = uuid.uuid4().hex[:6]
        buyers = [token(f"load-{run}-{i}@example.com", "Load-test-123!") for i in range(10)]
        me = SignedIn(c, buyers[0])
        listings = [
            v["listing"]["id"]
            for q in ("saw", "drill", "printer")
            for v in (await me.request("GET", "/search", params={"q": q, "limit": 50})).json()["items"]
        ]
        workshop = [
            v["listing"]["id"]
            for v in (await me.request("GET", "/search", params={"q": "saw", "limit": 50})).json()["items"]
            if v["listing"]["mode"] == "window"
        ]
        print(f"{USERS} browsers for {SECONDS:.0f}s over {len(listings)} listings")
        for b in buyers:
            await c.put(
                "/me",
                json={"adult": True, "name": "Load Tester", "kind": "person", "district": "Kreuzberg"},
                headers={"Authorization": f"Bearer {b}"},
            )
        contested = []
        if MODE == "spike":
            # Baseline, a 10x spike, then baseline again.
            base = USERS
            print(f"spike: {base}/s for 20 s, {base * 10}/s for {SECONDS:.0f} s, {base}/s for 20 s")
            await open_model(c, listings, base, 20, buyers)
            await open_model(c, listings, base * 10, SECONDS, buyers)
            await open_model(c, listings, base, 20, buyers)
        elif MODE in ("mixed", "soak"):
            print(f"{MODE}: open model at {USERS}/s for {SECONDS:.0f} s")
            runner = asyncio.create_task(open_model(c, listings, USERS, SECONDS, buyers))
            for lid in workshop[:5]:
                contested.append(await contested_bookings(c, buyers, lid))
            await runner
        else:
            until = time.time() + SECONDS
            browsing = [asyncio.create_task(browser(c, listings, until, buyers[i % len(buyers)])) for i in range(USERS)]
            for lid in workshop[:5]:
                contested.append(await contested_bookings(c, buyers, lid))
            await asyncio.gather(*browsing)

        for b in buyers:
            await c.delete("/me", headers={"Authorization": f"Bearer {b}"})
    for i in range(10):
        try:
            IDP.admin_delete_user(UserPoolId=ENV["USER_POOL_ID"], Username=f"load-{run}-{i}@example.com")
        except Exception:  # noqa: BLE001
            pass

    print(f"{'call':12} {'n':>6} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8}")
    for name, ts in sorted(timings.items()):
        ts.sort()
        q = lambda p: ts[min(len(ts) - 1, int(len(ts) * p))]  # noqa: E731
        print(f"{name:12} {len(ts):6d} {statistics.median(ts):8.1f} {q(0.95):8.1f} {q(0.99):8.1f}")
    print("contested windows, bookings won each:", contested)
    total = sum(len(t) for t in timings.values())
    print(f"{total} requests, {len(failures)} failures, {shed} shed with 503 + Retry-After")
    for f in sorted(set(failures))[:20]:
        print("  ", f)
    ok = not failures and all(n in (1, -1) for n in contested)
    print("load passed" if ok else "load FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
