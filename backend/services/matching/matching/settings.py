from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "matching"
    # How far ahead a search looks by default when the requirement does not say.
    default_horizon_days: int = 14
