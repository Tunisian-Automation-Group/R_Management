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
    notes: list[str] = []

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


def public_markets() -> dict[str, dict]:
    return {cc: m.public() for cc, m in markets().items()}
