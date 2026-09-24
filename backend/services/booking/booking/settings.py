from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "booking"
    database_url: str = "sqlite+aiosqlite:///./booking.db"

    # Seeded hosts answer a request after this many seconds, so the whole flow is
    # walkable without a second person. 0 disables the simulation entirely.
    # Requests to the demo user's own listings are never simulated: those are
    # answered for real in the Earn inbox.
    demo_auto_accept_seconds: float = 5.5
    # Run the auto-accept sweep and the inbox seeder in this process. Turn off
    # on all but one replica, and in tests, which call the workers directly.
    run_background_workers: bool = True

    # One request already waiting in the Earn inbox on a cold start, so the
    # owner side is not empty on first run. Somebody nearby wants two hours of
    # a saw that would otherwise sit in a cupboard tonight: the app's
    # ``seedBookings()``, server-side.
    demo_seed_inbox: bool = True
    demo_seed_requester_id: str = "o17"
    demo_seed_listing_id: str = "l9"
    demo_seed_category: str = "workshop"
    demo_seed_hours: float = 2
    demo_seed_district: str = "Kreuzberg"
