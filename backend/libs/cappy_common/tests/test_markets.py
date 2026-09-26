"""markets.json is reviewed configuration (M-2): a wrong value here charges
the wrong currency or opens a country by accident, so the file is checked."""

from __future__ import annotations

import typing

import pytest

from cappy_common.errors import Invalid
from cappy_common.markets import live_market, market, markets, public_markets
from cappy_common.models import Currency

# The languages that have catalogues (web and notification texts); any other
# falls back to English, which every market therefore lists.
CATALOGUES = {"en", "de", "fr"}
EEA = set("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE IS LI NO".split())


def test_every_market_is_well_formed():
    allowed = set(typing.get_args(Currency))
    ms = markets()
    assert EEA | {"CH", "GB", "US", "CA"} <= set(ms), "all of Europe, the US and Canada (GOAL 16)"
    for cc, m in ms.items():
        assert m.currency in allowed, (cc, m.currency)
        assert "en" in m.languages, f"{cc}: English is the fallback, so it is listed"
        assert all(len(lang) == 2 and lang.islower() for lang in m.languages), cc
        assert 0 < m.held_listing_above < m.id_check_above < m.max_rate_per_hour, cc
        assert m.minimum_age >= 18 and m.emergency_number.isdigit(), cc
        assert (m.cell == "na") == (cc in ("US", "CA")), cc
        if m.live:
            assert m.languages[0] in CATALOGUES, f"{cc} is live: its first language needs a catalogue"


def test_only_dach_is_open_and_launching_is_config():
    assert {cc for cc, m in markets().items() if m.live} == {"DE", "AT", "CH"}
    assert live_market("de").currency == "EUR" and market("CH").currency == "CHF"
    with pytest.raises(Invalid) as e:
        live_market("FR")
    assert e.value.code == "market_not_live"
    with pytest.raises(Invalid) as e:
        market("ZZ")
    assert e.value.code == "market_unknown"


def test_the_apps_see_no_entities_or_tax():
    ca = public_markets()["CA"]
    assert ca == {
        "currency": "CAD",
        "languages": ["en", "fr"],
        "units": "metric",
        "emergencyNumber": "911",
        "status": "planned",
        "minimumAge": 19,
    }
