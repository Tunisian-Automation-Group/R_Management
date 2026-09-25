"""Opaque, sortable ids with a readable prefix, e.g. ``bk_01j8x3k2m4n5p6q7r8s9t0v1w2``.

The body is a ULID in lowercase Crockford base32: 48 bits of milliseconds then
80 random bits. Sortable by creation time (useful for keyset pagination and
index locality), and collision-free in practice: two ids in the same
millisecond collide with probability 2⁻⁸⁰. The previous format carried 16
random bits per millisecond, which collides under ordinary load.

Ids are always minted by the server. A client never chooses one.
"""

from __future__ import annotations

import re
import secrets
import time

_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
ULID_RE = re.compile(r"^[0-9a-hjkmnp-tv-z]{26}$")


def _encode(n: int, length: int) -> str:
    out = []
    for _ in range(length):
        n, r = divmod(n, 32)
        out.append(_CROCKFORD[r])
    return "".join(reversed(out))


def ulid(now_ms: int | None = None) -> str:
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    return _encode(ms, 10) + _encode(secrets.randbits(80), 16)


def new_id(prefix: str) -> str:
    return f"{prefix}_{ulid()}"


def id_pattern(prefix: str) -> str:
    """A regex a path or body parameter can be validated against."""
    return rf"^{prefix}_[0-9a-hjkmnp-tv-z]{{26}}$"
