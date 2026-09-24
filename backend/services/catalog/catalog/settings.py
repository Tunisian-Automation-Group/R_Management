from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "catalog"
    database_url: str = "sqlite+aiosqlite:///./catalog.db"
    # Load the demo world into an empty database on startup.
    seed_on_start: bool = True
    # Local midnight in this zone anchors the seeded idle windows ("today 18:00").
    seed_timezone: str = "Europe/Berlin"
    # Where a caller with no owner record starts searching from (``GET /me``).
    home_district: str = "Kreuzberg"
    # Listing photographs: a directory on a volume (see docker-compose), the
    # largest upload accepted, and the base the returned URLs are built on.
    # Empty base means a same-origin path ("/media/<name>"), which is what the
    # gateway serves; set it to the public URL when the API is hosted apart.
    media_dir: str = "./media"
    media_max_bytes: int = 10_000_000
    media_public_base: str = ""
