from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "accounts"
    database_url: str = "sqlite+aiosqlite:///./accounts.db"

    # How long a sign-in lasts. A phone that opens the app once a fortnight
    # should not have to sign in every time; a lost phone should not have it
    # forever. Signing out ends it early.
    session_days: int = 30

    # The seeded owner the demo signs in as, so the Earn side has content on
    # a cold start. Set the password empty to seed no account at all.
    seed_on_start: bool = True
    demo_account_owner_id: str = "o1"
    demo_account_email: str = "nadia@cappy.demo"
    demo_account_password: str = "cappy-demo"
