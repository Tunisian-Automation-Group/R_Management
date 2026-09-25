from __future__ import annotations

from datetime import timedelta

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "booking"
    database_url: str = "sqlite+aiosqlite:///./booking.db"

    # How long a buyer has to complete payment before the window is released.
    payment_timeout_minutes: int = 30
    # How long an owner has to answer. Never later than the window's start: a
    # request nobody answered in time is not a booking.
    answer_within_hours: int = 24
    # After a booked window ends, a job nobody marked complete is completed
    # automatically (and the owner paid) after this long, unless disputed.
    auto_complete_after_hours: int = 48
    # How often the sweeps run, per replica. They use SKIP LOCKED, so every
    # replica can run them without doing the same work twice.
    sweep_seconds: float = 30.0
    # Either party can mark the hand-over from this long before the window.
    start_early_minutes: int = 30
    # Bookings a person may have waiting for payment at once. A card-testing
    # bot makes many; a person makes one or two.
    max_unpaid: int = 3
    # Kill switch (docs/runbook.md): false stops new bookings; everything
    # already booked carries on.
    accepting_bookings: bool = True

    @property
    def payment_timeout(self) -> timedelta:
        return timedelta(minutes=self.payment_timeout_minutes)

    @property
    def answer_within(self) -> timedelta:
        return timedelta(hours=self.answer_within_hours)

    @property
    def auto_complete_after(self) -> timedelta:
        return timedelta(hours=self.auto_complete_after_hours)

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        if not self.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be Postgres (the no-double-booking constraint needs it)")
        return problems
