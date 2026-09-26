"""Listing photographs (ADR 0007).

Every upload is decoded and re-encoded, never stored as sent:

* it must really be a JPEG, PNG or WebP (decoded, not sniffed by magic bytes,
  so a polyglot file that is also HTML or a script is refused);
* the pixel count is checked before decoding the image data, so a tiny file
  that inflates to gigapixels (a decompression bomb) never allocates memory;
* EXIF and every other metadata block is dropped. A phone photo of kit
  standing in someone's garage carries the GPS position of their home;
* the image is oriented upright, bounded to ``media_max_edge`` pixels on its
  longest side, and written as WebP.

The result is named by the hash of the *re-encoded* bytes and stored once, so
every URL is immutable and cacheable forever. In AWS it goes to S3 and is
served by CloudFront; the local directory backend exists for running one
service on a laptop.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from cappy_common.errors import Invalid, NotFound

# A photo and its renditions (U-40): <hash>.webp, and <hash>-<w>.webp for
# each width, made at upload so the CDN serves them as files (no resizing at
# the edge). A width the photo does not reach is stored at its own size.
WIDTHS = (400, 800, 1600)
NAME = re.compile(r"^[a-f0-9]{40}(-(400|800|1600))?\.webp$")


def rendition(name: str, width: int) -> str:
    return name.removesuffix(".webp") + f"-{width}.webp"


def renditions_of(name: str) -> list[str]:
    return [rendition(name, w) for w in WIDTHS]


_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO: multi-picture JPEG some phones write


@dataclass(frozen=True)
class Processed:
    name: str
    data: bytes
    width: int
    height: int
    # Width → the photo at that width, and its dominant colour ("#rrggbb"),
    # the placeholder shown while it loads.
    renditions: dict[int, bytes] = field(default_factory=dict)
    color: str = ""


def _encode(img: Image.Image) -> bytes:
    out = io.BytesIO()
    # No exif=, no icc_profile=: nothing from the original survives.
    img.save(out, format="WEBP", quality=82, method=4)
    return out.getvalue()


def sizes(img: Image.Image, full: bytes) -> tuple[dict[int, bytes], str]:
    """The renditions and the dominant colour of a decoded, oriented photo."""
    r, g, b = img.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    out: dict[int, bytes] = {}
    for w in WIDTHS:
        if img.width <= w:
            out[w] = full
        else:
            out[w] = _encode(img.resize((w, max(1, round(img.height * w / img.width))), Image.Resampling.LANCZOS))
    return out, f"#{r:02x}{g:02x}{b:02x}"


def resize_stored(data: bytes) -> tuple[dict[int, bytes], str]:
    """Renditions of a photo already stored (a WebP we made): for uploads from
    before renditions existed."""
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        return sizes(img, data)


def process(data: bytes, *, max_bytes: int, max_edge: int, max_pixels: int) -> Processed:
    if not data:
        raise Invalid("the upload was empty")
    if len(data) > max_bytes:
        raise Invalid(f"photos are limited to {max_bytes // 1_000_000} MB")
    # Refuse bombs by header, before any pixel data is decoded.
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in _FORMATS:
                raise Invalid("that is not a JPEG, PNG or WebP image")
            w, h = probe.size
            if w * h > max_pixels:
                raise Invalid("that image is too large to process")
            probe.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img) or img
            img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            encoded = _encode(img)
            width, height = img.size
            renditions, color = sizes(img, encoded)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as e:
        raise Invalid("that is not an image we can read") from e
    return Processed(
        name=f"{hashlib.sha256(encoded).hexdigest()[:40]}.webp",
        data=encoded,
        width=width,
        height=height,
        renditions=renditions,
        color=color,
    )


class MediaStore:
    async def put(self, name: str, data: bytes) -> None:
        raise NotImplementedError

    async def get(self, name: str) -> bytes:
        raise NotImplementedError

    async def delete(self, name: str) -> None:
        raise NotImplementedError


class DirectoryStore(MediaStore):
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    async def put(self, name: str, data: bytes) -> None:
        def write() -> None:
            self.root.mkdir(parents=True, exist_ok=True)
            final = self.root / name
            if not final.exists():
                tmp = self.root / f".{name}.part"
                tmp.write_bytes(data)
                tmp.replace(final)

        await asyncio.to_thread(write)

    async def get(self, name: str) -> bytes:
        if not NAME.match(name):
            raise NotFound("no such photo")
        path = self.root / name
        if not path.is_file():
            raise NotFound("no such photo")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, name: str) -> None:
        if NAME.match(name):
            await asyncio.to_thread((self.root / name).unlink, True)


class S3Store(MediaStore):
    def __init__(self, bucket: str, settings: Any, prefix: str = "media") -> None:
        import boto3

        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.aws_endpoint_url:
            kwargs["endpoint_url"] = settings.aws_endpoint_url
        self.bucket, self.prefix = bucket, prefix
        self._s3 = boto3.client("s3", **kwargs)

    def _key(self, name: str) -> str:
        # media/: the path CloudFront serves it at (/media/<name>). private/:
        # hand-over evidence, which CloudFront cannot read (P-27).
        return f"{self.prefix}/{name}"

    async def put(self, name: str, data: bytes) -> None:
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self.bucket,
            Key=self._key(name),
            Body=data,
            ContentType="image/webp",
            CacheControl="public, max-age=31536000, immutable" if self.prefix == "media" else "private, no-store",
        )

    async def get(self, name: str) -> bytes:
        if not NAME.match(name):
            raise NotFound("no such photo")
        try:
            obj = await asyncio.to_thread(self._s3.get_object, Bucket=self.bucket, Key=self._key(name))
        except self._s3.exceptions.NoSuchKey as e:
            raise NotFound("no such photo") from e
        return await asyncio.to_thread(obj["Body"].read)

    async def delete(self, name: str) -> None:
        if NAME.match(name):
            await asyncio.to_thread(self._s3.delete_object, Bucket=self.bucket, Key=self._key(name))


def make_store(settings: Any, *, private: bool = False) -> MediaStore:
    """Public listing photos, or (``private``) hand-over evidence, which only
    the two sides of a booking and staff may see (P-27)."""
    if settings.media_bucket:
        return S3Store(settings.media_bucket, settings, prefix="private" if private else "media")
    return DirectoryStore(str(Path(settings.media_dir) / "private") if private else settings.media_dir)


EVIDENCE_REF = "evidence:"


def evidence_ref(name: str) -> str:
    """What an evidence upload returns instead of a URL: a reference only
    booking can turn into a (signed, short-lived) link."""
    return EVIDENCE_REF + name


def name_from_ref(ref: str) -> str | None:
    name = ref.removeprefix(EVIDENCE_REF) if ref.startswith(EVIDENCE_REF) else None
    return name if name and NAME.match(name) else None


def url_for(settings: Any, name: str) -> str:
    return f"{settings.media_public_base.rstrip('/')}/media/{name}"


def name_from_url(settings: Any, url: str) -> str | None:
    """The media name behind one of our photo URLs, or None for anything else."""
    prefix = f"{settings.media_public_base.rstrip('/')}/media/"
    if not url.startswith(prefix):
        return None
    name = url.removeprefix(prefix)
    return name if NAME.match(name) else None
