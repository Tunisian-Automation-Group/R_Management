from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "catalog"
    database_url: str = "sqlite+aiosqlite:///./catalog.db"

    # Where a caller with no profile yet starts searching from.
    home_district: str = "Kreuzberg"

    # --- photographs (ADR 0007) ------------------------------------------------
    # S3 bucket for listing photos. Empty: a local directory, for single-service
    # development without LocalStack.
    media_bucket: str = ""
    media_dir: str = "./media"
    # The public base URL photos are served from (the CloudFront path in AWS).
    # Empty: same-origin ``/media/<name>``, which CloudFront or the gateway serve.
    media_public_base: str = ""
    # The largest upload accepted, before re-encoding. The app shrinks photos to
    # well under this; it is a backstop, not a budget.
    media_max_bytes: int = 12_000_000
    # Longest edge after re-encoding, and the pixel budget that refuses
    # decompression bombs before they are decoded.
    media_max_edge: int = 2000
    media_max_pixels: int = 16_000_000
    # Photos one person may upload in 24 hours (a listing takes a handful).
    media_daily_quota: int = 100

    # A search never considers more than this many candidate listings; they are
    # the nearest ones matching the category and time window.
    candidate_cap: int = 300

    # Only list owners who can be paid (ADR 0005), so a buyer never picks a
    # listing that checkout will then refuse. Off locally, where the fake
    # payments provider pays anyone.
    require_payable_owners: bool = False
    # Kill switch (docs/runbook.md): false stops new listings (a spam wave);
    # existing ones stay bookable.
    accepting_listings: bool = True
    # Fraud rules (docs/research/2026-09-launch-gaps.md): new listings per owner
    # per day, and the hourly price above which a new owner's listing waits
    # for a staff check.
    max_listings_per_day: int = 20
    # ponytail: minor units, compared across currencies as if all were euros
    # (fine for EUR/GBP/CHF/USD/CAD; SEK, HUF and the like hold sooner). Per
    # currency with the market config (M-2).
    review_above_cents: int = 10_000
    # CloudFront distribution to purge when moderation takes something down
    # (it would otherwise stay cached for up to 10 minutes). Empty locally.
    cdn_distribution_id: str = ""

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        if not self.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be Postgres")
        if not self.media_bucket:
            problems.append("MEDIA_BUCKET must be set; a local directory is not shared between tasks")
        if not self.require_payable_owners:
            problems.append("REQUIRE_PAYABLE_OWNERS must be true")
        return problems
