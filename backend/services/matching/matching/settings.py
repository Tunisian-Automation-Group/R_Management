from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "matching"
    # The world is re-fetched from the catalog after this many seconds, or
    # immediately when a ``catalog.changed`` event arrives.
    world_cache_ttl_seconds: float = 5.0
