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
    # S-21: how long the other side has to answer an offer in a dispute
    # before it goes to staff. Local compose shortens it so a tester sees an
    # escalation in minutes (GUIDE §A5); deployed it is never under 72 hours.
    dispute_offer_minutes: int = 72 * 60
    # S-12: a late return is reported from the booked end until this long
    # after. Locally the owner may report it this many minutes before the end,
    # so testers need not wait for a booking to finish; deployed it is 0.
    late_return_claim_hours: int = 24
    late_return_early_minutes: int = 0
    # Bookings a person may have waiting for payment at once. A card-testing
    # bot makes many; a person makes one or two.
    max_unpaid: int = 3
    # Booking requests one person may make in 24 hours (velocity limit).
    max_requests_per_day: int = 10
    # Renter identity verification for these categories (comma-separated;
    # none today: freight is space on runs already going, nobody drives
    # someone else's van), and for any booking above the market's
    # threshold (markets.json, in its own currency).
    verify_categories: str = ""

    # Moderate and strict cancellation policies charge for late cancellations;
    # off until counsel confirms them against the EU withdrawal right (G-B2).
    # Switched with the "paidCancellationPolicies" feature flag, the one the
    # app reads to word the policy (FEATURE_FLAGS="paidCancellationPolicies:100").
    # A money rule is everyone or no one: a partial rollout counts as off.
    @property
    def paid_cancellation_policies(self) -> bool:
        from cappy_common.flags import enabled, parse

        return enabled(parse(self.feature_flags), "paidCancellationPolicies", None)

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

    @property
    def dispute_offer_window(self) -> timedelta:
        return timedelta(minutes=self.dispute_offer_minutes)

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        if not self.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be Postgres (the no-double-booking constraint needs it)")
        # The local shortcuts (GUIDE §A, compose.yaml) never reach real people.
        if self.start_early_minutes > 60:
            problems.append("START_EARLY_MINUTES above 60 is a local testing shortcut")
        if self.auto_complete_after_hours < 24:
            problems.append("AUTO_COMPLETE_AFTER_HOURS under 24 leaves no time to report a problem")
        if self.dispute_offer_minutes < 72 * 60:
            problems.append("DISPUTE_OFFER_MINUTES under 72 hours rushes people into a staff decision")
        if self.late_return_early_minutes > 0:
            problems.append("LATE_RETURN_EARLY_MINUTES is a local testing shortcut")
        if self.late_return_claim_hours < 24:
            problems.append("LATE_RETURN_CLAIM_HOURS under 24 leaves owners no time to report")
        return problems
