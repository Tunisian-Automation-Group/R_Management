"""The analytics lake's Firehose transform (P-6) lives in infra; its
self-check runs with the suite so a change there cannot skip it."""

from __future__ import annotations

import runpy
from pathlib import Path

SCRUB = Path(__file__).parents[4] / "infra" / "platform" / "analytics" / "scrub.py"


def test_the_analytics_scrub_keeps_nobody(capsys):
    runpy.run_path(str(SCRUB), run_name="__main__")
    assert "scrub ok" in capsys.readouterr().out
