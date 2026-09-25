from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "matching"
    # How far ahead a search looks by default when the requirement does not say.
    default_horizon_days: int = 14
    # Nothing can be booked to start sooner: the owner needs time to answer.
    min_lead_minutes: int = 120
