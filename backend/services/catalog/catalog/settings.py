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
