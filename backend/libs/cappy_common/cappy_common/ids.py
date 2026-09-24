"""Opaque ids with a readable prefix, e.g. ``bk_m1x9k2a3f7``.

Same visual shape as the frontend's base-36 timestamp ids, plus random bits
so two requests in the same millisecond cannot collide.
"""

from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def _base36(n: int) -> str:
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(_ALPHABET[r])
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    return f"{prefix}_{_base36(int(time.time() * 1000))}{secrets.token_hex(2)}"
