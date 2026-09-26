from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "matching"
    # How far ahead a search looks by default when the requirement does not say.
    default_horizon_days: int = 14
    # Nothing can be booked to start sooner: the owner needs time to answer.
    min_lead_minutes: int = 120

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        # Locally a few minutes, so a tester can walk every flow (GUIDE §A).
        if self.min_lead_minutes < 60:
            problems.append("MIN_LEAD_MINUTES under 60 is a local testing shortcut: owners need time to answer")
        return problems
