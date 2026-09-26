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
    # The ID check (identity.py): "stripe" (Stripe Identity) or "fake". Empty
    # follows PAYMENTS_PROVIDER. Another vendor is a class in identity.py.
    identity_provider: Literal["", "fake", "stripe"] = ""
    # Where Stripe sends an owner back to after onboarding.
    web_base_url: str = "http://localhost:5173"
    # Kill switch (docs/runbook.md): false holds every payout on its queue
    # (retried with backoff) until switched back on. Nothing is lost.
    payouts_on: bool = True
    # The issuer on fee invoices (§ 14 (4) UStG): the operator's legal name,
    # postal address (comma-separated lines) and tax number and/or VAT ID.
    legal_company: str = "Cappy (local, not a company)"
    legal_address: str = "Musterstraße 1, 10115 Berlin"
    legal_vat_id: str = ""
    legal_tax_number: str = "00/000/00000 (local)"
    # The issuer's calendar and tax (invoices.Issuer): Germany by default.
    invoice_time_zone: str = "Europe/Berlin"
    invoice_tax_rate_bps: int = 1900
    invoice_tax_label: str = "USt"
    invoice_retention_years: int = 10

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        if not self.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be Postgres")
        if self.payments_provider != "stripe":
            problems.append("PAYMENTS_PROVIDER must be stripe")
        if not self.stripe_secret_key.get_secret_value() or not self.stripe_webhook_secret.get_secret_value():
            problems.append("STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET are required")
        if self.identity_provider == "fake":
            problems.append("IDENTITY_PROVIDER must not be fake")
        if not self.stripe_publishable_key:
            problems.append("STRIPE_PUBLISHABLE_KEY is required")
        if "local" in self.legal_company or "Muster" in self.legal_address:
            problems.append("LEGAL_COMPANY and LEGAL_ADDRESS must be the operator's (invoices, § 14 UStG)")
        if not self.legal_vat_id and (not self.legal_tax_number or "local" in self.legal_tax_number):
            problems.append("LEGAL_VAT_ID or LEGAL_TAX_NUMBER is required (invoices, § 14 UStG)")
        if not self.web_base_url.startswith("https://"):
            problems.append("WEB_BASE_URL must be https")
        return problems
