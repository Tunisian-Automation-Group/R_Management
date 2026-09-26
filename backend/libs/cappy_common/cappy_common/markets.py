"""Markets (ADR 0013, M-2): one per country, kept as reviewed configuration in
``markets.json``. A market says which cell serves it, its currency, languages
and units, who contracts and pays out there, the tax and consumer-law regime,
the minimum age, and the money thresholds in its own currency. Launching a
country is setting its ``status`` to ``live``.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .errors import Invalid


class Market(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^[A-Z]{2}$")
    cell: Literal["eu", "na"]
    status: Literal["live", "planned"]
    currency: str
    languages: list[str]
    units: Literal["metric", "imperial"]
    # The main time zone (IANA): the default for listings that name none.
    time_zone: str
    legal_entity: str
    stripe_platform: str
    tax_regime: str
    minimum_age: int
    emergency_number: str
    consumer_law: str
    # Money in the currency's minor units (Stripe's form).
    id_check_above: int
    held_listing_above: int
    max_rate_per_hour: int
    # What one staff member may refund alone when settling a dispute, by role
    # (H-6); above it a second staff member approves (four eyes).
    refund_limit_support: int
    refund_limit_lead: int
    # The most a late return's fee may be, on top of the extra time (S-12).
    late_fee_cap: int
    notes: list[str] = []

    def refund_limit(self, role: str) -> int:
        return self.refund_limit_lead if role == "lead" else self.refund_limit_support

    @property
    def live(self) -> bool:
        return self.status == "live"

    def public(self) -> dict:
        """What the apps may know (app-config): nothing about entities or tax."""
        return {
            "currency": self.currency,
            "languages": self.languages,
            "units": self.units,
            "emergencyNumber": self.emergency_number,
            "status": self.status,
            "minimumAge": self.minimum_age,
        }


@cache
def markets() -> dict[str, Market]:
    raw = json.loads(resources.files(__package__).joinpath("markets.json").read_text(encoding="utf-8"))
    return {cc: Market(code=cc, **m) for cc, m in raw["markets"].items()}


def market(country: str | None) -> Market:
    """The market of a country. Unknown countries are refused, not guessed."""
    m = markets().get((country or "").upper())
    if m is None:
        raise Invalid(f"Cappy does not serve {country or 'that country'}", code="market_unknown")
    return m


def live_market(country: str | None) -> Market:
    """The market of a country that is open, or 422 ``market_not_live``: a
    launch is a config change, never a code change."""
    m = market(country)
    if not m.live:
        raise Invalid(f"Cappy is not open in {m.code} yet", code="market_not_live")
    return m


def market_of_currency(currency: str) -> Market:
    """The market a booking's money belongs to, when only its currency is
    known: the live market with that currency, else any. ponytail: bookings
    do not store the owner's country; markets sharing a currency share
    their money limits in markets.json, so this is the same answer."""
    same = [m for m in markets().values() if m.currency == currency.upper()]
    if not same:
        raise Invalid(f"no market uses {currency}", code="market_unknown")
    return next((m for m in same if m.live), same[0])


def public_markets() -> dict[str, dict]:
    return {cc: m.public() for cc, m in markets().items()}
