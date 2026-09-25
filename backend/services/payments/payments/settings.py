from __future__ import annotations

from typing import Literal

from pydantic import SecretStr

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "payments"
    database_url: str = "sqlite+aiosqlite:///./payments.db"

    # "fake" authorises every booking at once and moves no money: local runs
    # and tests without Stripe keys. Deployed, only "stripe" is allowed.
    payments_provider: Literal["fake", "stripe"] = "fake"
    stripe_secret_key: SecretStr = SecretStr("")
    stripe_publishable_key: str = ""
    stripe_webhook_secret: SecretStr = SecretStr("")
    # stripe-mock in contract tests (http://localhost:12111). Empty: api.stripe.com.
    stripe_api_base: str = ""
    # Where Stripe sends an owner back to after onboarding.
    web_base_url: str = "http://localhost:5173"

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        if not self.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be Postgres")
        if self.payments_provider != "stripe":
            problems.append("PAYMENTS_PROVIDER must be stripe")
        if not self.stripe_secret_key.get_secret_value() or not self.stripe_webhook_secret.get_secret_value():
            problems.append("STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET are required")
        if not self.stripe_publishable_key:
            problems.append("STRIPE_PUBLISHABLE_KEY is required")
        if not self.web_base_url.startswith("https://"):
            problems.append("WEB_BASE_URL must be https")
        return problems
