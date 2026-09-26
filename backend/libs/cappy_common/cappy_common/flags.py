"""Feature flags with percentage rollouts (S-26), on top of the kill switches.

Configured as ``FEATURE_FLAGS="name:percent,..."``. 0 and 100 are plain
off/on. Anything between is a rollout: a person is in it when a stable hash
of ``name:userId`` lands below the percent, so the same person gets the same
answer on every device and every request, and raising the percent only adds
people. The app evaluates rollouts itself with the same hash, which keeps
``/api/app-config`` one cacheable answer for everyone; a service enforcing a
flag calls ``enabled`` with the caller's id.
"""

from __future__ import annotations


def parse(spec: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, pct = part.partition(":")
        out[name.strip()] = max(0, min(100, int(pct or 100)))
    return out


def bucket(name: str, user_id: str) -> int:
    """FNV-1a (32 bit) of ``name:userId``, mod 100. Tiny, and trivial to
    reproduce in the app (web/src: the same function)."""
    h = 0x811C9DC5
    for b in f"{name}:{user_id}".encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h % 100


def enabled(flags: dict[str, int], name: str, user_id: str | None) -> bool:
    pct = flags.get(name, 0)
    if pct >= 100 or pct <= 0:
        return pct >= 100
    return user_id is not None and bucket(name, user_id) < pct


if __name__ == "__main__":
    f = parse("chat:100, dark:0, newcheckout:25")
    assert f == {"chat": 100, "dark": 0, "newcheckout": 25}
    assert enabled(f, "chat", None) and not enabled(f, "dark", "u1") and not enabled(f, "newcheckout", None)
    assert bucket("newcheckout", "user-1") == bucket("newcheckout", "user-1")
    share = sum(enabled(f, "newcheckout", f"u{i}") for i in range(10_000)) / 10_000
    assert 0.22 < share < 0.28, share
    print("flags ok", bucket("newcheckout", "user-1"))
