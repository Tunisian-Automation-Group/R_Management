"""Where a listing's photographs live.

A file store on a volume today, named by content hash so the same picture
uploaded twice is one file and every URL is immutable (and cacheable forever).
The interface is the two functions below; an object-storage backend replaces
their bodies and nothing else changes, because the catalog only ever stores
the URL.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from cappy_common.errors import Invalid, NotFound

# What a browser or a phone camera produces once the app has shrunk it. HEIC
# never reaches here: the app draws it to a canvas and sends JPEG.
_KINDS: dict[str, tuple[bytes, str]] = {
    "jpg": (b"\xff\xd8\xff", "image/jpeg"),
    "png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    "webp": (b"RIFF", "image/webp"),
}

NAME = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp)$")


def sniff(data: bytes) -> tuple[str, str]:
    """(extension, content type) from the bytes themselves, never from the
    filename or the declared type, both of which the client chooses."""
    for ext, (magic, ctype) in _KINDS.items():
        if data.startswith(magic) and (ext != "webp" or data[8:12] == b"WEBP"):
            return ext, ctype
    raise Invalid("that is not a JPEG, PNG or WebP image")


def store(media_dir: str, data: bytes, max_bytes: int) -> tuple[str, str]:
    """Write the image; return (name, content type). Idempotent by content."""
    if not data:
        raise Invalid("the upload was empty")
    if len(data) > max_bytes:
        raise Invalid(f"photos are limited to {max_bytes // 1_000_000} MB; the app shrinks them before sending")
    ext, ctype = sniff(data)
    name = f"{hashlib.sha256(data).hexdigest()[:32]}.{ext}"
    root = Path(media_dir)
    root.mkdir(parents=True, exist_ok=True)
    final = root / name
    if not final.exists():
        # Write beside, then rename: a reader never sees a half-written file.
        tmp = root / f".{name}.{os.getpid()}.part"
        tmp.write_bytes(data)
        os.replace(tmp, final)
    return name, ctype


def locate(media_dir: str, name: str) -> tuple[Path, str]:
    """The file behind a media name, or NotFound. The name pattern is the
    whole access control: nothing outside the store can be named."""
    if not NAME.match(name):
        raise NotFound("no such photo")
    path = Path(media_dir) / name
    if not path.is_file():
        raise NotFound("no such photo")
    return path, _KINDS[name.rsplit(".", 1)[1]][1]
