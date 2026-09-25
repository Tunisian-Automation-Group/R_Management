"""Keyset (cursor) pagination.

Every list endpoint returns ``{"items": [...], "nextCursor": "..."}``. The
cursor is an opaque, URL-safe encoding of the sort key of the last item, so
the next page is ``WHERE (sort_key, id) < (:last_key, :last_id)`` against an
index: constant cost per page however deep the client scrolls, unlike
``OFFSET``, which reads and discards every skipped row.
"""

from __future__ import annotations

import base64
import binascii
import json

from pydantic import Field

from .errors import Invalid
from .models import CamelModel

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class Page[T](CamelModel):
    items: list[T]
    next_cursor: str | None = Field(default=None)


def encode_cursor(key: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(key, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        key = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as e:
        raise Invalid("that cursor is not one we issued") from e
    if not isinstance(key, dict):
        raise Invalid("that cursor is not one we issued")
    return key


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, limit))
